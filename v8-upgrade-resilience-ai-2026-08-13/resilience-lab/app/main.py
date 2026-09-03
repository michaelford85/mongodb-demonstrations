"""Orders service — a FastAPI app that keeps talking to MongoDB while you
break things underneath it.

    python app/main.py                                  # reads HOST/PORT
    uvicorn main:app --app-dir app --host 127.0.0.1 --port 8000

Endpoints:

    GET  /status    metrics over the last N seconds, plus topology events
    GET  /health    liveness of the service and of the cluster ping
    GET  /topology  what the driver currently believes about the replica set
    POST /load/pause, /load/resume   stop and start the generator
    POST /orders    write one order on demand
"""
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
import metrics  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402
from workload import GENERATOR, make_order  # noqa: E402

metrics.register_listeners()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.get_client()  # fail fast on a missing or unusable MONGODB_URI
    if config.AUTOSTART:
        GENERATOR.start()
    yield
    GENERATOR.shutdown()


app = FastAPI(title="orders service — resilience lab", lifespan=lifespan)


def _topology() -> dict:
    """Read the driver's own view; no command is sent to the cluster."""
    description = config.get_client().topology_description
    servers = [
        {
            "address": f"{s.address[0]}:{s.address[1]}",
            "type": s.server_type_name,
            "round_trip_time_ms": round(s.round_trip_time * 1000, 1)
            if s.round_trip_time else None,
        }
        for s in description.server_descriptions().values()
    ]
    return {
        "topology_type": description.topology_type_name,
        "replica_set_name": description.replica_set_name,
        "servers": sorted(servers, key=lambda s: s["address"]),
    }


@app.get("/status")
def status() -> dict:
    snapshot = metrics.STORE.snapshot()
    snapshot["load"] = {
        "running": GENERATOR.running,
        "workers": config.WORKER_COUNT,
        "target_ops_per_second": config.TARGET_OPS_PER_SECOND,
        "read_ratio": config.READ_RATIO,
    }
    snapshot["driver_options"] = config.client_options()
    snapshot["namespace"] = f"{config.DB_NAME}.{config.ORDERS_COLLECTION}"
    try:
        snapshot["topology"] = _topology()
    except PyMongoError as exc:
        snapshot["topology"] = {"error": type(exc).__name__}
    return snapshot


@app.get("/health")
def health() -> JSONResponse:
    try:
        config.get_client().admin.command("ping")
        cluster = "reachable"
        code = 200
    except PyMongoError as exc:
        cluster = f"unreachable: {type(exc).__name__}"
        code = 503
    return JSONResponse(
        status_code=code,
        content={"service": "up", "cluster": cluster,
                 "load_running": GENERATOR.running},
    )


@app.get("/topology")
def topology() -> dict:
    return _topology()


@app.post("/load/pause")
def load_pause() -> dict:
    GENERATOR.pause()
    return {"load_running": GENERATOR.running}


@app.post("/load/resume")
def load_resume() -> dict:
    GENERATOR.resume()
    return {"load_running": GENERATOR.running}


@app.post("/orders")
def create_order() -> JSONResponse:
    """One write on demand — handy for probing during a step-down."""
    doc = make_order()
    try:
        config.get_orders().insert_one(doc)
    except PyMongoError as exc:
        return JSONResponse(
            status_code=503,
            content={"written": False, "error": type(exc).__name__,
                     "detail": str(exc)[:200]},
        )
    return JSONResponse(
        status_code=201,
        content={"written": True, "order_id": doc["order_id"]},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)
