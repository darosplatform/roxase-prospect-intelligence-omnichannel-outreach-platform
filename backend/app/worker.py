"""ROXASE outbox worker — durable asynchronous execution.

Independent process sharing the same database as the API. It is the single
execution authority for queued outreach requests: it claims, leases, processes,
retries with exponential backoff and finally fails/sends items, honoring the
sticky dry-run guard and the global outreach kill switch.

Run:    python -m app.worker            # foreground loop
        SIGTERM / SIGINT              # graceful shutdown after current batch
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import settings
from app.db.session import async_session_factory
from app.services import outbox

logger = logging.getLogger("roxase.worker")


async def _process_poll() -> int:
    """One poll round: claim + process a batch. Returns handles count."""
    async with async_session_factory() as session:
        return await outbox.run_once(session, worker_id=_worker_id())


_worker_id_cache: str | None = None


def _worker_id() -> str:
    global _worker_id_cache
    if _worker_id_cache is None:
        _worker_id_cache = f"worker-{uuid.uuid4().hex[:8]}"
    return _worker_id_cache


async def _run(stop_event: asyncio.Event) -> None:
    logger.info("outbox worker started (id=%s, poll=%.1fs, dry_run=%s, outreach_enabled=%s)",
                _worker_id(), settings.worker_poll_interval, settings.dry_run,
                settings.outreach_enabled)
    while not stop_event.is_set():
        try:
            handled = await _process_poll()
            if handled:
                logger.info("polled %d request(s)", handled)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - loop guards never take the worker down
            logger.exception("worker poll failed; continuing")
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