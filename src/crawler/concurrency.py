import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SemaphoreManager:
    """Combines a global concurrency limit with a per-host limit."""

    def __init__(self, max_concurrent: int = 10, max_per_host: int = 5) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if max_per_host < 1:
            raise ValueError("max_per_host must be >= 1")

        self._max_concurrent = max_concurrent
        self._max_per_host = max_per_host
        self._global = asyncio.Semaphore(max_concurrent)
        self._per_host: dict[str, asyncio.Semaphore] = {}
        self._active = 0

    @asynccontextmanager
    async def acquire(self, url: str):
        host = self._host_of(url)
        host_sem = self._get_host_sem(host)
        async with self._global:
            async with host_sem:
                self._active += 1
                try:
                    yield
                finally:
                    self._active -= 1

    @property
    def active(self) -> int:
        return self._active

    def _get_host_sem(self, host: str) -> asyncio.Semaphore:
        sem = self._per_host.get(host)
        if sem is None:
            sem = asyncio.Semaphore(self._max_per_host)
            self._per_host[host] = sem
        return sem

    @staticmethod
    def _host_of(url: str) -> str:
        return urlparse(url).netloc.lower()
