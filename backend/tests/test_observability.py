"""Observability tests: health probes, metrics exposition, request-id
correlation and structured logging."""

import json

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.logging_config import JsonFormatter
from app.core.metrics import metrics


@pytest.mark.asyncio
async def test_health_live(client: AsyncClient):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["env"] == settings.env


@pytest.mark.asyncio
async def test_health_backward_compatible(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient):
    # Without live Postgres/Redis reachable from the test engine/process the
    # endpoint may degrade; it must still respond with a structured body and a
    # checks map (200 or 503 are both valid depending on availability).
    r = await client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert "checks" in body
    assert set(body["checks"]) == {"database", "redis"}


@pytest.mark.asyncio
async def test_metrics_exposition(client: AsyncClient):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    text = r.text
    assert "# TYPE http_requests_total counter" in text
    assert "http_requests_total " in text
    assert "# TYPE outreach_queue_depth gauge" in text


@pytest.mark.asyncio
async def test_request_id_roundtrip(client: AsyncClient):
    r = await client.get("/health/live", headers={"X-Request-ID": "trace-abc"})
    assert r.headers.get("X-Request-ID") == "trace-abc"


@pytest.mark.asyncio
async def test_request_id_generated_if_absent(client: AsyncClient):
    r = await client.get("/health/live")
    assert r.headers.get("X-Request-ID")


def test_metrics_prometheus_render_includes_worker_counters():
    metrics.reset()
    metrics.inc("outreach_worker_claimed_total", 3)
    text = metrics.render_prometheus()
    assert "# TYPE outreach_worker_claimed_total counter" in text
    assert "outreach_worker_claimed_total 3" in text


def test_json_formatter_emits_request_id():
    import logging

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    from app.core.logging_config import request_id_var

    token = request_id_var.set("req-xyz")
    try:
        line = json.loads(formatter.format(record))
    finally:
        request_id_var.reset(token)
    assert line["message"] == "hello"
    assert line["request_id"] == "req-xyz"
    assert line["level"] == "INFO"