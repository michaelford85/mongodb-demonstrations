#!/usr/bin/env python3
"""
Demo-grade Agentic AI (OpenAI + MCP + MongoDB) over HTTP MCP transport.

This version fixes 400/406 errors by using the official `mcp` Python client
(`streamable_http_client` + `ClientSession`) instead of hand-rolled HTTP JSON-RPC.

Run:
  ./scripts/start_mcp_server.sh
  SHOW_TOOLS=1 SHOW_MEMORY=1 python demo_mcp_agent_http_simple_fixed_v3.py

Commands:
  remember <text>   save a memory doc (embedded via Voyage)
  clear             delete all memory docs
  exit              quit

Env (.env):
  MDB_MCP_SERVER_URL=http://127.0.0.1:3000/mcp
  OPENAI_API_KEY=...
  OPENAI_MODEL=gpt-5
  MDB_MCP_VOYAGE_API_KEY=...
  VOYAGE_MODEL=voyage-4
  VOYAGE_OUTPUT_DIM=1024

  MOVIES_DB=sample_mflix
  MOVIES_COLLECTION=movies
  MOVIES_VECTOR_INDEX=movies_voyage_v4
  EMBEDDING_FIELD=embedding_voyage_v4

  MEMORY_DB=mcp_config
  MEMORY_COLLECTION=agent_memory
  MEMORY_VECTOR_INDEX=memory_voyage_v4
  MEMORY_EMBED_FIELD=embedding_voyage_v4

Optional:
  SHOW_TOOLS=1, SHOW_MEMORY=1
"""

from __future__ import annotations

import time
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import json_util
from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI
import voyageai

# --- Silence noisy MCP 'ping' notification validation logs (without touching transport) ---
import logging

class _DropPingValidation(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # mcp client sometimes logs: "Failed to validate notification ... input_value='ping'"
        if 'Failed to validate notification' in msg and "input_value='ping'" in msg:
            return False
        return True

# Apply filter broadly (root) so it works regardless of which logger emits it.
_root = logging.getLogger()
_root.addFilter(_DropPingValidation())

# Reduce default noise from mcp/anyio/httpx unless DEBUG_MCP=1
if os.getenv('DEBUG_MCP', '0') != '1':
    logging.getLogger('mcp').setLevel(logging.ERROR)
    logging.getLogger('anyio').setLevel(logging.ERROR)
    logging.getLogger('httpx').setLevel(logging.ERROR)
# --- end log filter ---



def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v not in (None, "") else default


def _must(name: str) -> str:
    v = _env(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tool_result_text(res: Any) -> str:
    """Extract text from MCP call_tool results (dicts or SDK objects)."""
    if res is None:
        return ""
    if isinstance(res, str):
        return res

    content = None
    if isinstance(res, dict):
        content = res.get("content")
    elif hasattr(res, "content"):
        try:
            content = getattr(res, "content")
        except Exception:
            content = None

    parts: List[str] = []
    if isinstance(content, list):
        for item in content:
            # Dict form: {"type":"text","text":"..."}
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                if t:
                    parts.append(str(t))
                continue

            # Object form: TextContent(type="text", text="...")
            if hasattr(item, "type") and getattr(item, "type", None) == "text":
                t = getattr(item, "text", None)
                if t:
                    parts.append(str(t))

    if parts:
        return "".join(parts)

    # Fallbacks
    if isinstance(res, dict):
        return json.dumps(res, default=str)
    return str(res)



def _extract_json_payload(text: str) -> str:
    """Best-effort extraction of a JSON/EJSON payload from noisy tool output."""
    if not text:
        return ""
    t = text.strip()
    # If it's already JSON-ish, return as-is.
    if (t.startswith('{') and t.endswith('}')) or (t.startswith('[') and t.endswith(']')):
        return t
    import re as _re
    m = _re.search(r"(\[.*\]|\{.*\})", t, flags=_re.S)
    return m.group(1) if m else t

def _parse_docs(text: str) -> List[Dict[str, Any]]:
    """
    Parse tool output text into a list of MongoDB documents.
    The MongoDB MCP server may return:
      - plain JSON
      - Extended JSON (EJSON)
      - JSON embedded after wrapper/warning lines
    """
    if not text:
        return []

    payload = _extract_json_payload(text) or text.strip()

    # Try EJSON first (handles {"$numberDouble": "..."} etc.)
    try:
        from bson import json_util  # type: ignore
        parsed = json_util.loads(payload)
    except Exception:
        parsed = None

    if parsed is None:
        try:
            parsed = json.loads(payload)
        except Exception:
            parsed = None

    if parsed is None:
        # Last-ditch: find the first JSON-ish substring
        m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text, flags=re.S)
        if m:
            sub = m.group(1)
            try:
                from bson import json_util  # type: ignore
                parsed = json_util.loads(sub)
            except Exception:
                try:
                    parsed = json.loads(sub)
                except Exception:
                    parsed = None

    if isinstance(parsed, list):
        return [d for d in parsed if isinstance(d, dict)]
    if isinstance(parsed, dict):
        for key in ("documents", "result", "value", "data"):
            v = parsed.get(key)
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]
    return []


