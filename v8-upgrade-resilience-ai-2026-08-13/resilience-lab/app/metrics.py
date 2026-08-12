"""Rolling metrics window plus a driver topology event log.

Two things are recorded:

* every completed operation (kind, latency, outcome, whether the driver
  retried it), kept in a deque trimmed to METRICS_WINDOW_SECONDS;
* every SDAM topology change the driver reports, so a step-down is visible as
  a timestamped event rather than only as a latency bump.

Counters are cumulative since process start; rates and percentiles are
computed over the window only.
"""
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone

import config
from pymongo import monitoring


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class MetricsStore:
    """Thread-safe. Every load-generator worker writes into one instance."""

    def __init__(self, window_seconds: int, event_log_size: int):
        self._lock = threading.Lock()
        self._window = window_seconds
        self._samples = deque()  # (monotonic_ts, kind, latency_ms, error_type)
        self._events = deque(maxlen=event_log_size)
        self._first_sample_at = None
        self.started_at = _now_iso()
        self.totals = Counter()
        self.errors_by_type = Counter()
        self.last_error = None

    # ── recording ───────────────────────────────────────────────────────────

    def record(self, kind: str, latency_ms: float, error_type: str = None) -> None:
        with self._lock:
            now = time.monotonic()
            if self._first_sample_at is None:
                self._first_sample_at = now
            self._samples.append((now, kind, latency_ms, error_type))
            self.totals[f"{kind}_attempted"] += 1
            if error_type:
                self.totals[f"{kind}_failed"] += 1
                self.errors_by_type[error_type] += 1
                self.last_error = {"at": _now_iso(), "kind": kind,
                                   "type": error_type}
            else:
                self.totals[f"{kind}_succeeded"] += 1
            self._trim()

    def bump(self, counter: str) -> None:
        with self._lock:
            self.totals[counter] += 1

    def add_event(self, kind: str, detail: str) -> None:
        with self._lock:
            self._events.appendleft({"at": _now_iso(), "event": kind,
                                     "detail": detail})

    def _trim(self) -> None:
        cutoff = time.monotonic() - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    # ── reporting ───────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        with self._lock:
            self._trim()
            samples = list(self._samples)
            totals = dict(self.totals)
            errors = dict(self.errors_by_type)
            events = list(self._events)
            last_error = self.last_error
            first_at = self._first_sample_at

        # Divide by elapsed time, not the nominal window, so the first N
        # seconds after startup do not under-report the rate.
        elapsed = self._window
        if first_at is not None:
            elapsed = min(self._window, max(time.monotonic() - first_at, 0.001))

        window = {"window_seconds": self._window,
                  "measured_seconds": round(elapsed, 1),
                  "operations": len(samples)}
        window["ops_per_second"] = round(len(samples) / elapsed, 2)
        for kind in ("write", "read"):
            of_kind = [s for s in samples if s[1] == kind]
            latencies = sorted(s[2] for s in of_kind if s[3] is None)
            failed = sum(1 for s in of_kind if s[3] is not None)
            window[kind] = {
                "operations": len(of_kind),
                "ops_per_second": round(len(of_kind) / elapsed, 2),
                "errors": failed,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 1)
                if latencies else None,
                "p95_latency_ms": _percentile(latencies, 0.95),
                "max_latency_ms": round(max(latencies), 1) if latencies else None,
            }
        window["errors"] = sum(1 for s in samples if s[3] is not None)
        window["error_rate"] = (round(window["errors"] / len(samples), 4)
                                if samples else 0.0)

        totals.setdefault("driver_retries", 0)

        return {
            "started_at": self.started_at,
            "window": window,
            "totals": totals,
            "errors_by_type": errors,
            "last_error": last_error,
            "topology_events": events,
        }


def _percentile(sorted_values: list, fraction: float):
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1,
                int(round(fraction * (len(sorted_values) - 1))))
    return round(sorted_values[index], 1)


STORE = MetricsStore(config.METRICS_WINDOW_SECONDS, config.EVENT_LOG_SIZE)


