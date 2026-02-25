from __future__ import annotations

import atexit
import os
from pathlib import Path
from typing import TextIO

from demi_consultant.core.exceptions import ProcessLockError

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


class ProcessLock:
    """Best-effort single process lock for each running adapter."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        if fcntl is None:  # pragma: no cover
            return

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise ProcessLockError(
                f"Lock is already held by another process: {self._lock_path}"
            ) from exc

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        atexit.register(self.release)

    def release(self) -> None:
        if self._handle is None:
            return

        if fcntl is not None:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass

        try:
            self._handle.close()
        except OSError:
            pass
        finally:
            self._handle = None
