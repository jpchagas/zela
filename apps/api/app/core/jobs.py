"""Seam between request handlers and background workers.

Handlers publish only IDs of rows already committed, so a lost publish is recovered by
the sweeper (app.workers.sweep) re-queuing rows still in `received`. Pub/Sub push
delivery replaces the inline publisher with the deployment milestone.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class JobPublisher(Protocol):
    def publish(self, topic: str, payload: dict[str, str]) -> None: ...


class LoggingPublisher:
    """Records what would be published; nothing runs."""

    def publish(self, topic: str, payload: dict[str, str]) -> None:
        logger.info("job published", extra={"topic": topic, "payload": payload})


class InlinePublisher:
    """Runs jobs on a small thread pool in this process, after the response is sent."""

    def __init__(self, max_workers: int = 4):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="jobs")

    def publish(self, topic: str, payload: dict[str, str]) -> None:
        from app.workers.runner import HANDLERS

        handler = HANDLERS[topic]
        future = self._pool.submit(handler, payload)
        future.add_done_callback(_log_failure(topic, payload))


def _log_failure(topic: str, payload: dict[str, str]):
    def callback(future) -> None:
        if (exc := future.exception()) is not None:
            logger.error("job failed", exc_info=exc, extra={"topic": topic, "payload": payload})

    return callback


@lru_cache
def get_job_publisher() -> JobPublisher:
    if get_settings().jobs_mode == "inline":
        return InlinePublisher()
    return LoggingPublisher()