class TopologyLogger(monitoring.TopologyListener):
    """Records replica set membership and primary changes as they happen."""

    def opened(self, event):
        STORE.add_event("topology_opened", str(event.topology_id))

    def closed(self, event):
        STORE.add_event("topology_closed", str(event.topology_id))

    def description_changed(self, event):
        old, new = event.previous_description, event.new_description
        if old.topology_type != new.topology_type:
            STORE.add_event(
                "topology_type_changed",
                f"{old.topology_type_name} -> {new.topology_type_name}",
            )
        old_primary = [s.address for s in old.server_descriptions().values()
                       if s.server_type_name == "RSPrimary"]
        new_primary = [s.address for s in new.server_descriptions().values()
                       if s.server_type_name == "RSPrimary"]
        if old_primary != new_primary:
            STORE.add_event(
                "primary_changed",
                f"{_hosts(old_primary) or 'none'} -> "
                f"{_hosts(new_primary) or 'none'}",
            )


def _hosts(addresses: list) -> str:
    return ", ".join(f"{host}:{port}" for host, port in addresses)


class CommandCounter(monitoring.CommandListener):
    """Counts the retries the driver performs on the workload's behalf.

    `operation_id` cannot be used for this: for ordinary reads and writes
    PyMongo publishes command events without an explicit operation id, so it
    falls back to `request_id`, which is fresh for every attempt. What is
    stable is the thread — retryable-writes and retryable-reads re-issue the
    command from the same thread that ran the first attempt. So a retryable
    command failure arms a per-thread flag, and the next watched command
    started on that thread is the driver's retry.

    Only the workload's own commands are watched; heartbeats, pings and index
    builds are ignored.
    """

    WATCHED = {"insert", "find", "update", "findAndModify"}

    def __init__(self):
        self._pending = threading.local()

    def _armed(self) -> str:
        return getattr(self._pending, "command", None)

    def started(self, event):
        if event.command_name not in self.WATCHED:
            return
        STORE.bump("wire_commands")
        armed = self._armed()
        # Consume the flag either way, so a command the driver gave up on
        # cannot be mistaken for a retry of the next operation.
        self._pending.command = None
        if armed == event.command_name:
            STORE.bump("driver_retries")
            STORE.add_event("driver_retry",
                            f"{event.command_name} retried by the driver")

    def succeeded(self, event):
        if event.command_name in self.WATCHED:
            self._pending.command = None

    def failed(self, event):
        if event.command_name not in self.WATCHED:
            return
        STORE.bump("wire_command_failures")
        if _is_retryable(event.failure):
            self._pending.command = event.command_name
        else:
            self._pending.command = None


# From the retryable reads/writes specs: either the server labels the error
# retryable, or its code is one the driver treats as retryable.
RETRYABLE_LABELS = frozenset(["RetryableWriteError", "RetryableReadError"])
RETRYABLE_CODES = frozenset([
    6,      # HostUnreachable
    7,      # HostNotFound
    89,     # NetworkTimeout
    91,     # ShutdownInProgress
    134,    # ReadConcernMajorityNotAvailableYet
    189,    # PrimarySteppedDown
    262,    # ExceededTimeLimit
    9001,   # SocketException
    10107,  # NotWritablePrimary
    11600,  # InterruptedAtShutdown
    11602,  # InterruptedDueToReplStateChange
    13435,  # NotPrimaryNoSecondaryOk
    13436,  # NotPrimaryOrSecondary
])


def _is_retryable(failure) -> bool:
    if not isinstance(failure, dict):
        return False
    if RETRYABLE_LABELS.intersection(failure.get("errorLabels") or ()):
        return True
    return failure.get("code") in RETRYABLE_CODES


_registered = False


def register_listeners() -> None:
    """Register monitoring globally; must run before the client is built."""
    global _registered
    if not _registered:
        monitoring.register(TopologyLogger())
        monitoring.register(CommandCounter())
        _registered = True
