"""Steady, rate-limited stream of order writes and reads.

Each worker thread loops: pick read or write by READ_RATIO, time the call,
record the outcome. Errors are caught and classified rather than raised, so a
failover shows up as a spike in the metrics instead of killing the generator.

There is no retry loop here on purpose. The driver's own retryable-writes and
retryable-reads machinery does the retrying, and metrics.CommandCounter counts
the extra wire commands it sends, so the retry behaviour on show is the
driver's rather than ours.
"""
import random
import threading
import time
import uuid
from datetime import datetime, timezone

import config
from metrics import STORE
from pymongo.errors import PyMongoError

REGIONS = ("region-a", "region-b", "region-c")
STATUSES = ("created", "paid", "shipped", "cancelled")
ITEMS = ("widget", "gadget", "sprocket", "bracket", "flange")


def make_order() -> dict:
    """A generic synthetic order. No real names, companies, or domains."""
    return {
        "order_id": str(uuid.uuid4()),
        "customer_id": f"customer-{random.randint(1, 500):04d}",
        "region": random.choice(REGIONS),
        "status": random.choice(STATUSES),
        "item": random.choice(ITEMS),
        "quantity": random.randint(1, 5),
        "amount": round(random.uniform(5.0, 500.0), 2),
        "created_at": datetime.now(timezone.utc),
        "source": "resilience-lab",
    }


def _classify(exc: BaseException) -> str:
    """Short, stable label for the /status error breakdown."""
    name = type(exc).__name__
    code = getattr(exc, "code", None)
    return f"{name}({code})" if code else name



class LoadGenerator:
    """Owns the worker threads and the run/pause state exposed over HTTP."""

    def __init__(self):
        self._threads = []
        self._stop = threading.Event()
        self._running = threading.Event()
        self._lock = threading.Lock()
        self._recent_ids = []
        self._recent_lock = threading.Lock()

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            self._running.set()
            if self._threads:
                return
            self._stop.clear()
            for index in range(config.WORKER_COUNT):
                thread = threading.Thread(
                    target=self._loop, args=(index,),
                    name=f"load-{index}", daemon=True,
                )
                thread.start()
                self._threads.append(thread)
        STORE.add_event("load_started",
                        f"{config.WORKER_COUNT} worker(s), target "
                        f"{config.TARGET_OPS_PER_SECOND} ops/s")

    def pause(self) -> None:
        self._running.clear()
        STORE.add_event("load_paused", "workers idle, service still up")

    def resume(self) -> None:
        self.start()
        STORE.add_event("load_resumed", "workers active")

    def shutdown(self) -> None:
        self._stop.set()
        self._running.clear()
        for thread in self._threads:
            thread.join(timeout=2)

    @property
    def running(self) -> bool:
        return self._running.is_set()

    # ── the loop ────────────────────────────────────────────────────────────

    def _interval(self) -> float:
        rate = max(config.TARGET_OPS_PER_SECOND, 0.01)
        return config.WORKER_COUNT / rate

    def _loop(self, index: int) -> None:
        interval = self._interval()
        # Stagger workers so requests spread across the interval.
        time.sleep(interval * index / max(config.WORKER_COUNT, 1))
        while not self._stop.is_set():
            if not self._running.is_set():
                time.sleep(0.2)
                continue
            started = time.perf_counter()
            if random.random() < config.READ_RATIO:
                self._one_op("read", self._do_read, started)
            else:
                self._one_op("write", self._do_write, started)
            elapsed = time.perf_counter() - started
            time.sleep(max(0.0, interval - elapsed))

    def _one_op(self, kind: str, func, started: float) -> None:
        try:
            func()
            STORE.record(kind, (time.perf_counter() - started) * 1000)
        except PyMongoError as exc:
            STORE.record(kind, (time.perf_counter() - started) * 1000,
                         error_type=_classify(exc))
        except Exception as exc:  # noqa: BLE001 — never kill a worker
            STORE.record(kind, (time.perf_counter() - started) * 1000,
                         error_type=_classify(exc))

    def _do_write(self) -> None:
        doc = make_order()
        config.get_orders().insert_one(doc)
        with self._recent_lock:
            self._recent_ids.append(doc["order_id"])
            del self._recent_ids[:-200]

    def _do_read(self) -> None:
        with self._recent_lock:
            order_id = random.choice(self._recent_ids) if self._recent_ids else None
        orders = config.get_orders()
        if order_id:
            orders.find_one({"order_id": order_id})
        else:
            list(orders.find({"region": random.choice(REGIONS)}).limit(10))


GENERATOR = LoadGenerator()
