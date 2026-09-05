"""Minimal, dependency-free metrics registry + Prometheus text renderer.

No prometheus_client dependency: we keep plain in-process counters/gauges and
render the standard Prometheus exposition text format ourselves on `GET
/metrics`. Counters accumulate; gauges hold a snapshot value (e.g. queue depth,
last processing latency). Every metric may carry an optional HELP description.

Metrics are guarded by a lock so concurrent workers can record concurrently.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Metric:
    name: str
    kind: str = "counter"  # "counter" | "gauge"
    help: str = ""
    value: int = 0
    # For derived/observed metrics (e.g. queue depth) a resolver can compute the
    # value lazily at render time instead of being recorded manually.
    resolver: Callable[[], int] | None = field(default=None)

    def resolve(self) -> int:
        if self.resolver is not None:
            return self.resolver()
        return self.value


class Metrics:
    """Debug-safe counter/gauge registry with Prometheus text rendering."""

    def __init__(self) -> None:
        self._metrics: dict[str, Metric] = {}
        self._lock = threading.Lock()

    def register(self, name: str, kind: str = "counter", help: str = "") -> None:
        with self._lock:
            self._metrics.setdefault(name, Metric(name=name, kind=kind, help=help))

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                m = Metric(name=name, kind="counter")
                self._metrics[name] = m
            m.value += value

    def count(self, name: str) -> int:
        with self._lock:
            m = self._metrics.get(name)
            return m.value if m else 0

    def set(self, name: str, value: int, help: str = "") -> None:
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                m = Metric(name=name, kind="gauge", help=help)
                self._metrics[name] = m
            else:
                m.kind = "gauge"
                if help:
                    m.help = help
            m.value = value
            m.resolver = None

    def observe(self, name: str, resolver: Callable[[], int], help: str = "") -> None:
        """Bind a lazy gauge that computes its value at render time."""
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                m = Metric(name=name, kind="gauge", help=help)
                self._metrics[name] = m
            else:
                m.kind = "gauge"
                if help:
                    m.help = help
            m.resolver = resolver

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {n: m.resolve() for n, m in self._metrics.items()}

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()

    # ------------------------------------------------------------------ #
    # Prometheus text exposition
    # ------------------------------------------------------------------ #
    def render_prometheus(self) -> str:
        with self._lock:
            items = list(self._metrics.items())
        lines: list[str] = []
        for name, metric in sorted(items):
            value = metric.resolve()
            if metric.help:
                lines.append(f"# HELP {name} {metric.help}")
            lines.append(f"# TYPE {name} {metric.kind}")
            lines.append(f"{name} {value}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
metrics.register("outreach_worker_claimed_total", "counter", "Total requests claimed by workers")
metrics.register("outreach_worker_dispatched_total", "counter", "Total requests dispatched")
metrics.register("outreach_worker_failed_total", "counter", "Total requests failed")
metrics.register("outreach_worker_retried_total", "counter", "Total requests scheduled for retry")
metrics.register("outreach_worker_recovered_total", "counter", "Total recovered leases")
metrics.register("outreach_worker_sent_total", "counter", "Total sent")
metrics.register("outreach_worker_simulated_total", "counter", "Total simulated sends")
metrics.register("outreach_queue_depth", "gauge", "Queued/claimable")

# Observed at render time by the queue-depth resolver bound from the app.
metrics.register("outreach_processing_latency_seconds_last", "gauge", "Last worker latency (s)")
metrics.register("http_requests_total", "counter", "Total HTTP requests handled")
metrics.register("http_requests_client_errors_total", "counter", "HTTP 4xx responses")
metrics.register("http_requests_server_errors_total", "counter", "HTTP 5xx responses")
metrics.register("http_in_flight", "gauge", "HTTP requests currently in flight")

metrics.register("discovery_jobs_total", "counter", "Total discovery jobs created")
metrics.register("discovery_jobs_failed_total", "counter", "Discovery jobs that ended failed")
metrics.register("discovery_fetch_total", "counter", "Total secure-fetch attempts")
metrics.register(
    "discovery_fetch_blocked_ssrf_total", "counter", "Fetches blocked by SSRF safety checks"
)
metrics.register(
    "discovery_fetch_failed_total", "counter", "Fetches that failed for a non-SSRF reason"
)
metrics.register(
    "discovery_fetch_succeeded_total", "counter", "Fetches that produced a RawDocument"
)
metrics.register("discovery_fetch_latency_ms_last", "gauge", "Last secure-fetch latency (ms)")
metrics.register("discovery_documents_total", "counter", "Total RawDocuments stored")
metrics.register("discovery_worker_claimed_total", "counter", "Total discovery jobs claimed")
metrics.register(
    "discovery_worker_recovered_total", "counter", "Discovery jobs recovered from an expired lease"
)
metrics.register(
    "discovery_worker_retried_total", "counter", "Discovery jobs scheduled for retry"
)


def set_processing_latency(seconds: float) -> None:
    """Record last worker processing latency as a gauge (integer centiseconds)."""
    metrics.set("outreach_processing_latency_seconds_last", int(seconds * 100))