def load_cfg() -> Cfg:
    load_dotenv()
    return Cfg(
        mcp_url=_env("MDB_MCP_SERVER_URL", "http://127.0.0.1:3000/mcp") or "http://127.0.0.1:3000/mcp",
        openai_model=_env("OPENAI_MODEL", "gpt-5") or "gpt-5",
        voyage_key=_must("MDB_MCP_VOYAGE_API_KEY"),
        voyage_model=_env("VOYAGE_MODEL", "voyage-4") or "voyage-4",
        voyage_dim=int(_env("VOYAGE_OUTPUT_DIM", "1024") or "1024"),
        movies_db=_env("MOVIES_DB", "sample_mflix") or "sample_mflix",
        movies_coll=_env("MOVIES_COLLECTION", "movies") or "movies",
        movies_index=_env("MOVIES_VECTOR_INDEX", "movies_voyage_v4") or "movies_voyage_v4",
        movies_embed=_env("EMBEDDING_FIELD", "embedding_voyage_v4") or "embedding_voyage_v4",
        mem_db=_env("MEMORY_DB", "mcp_config") or "mcp_config",
        mem_coll=_env("MEMORY_COLLECTION", "agent_memory") or "agent_memory",
        mem_index=_env("MEMORY_VECTOR_INDEX", "memory_voyage_v4") or "memory_voyage_v4",
        mem_embed=_env("MEMORY_EMBED_FIELD", "embedding_voyage_v4") or "embedding_voyage_v4",
    )


async def connect_mcp(mcp_url: str) -> Tuple[ClientSession, Any]:
    cm = streamable_http_client(mcp_url)
    streams = await cm.__aenter__()

    if isinstance(streams, tuple):
        if len(streams) < 2:
            raise RuntimeError("streamable_http_client returned a short tuple")
        read, write = streams[0], streams[1]
    else:
        read = getattr(streams, "read", None)
        write = getattr(streams, "write", None)
        if read is None or write is None:
            raise RuntimeError("streamable_http_client returned unexpected object")

    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return session, cm

def _short(s: str, n: int = 180) -> str:
    s = s.replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 3] + "..."

def _extract_vectorsearch_meta(pipeline: Any) -> Dict[str, Any]:
    """
    Pull out the useful bits from a pipeline if it has a $vectorSearch stage.
    """
    meta: Dict[str, Any] = {}
    if not isinstance(pipeline, list):
        return meta
    for stage in pipeline:
        if isinstance(stage, dict) and "$vectorSearch" in stage and isinstance(stage["$vectorSearch"], dict):
            vs = stage["$vectorSearch"]
            meta["index"] = vs.get("index")
            meta["path"] = vs.get("path")
            meta["limit"] = vs.get("limit")
            meta["numCandidates"] = vs.get("numCandidates")
            # don't print full queryVector
            if "queryVector" in vs:
                qv = vs["queryVector"]
                meta["queryVector_dim"] = len(qv) if isinstance(qv, list) else None
            if "query" in vs:
                meta["query"] = _short(str(vs["query"]), 80)
            break
    return meta

def _pretty_kv(d: Dict[str, Any]) -> str:
    parts = []
    for k, v in d.items():
        if v is None:
            continue
        parts.append(f"{k}={v}")
    return " ".join(parts)

