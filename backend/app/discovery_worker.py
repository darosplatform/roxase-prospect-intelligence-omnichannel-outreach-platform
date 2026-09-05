"""ROXASE discovery worker — durable asynchronous execution for DiscoveryJobs.

Independent process sharing the same database as the API and the outreach
worker. It is the single execution authority for `queued` discovery jobs:
claims, leases, walks each pending source through fetch -> extract ->
detect-signal, retries transient worker faults with exponential backoff, and
finally reaches `done`/`failed`. Structurally identical to `app/worker.py`
(same signal handling, same graceful-shutdown pattern) so operators only
need to learn one worker shape.

Run:    python -m app.discovery_worker
        SIGTERM / SIGINT              # graceful shutdown after current batch
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import settings
from app.db.session import async_session_factory
from app.services import discovery_worker as engine

logger = logging.getLogger("roxase.discovery_worker.main")

_worker_id_cache: str | None = None


def _worker_id() -> str:
    global _worker_id_cache
    if _worker_id_cache is None:
        _worker_id_cache = f"discovery-worker-{uuid.uuid4().hex[:8]}"
    return _worker_id_cache


async def _process_poll() -> int:
    async with async_session_factory() as session:
        return await engine.run_once(session, worker_id=_worker_id())


async def _run(stop_event: asyncio.Event) -> None:
    logger.info(
        "discovery worker started (id=%s, poll=%.1fs)", _worker_id(), settings.worker_poll_interval
    )
    while not stop_event.is_set():
        try:
            handled = await _process_poll()
            if handled:
                logger.info("polled %d discovery job(s)", handled)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - loop guards never take the worker down
            logger.exception("discovery worker poll failed; continuing")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.worker_poll_interval)
        except TimeoutError:
            pass


def main() -> None:
    logging.basicConfig(level=settings.log_level.upper())
    stop_event = asyncio.Event()

    def _signal(*_args) -> None:
        logger.info("shutdown signal received; draining current batch")
        stop_event.set()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in ("SIGTERM", "SIGINT"):
        try:
            loop.add_signal_handler(getattr(__import__("signal"), sig), _signal)
        except (NotImplementedError, AttributeError):  # pragma: no cover
            pass
    try:
        loop.run_until_complete(_run(stop_event))
    finally:
        loop.close()


if __name__ == "__main__":
    main()
