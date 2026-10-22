"""Seam between request handlers and background workers.

Production publishes to Pub/Sub (Milestone 2). Handlers only publish IDs of rows already
committed, so a lost publish can be recovered by re-sweeping rows still in `received`.
"""

import logging
from functools import lru_cache
from typing import Protocol

logger = logging.getLogger(__name__)


class JobPublisher(Protocol):
    def publish(self, topic: str, payload: dict[str, str]) -> None: ...


class LoggingPublisher:
    """Local stand-in: records what would be published."""

    def publish(self, topic: str, payload: dict[str, str]) -> None:
        logger.info("job published", extra={"topic": topic, "payload": payload})


@lru_cache
def get_job_publisher() -> JobPublisher:
    return LoggingPublisher()