async def mcp_call(session, tool: str, args: Dict[str, Any]) -> Any:
    show = _env("SHOW_TOOLS", "0") == "1"
    dump = _env("DUMP_TOOL_RESULT", "0") == "1"  # set to 1 only when you want raw payloads

    t0 = time.perf_counter()

    if show:
        base = {}
        # common args
        if "database" in args: base["db"] = args.get("database")
        if "collection" in args: base["coll"] = args.get("collection")
        if "filter" in args and tool in ("find", "update-many", "delete-many"):
            base["filter"] = _short(json.dumps(args.get("filter", {}), default=str), 120)

        # aggregation special handling
        if tool == "aggregate" and "pipeline" in args:
            vs_meta = _extract_vectorsearch_meta(args.get("pipeline"))
            if vs_meta:
                base.update({"op": "vectorSearch"})
                base.update(vs_meta)
            else:
                base.update({"op": "aggregate"})

        print(f"[tool→] {tool} {_pretty_kv(base)}", file=sys.stderr, flush=True)

    res = await session.call_tool(tool, args)

    dt_ms = int((time.perf_counter() - t0) * 1000)

    if show:
        # Try to summarize the tool result without dumping everything
        try:
            txt = _tool_result_text(res)  # your existing helper
            summary = _short(txt, 220)
            print(f"[tool←] {tool} {dt_ms}ms result={summary}", file=sys.stderr, flush=True)
            if dump:
                print(f"[tool⇠ raw] {txt}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[tool←] {tool} {dt_ms}ms (could not summarize result: {e})", file=sys.stderr, flush=True)

    return res

# async def mcp_call(session: ClientSession, tool: str, args: Dict[str, Any]) -> Any:
#     if _env("SHOW_TOOLS", "0") == "1":
#         print(f"[tool] {tool} args={list(args.keys())}", file=sys.stderr)
#     return await session.call_tool(tool, args)


