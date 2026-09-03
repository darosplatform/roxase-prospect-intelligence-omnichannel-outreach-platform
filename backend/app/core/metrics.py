"""Minimal, dependency-free metrics registry for the outbox worker.

Counters are plain in-process integers guarded by a lock so concurrent workers
can record concurrently. The registry is intentionally simple for V1: no
Prometheus/Kafka dependency. A future observability chantier can attach an
exporter on top of this same registry.
"""

from __future__ import annotations

import threading


class Metrics:
    """Thread-safe counter registry exposing a small subset of Prometheus-like ops."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def count(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def set(self, name: str, value: int) -> None:
        with self._lock:
            self._counters[name] = value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


metrics = Metrics()