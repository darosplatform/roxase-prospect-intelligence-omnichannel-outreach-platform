"""App-level HTTP request statistics folded into the metrics registry.

Kept separate from the low-level outbox worker metrics so `/metrics` can cheaply
expose request totals / error rates without polling external systems. Counters
are folded incrementally (delta since last render) so they remain monotonic.
"""

from __future__ import annotations

import threading

_requests_total = 0
_requests_4xx = 0
_requests_5xx = 0
_in_flight = 0
_lock = threading.Lock()

_prev_total = 0
_prev_4xx = 0
_prev_5xx = 0


def record(status_code: int) -> None:
    global _requests_total, _requests_4xx, _requests_5xx
    with _lock:
        _requests_total += 1
        if 400 <= status_code < 500:
            _requests_4xx += 1
        elif status_code >= 500:
            _requests_5xx += 1


def record_in_flight(delta: int) -> None:
    global _in_flight
    with _lock:
        _in_flight += delta


def fold_into(metrics) -> None:
    global _prev_total, _prev_4xx, _prev_5xx
    with _lock:
        delta_total = _requests_total - _prev_total
        delta_4xx = _requests_4xx - _prev_4xx
        delta_5xx = _requests_5xx - _prev_5xx
        _prev_total = _requests_total
        _prev_4xx = _requests_4xx
        _prev_5xx = _requests_5xx
        in_flight = _in_flight
    metrics.inc("http_requests_total", delta_total)
    metrics.inc("http_requests_client_errors_total", delta_4xx)
    metrics.inc("http_requests_server_errors_total", delta_5xx)
    metrics.set("http_in_flight", in_flight)