async def mcp_aggregate(session: ClientSession, db: str, coll: str, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    res = await mcp_call(session, "aggregate", {"database": db, "collection": coll, "pipeline": pipeline})

    # Prefer parsing each TextContent chunk independently (the MCP server often splits
    # wrapper lines and the actual JSON payload into separate parts).
    try:
        if hasattr(res, "content") and isinstance(res.content, list):
            for item in res.content:
                txt = getattr(item, "text", None)
                if isinstance(txt, str) and txt.strip():
                    docs = _parse_docs(txt)
                    if docs:
                        return docs
    except Exception:
        pass

    return _parse_docs(_tool_result_text(res))



def embed(v: voyageai.Client, model: str, dim: int, text: str) -> List[float]:
    out = v.embed([text], model=model, output_dimension=dim)
    return out.embeddings[0]



@dataclass
class Cfg:
    mcp_url: str
    openai_model: str

    voyage_key: str
    voyage_model: str
    voyage_dim: int

    movies_db: str
    movies_coll: str
    movies_index: str
    movies_embed: str

    mem_db: str
    mem_coll: str
    mem_index: str
    mem_embed: str


async def remember(session: ClientSession, cfg: Cfg, v: voyageai.Client, text: str) -> None:
    vec = embed(v, cfg.voyage_model, cfg.voyage_dim, text)
    doc = {"text": text, "tags": ["user_preference"], "createdAt": _now_iso(), "source": "demo-client", cfg.mem_embed: vec}
    await mcp_call(session, "insert-many", {"database": cfg.mem_db, "collection": cfg.mem_coll, "documents": [doc]})


async def clear_memory(session: ClientSession, cfg: Cfg) -> int:
    res = await mcp_call(session, "delete-many", {"database": cfg.mem_db, "collection": cfg.mem_coll, "filter": {}})
    txt = _tool_result_text(res)
    m = re.search(r"deletedCount['\"]?\s*:\s*(\d+)", txt)
    return int(m.group(1)) if m else 0


# async def retrieve_memory(session: ClientSession, cfg: Cfg, v: voyageai.Client, query: str, k: int = 3) -> List[str]:
#     qvec = embed(v, cfg.voyage_model, cfg.voyage_dim, query)
#     pipeline = [
#         {"$vectorSearch": {"index": cfg.mem_index, "queryVector": qvec, "path": cfg.mem_embed, "numCandidates": max(50, k * 10), "limit": k}},
#         {"$project": {"_id": 0, "text": 1, "score": {"$meta": "vectorSearchScore"}}},
#     ]
#     docs = await mcp_aggregate(session, cfg.mem_db, cfg.mem_coll, pipeline)
#     return [d.get("text", "") for d in docs if isinstance(d, dict) and d.get("text")]

async def retrieve_memory(
    session: ClientSession,
    cfg: Cfg,
    v: voyageai.Client,
    query: str,
    k: int = 3,
) -> List[str]:
    # Embed the *query* locally (Voyage), then use queryVector.
    qvec = embed(v, cfg.voyage_model, cfg.voyage_dim, query)

    pipeline = [
        {
            "$vectorSearch": {
                "index": cfg.mem_index,
                "queryVector": qvec,
                "path": cfg.mem_embed,
                "numCandidates": max(50, k * 10),
                "limit": k,
                # NOTE: no "filter" field here -> no tag filtering
            }
        },
        {"$project": {"_id": 0, "text": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]

    docs = await mcp_aggregate(session, cfg.mem_db, cfg.mem_coll, pipeline)
    return [d.get("text", "") for d in docs if isinstance(d, dict) and d.get("text")]


async def search_movies(session: ClientSession, cfg: Cfg, v: voyageai.Client, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    qvec = embed(v, cfg.voyage_model, cfg.voyage_dim, query)
    pipeline = [
        {"$vectorSearch": {"index": cfg.movies_index, "queryVector": qvec, "path": cfg.movies_embed, "numCandidates": 200, "limit": limit}},
        {"$project": {"_id": 0, "title": 1, "genres": 1, "fullplot": 1, "score": {"$meta": "vectorSearchScore"}}},
    ]
    return await mcp_aggregate(session, cfg.movies_db, cfg.movies_coll, pipeline)


def answer(openai: OpenAI, model: str, user: str, memory: List[str], movies: List[Dict[str, Any]]) -> str:
    mem_block = "\n".join(f"- {m}" for m in memory) if memory else "(none)"
    movie_lines = []
    for m in movies:
        title = m.get("title", "")
        genres = ", ".join(m.get("genres") or [])
        plot = (m.get("fullplot") or "").replace("\n", " ")
        movie_lines.append(f"- {title} | {genres} | {plot[:160]}")
    movie_block = "\n".join(movie_lines) if movie_lines else "(none)"

    prompt = f"""You are a helpful demo assistant.

User request:
{user}

Retrieved user memory (top-k):
{mem_block}

Candidate movies (from vector search):
{movie_block}

Instructions:
- If the user asks for movies/recommendations, output ONLY a bullet list:
  Title — Genres — one sentence why (use query + memory).
- If the user does NOT ask for movies, answer normally and IGNORE the candidate movies list.
- Do not mention tools, databases, MCP, or embeddings.
"""
    r = openai.responses.create(model=model, input=prompt)
    return r.output_text.strip()


async def main() -> None:
    cfg = load_cfg()

    print("\n=== Demo-Grade Agentic AI (OpenAI + MCP + MongoDB / HTTP) ===")
    print("Commands: remember <text> | clear | exit")
    print(f"OpenAI model: {cfg.openai_model}")
    print(f"MCP URL:      {cfg.mcp_url}")
    print(f"Movies:       {cfg.movies_db}.{cfg.movies_coll} (index={cfg.movies_index}, field={cfg.movies_embed})")
    print(f"Memory:       {cfg.mem_db}.{cfg.mem_coll} (index={cfg.mem_index}, field={cfg.mem_embed})")
    print("=============================================================\n")

    openai = OpenAI(api_key=_must("OPENAI_API_KEY"))
    v = voyageai.Client(api_key=cfg.voyage_key)

    session: Optional[ClientSession] = None
    cm = None
    try:
        session, cm = await connect_mcp(cfg.mcp_url)
        tools = await session.list_tools()
        tool_count = len(getattr(tools, "tools", []) or [])
        print(f"✅ MCP ready ({tool_count} tools available)\n")

        while True:
            user = input("> ").strip()
            if not user:
                continue
            low = user.lower()

            if low in ("exit", "quit", "q"):
                break

            if low == "clear":
                n = await clear_memory(session, cfg)
                print(f"[memory] deleted {n} documents\n")
                continue

            if low.startswith("remember "):
                text = user[len("remember "):].strip()
                if not text:
                    print("Usage: remember <text>\n")
                    continue
                await remember(session, cfg, v, text)
                print("[memory] saved\n")
                continue

            memory = await retrieve_memory(session, cfg, v, user, k=3)
            if _env("SHOW_MEMORY", "0") == "1":
                preview = " | ".join(m[:80] for m in memory) if memory else "(none)"
                print(f"[memory] {preview}", file=sys.stderr)

            wants_movies = bool(re.search(r"\b(movie|movies|recommend|similar)\b", user, re.I))
            movies: List[Dict[str, Any]] = []
            if wants_movies:
                movies = await search_movies(session, cfg, v, user, limit=5)

            print(answer(openai, cfg.openai_model, user, memory, movies) + "\n")

    finally:
        try:
            if session is not None:
                await session.__aexit__(None, None, None)
        except Exception:
            pass
        try:
            if cm is not None:
                await cm.__aexit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())