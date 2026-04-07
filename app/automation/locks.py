"""Simple file-based locking to prevent overlapping automation runs."""

from __future__ import annotations

import fcntl
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class FileLock:
    """Non-blocking file lock for single-machine job deduplication.

    Uses fcntl.flock which is released automatically when the process exits
    or the file descriptor is closed.
    """

    def __init__(self, lock_dir: Path, name: str):
        self._lock_dir = lock_dir
        self._name = name
        self._lock_path = lock_dir / f".{name}.lock"
        self._fd: int | None = None

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True on success, False if already held."""
        self._lock_dir.mkdir(parents=True, exist_ok=True)
        fd: int | None = None
        try:
            fd = os.open(str(self._lock_path), os.O_CREAT | os.O_RDWR)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, f"{os.getpid()}:{time.time()}\n".encode())
            self._fd = fd
            return True
        except (OSError, BlockingIOError):
            logger.debug("Lock '%s' already held", self._name)
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Could not acquire lock '{self._name}'")
        return self

    def __exit__(self, *exc):
        self.release()

    def __del__(self):
        self.release()
