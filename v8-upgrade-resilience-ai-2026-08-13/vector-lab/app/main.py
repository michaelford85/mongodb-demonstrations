"""DocsCo knowledge base search — a FastAPI app that runs one query three ways.

    python app/main.py                                  # reads HOST/PORT
    uvicorn main:app --app-dir app --host 127.0.0.1 --port 8001

Endpoints:

    GET  /                 the comparison UI
    GET  /api/search       JSON: ?q=...&mode=keyword|vector|rerank|all
    GET  /api/config       what the lab is configured to use
    GET  /health           service and cluster liveness
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))

import config  # noqa: E402
import rerank as rerank_mod  # noqa: E402
import search  # noqa: E402
import topics  # noqa: E402
from fastapi import FastAPI, Query, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

app = FastAPI(title="DocsCo knowledge base search — vector lab")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["tojson_pretty"] = lambda v: json.dumps(v, indent=2)


def _lab_config() -> dict:
    return {
        "namespace": config.namespace(),
        "embedding_provider": config.EMBEDDING_PROVIDER,
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_dim": config.EMBEDDING_DIM,
        "rerank_backend": rerank_mod.backend(),
        "rerank_model": config.RERANK_MODEL,
        "text_index": config.TEXT_INDEX,
        "vector_index": config.VECTOR_INDEX,
        "result_limit": config.RESULT_LIMIT,
        "rerank_candidates": config.RERANK_CANDIDATES,
    }


def _run_modes(query: str, modes: list) -> tuple:
    """Run each mode, capturing per-mode failures so one broken index does not
    take the whole comparison down."""
    panels, errors = [], []
    for mode in modes:
        try:
            panels.append(search.run(mode, query))
        except PyMongoError as exc:
            errors.append({"mode": mode, "error": type(exc).__name__,
                           "detail": str(exc)[:300]})
        except (RuntimeError, ValueError) as exc:
            errors.append({"mode": mode, "error": type(exc).__name__,
                           "detail": str(exc)[:300]})
    return panels, errors


@app.get("/")
def index(request: Request,
          q: str = Query(default=""),
          mode: str = Query(default="all")) -> object:
    query = q.strip()
    modes = list(search.MODES) if mode == "all" else [mode]
    panels, errors = _run_modes(query, modes) if query else ([], [])
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "query": query,
            "mode": mode,
            "modes": search.MODES,
            "panels": panels,
            "errors": errors,
            "examples": topics.EXAMPLE_QUERIES,
            "lab": _lab_config(),
            "show_pipeline": config.SHOW_PIPELINE,
        },
    )


@app.get("/api/search")
def api_search(q: str = Query(...), mode: str = Query(default="all")) -> JSONResponse:
    query = q.strip()
    if not query:
        return JSONResponse(status_code=400, content={"error": "q is required"})
    if mode != "all" and mode not in search.MODES:
        return JSONResponse(
            status_code=400,
            content={"error": f"mode must be 'all' or one of {list(search.MODES)}"},
        )
    modes = list(search.MODES) if mode == "all" else [mode]
    panels, errors = _run_modes(query, modes)
    return JSONResponse(content={"query": query, "results": panels,
                                 "errors": errors, "config": _lab_config()})


@app.get("/api/config")
def api_config() -> dict:
    return _lab_config()


@app.get("/health")
def health() -> JSONResponse:
    try:
        config.get_client().admin.command("ping")
        cluster = "reachable"
        code = 200
    except PyMongoError as exc:
        cluster = f"unreachable: {type(exc).__name__}"
        code = 503
    return JSONResponse(status_code=code,
                        content={"service": "up", "cluster": cluster})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
