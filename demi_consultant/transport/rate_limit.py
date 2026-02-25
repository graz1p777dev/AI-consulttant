from __future__ import annotations

from dataclasses import dataclass
import math
import threading
from time import time


@dataclass(frozen=True)
class RateLimitVerdict:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter:
    """Thread-safe per-user cooldown limiter shared across all channels."""

    def __init__(self, interval_seconds: int = 8) -> None:
        self._interval_seconds = interval_seconds
        self._next_allowed_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, user_id: str, event_ts: float | None = None) -> RateLimitVerdict:
        now = event_ts if event_ts is not None else time()
        with self._lock:
            next_allowed = self._next_allowed_at.get(user_id, 0.0)
            if now < next_allowed:
                retry_after = max(1, int(math.ceil(next_allowed - now)))
                return RateLimitVerdict(allowed=False, retry_after_seconds=retry_after)

            self._next_allowed_at[user_id] = now + self._interval_seconds
            return RateLimitVerdict(allowed=True)
