from __future__ import annotations

import logging
import sys
from time import perf_counter


class _DefaultContextFilter(logging.Filter):
    """Guarantees context fields are present for every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "channel"):
            record.channel = "-"
        if not hasattr(record, "user_id"):
            record.user_id = "-"
        if not hasattr(record, "latency_ms"):
            record.latency_ms = "-"
        return True


def configure_logging(debug: bool) -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.addFilter(_DefaultContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | "
            "channel=%(channel)s user=%(user_id)s latency_ms=%(latency_ms)s | %(message)s"
        )
    )

    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)


def mask_user_id(user_id: str | None) -> str:
    if not user_id:
        return "-"
    value = str(user_id)
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def latency_ms(started_at: float | None) -> str:
    if started_at is None:
        return "-"
    elapsed = int((perf_counter() - started_at) * 1000)
    return str(max(elapsed, 0))


def log_extra(*, channel: str, user_id: str | None = None, started_at: float | None = None) -> dict[str, str]:
    return {
        "channel": channel,
        "user_id": mask_user_id(user_id),
        "latency_ms": latency_ms(started_at),
    }
