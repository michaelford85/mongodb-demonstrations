"""The model behind the agent: openai, anthropic, or a local rule-based stand-in.

`complete(system, messages)` returns raw text. The agent asks for JSON and
parses it, so any provider that can follow a format instruction works.

The offline provider is not a language model. It is a small rule-based planner
in offline_planner.py that reads the same prompt and emits the same JSON. It
exists so the agent loop, the tool dispatch, and the session memory can all be
demonstrated with no key and no network — and so a workshop can be interrupted
without a bill.
"""
import json
import re
import time

import config
import offline_planner

_openai = None
_anthropic = None


def provider() -> str:
    return config.LLM_PROVIDER


def is_offline() -> bool:
    return config.LLM_PROVIDER == "offline"


def describe() -> str:
    if is_offline():
        return "offline rule-based planner (no LLM calls)"
    return f"{config.LLM_PROVIDER} / {config.LLM_MODEL}"


def _get_openai():
    global _openai
    if _openai is None:
        from openai import OpenAI

        key = config.llm_api_key()
        if not key:
            raise RuntimeError("LLM_API_KEY is required for LLM_PROVIDER=openai")
        kwargs = {"api_key": key}
        if config.LLM_BASE_URL:
            kwargs["base_url"] = config.LLM_BASE_URL
        _openai = OpenAI(**kwargs)
    return _openai


def _get_anthropic():
    global _anthropic
    if _anthropic is None:
        import anthropic

        key = config.llm_api_key()
        if not key:
            raise RuntimeError(
                "LLM_API_KEY is required for LLM_PROVIDER=anthropic")
        kwargs = {"api_key": key}
        if config.LLM_BASE_URL:
            kwargs["base_url"] = config.LLM_BASE_URL
        _anthropic = anthropic.Anthropic(**kwargs)
    return _anthropic


def complete(system: str, messages: list) -> str:
    """One completion. `messages` is [{"role": "user"|"assistant", ...}, ...]."""
    if is_offline():
        return offline_planner.complete(system, messages)

    for attempt in range(4):
        try:
            if config.LLM_PROVIDER == "openai":
                resp = _get_openai().chat.completions.create(
                    model=config.LLM_MODEL,
                    temperature=config.LLM_TEMPERATURE,
                    max_tokens=config.LLM_MAX_TOKENS,
                    messages=[{"role": "system", "content": system}] + messages,
                )
                return resp.choices[0].message.content or ""
            if config.LLM_PROVIDER == "anthropic":
                resp = _get_anthropic().messages.create(
                    model=config.LLM_MODEL,
                    temperature=config.LLM_TEMPERATURE,
                    max_tokens=config.LLM_MAX_TOKENS,
                    system=system,
                    messages=messages,
                )
                return "".join(block.text for block in resp.content
                               if getattr(block, "type", "") == "text")
            raise RuntimeError(
                f"unknown LLM_PROVIDER '{config.LLM_PROVIDER}'; expected "
                f"openai, anthropic or offline")
        except Exception as exc:  # noqa: BLE001 — retry transient limits only
            transient = any(s in str(exc).lower()
                            for s in ("rate", "overloaded", "timeout", "503"))
            if transient and attempt < 3:
                wait = 2 ** attempt * 3
                print(f"  Model unavailable, retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Exceeded model retries")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def complete_json(system: str, messages: list) -> dict:
    """Ask for JSON and parse it, tolerating a code fence or surrounding prose.

    Models wrap JSON in fences or add a sentence either side often enough that
    handling it here is cheaper than re-prompting.
    """
    raw = complete(system, messages).strip()

    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"model did not return JSON: {raw[:300]}")
