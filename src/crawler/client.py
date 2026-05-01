import asyncio
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class AsyncCrawler:
    """Asynchronous HTTP client with bounded concurrency and a shared session."""

    def __init__(
        self,
        max_concurrent: int = 10,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        user_agent: str = "AsyncCrawler/0.1",
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("timeouts must be positive")

        self._max_concurrent = max_concurrent
        self._timeout = aiohttp.ClientTimeout(
            connect=connect_timeout,
            sock_read=read_timeout,
        )
        self._headers = {"User-Agent": user_agent}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session_lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None

    async def fetch_url(self, url: str) -> str:
        """Download a single URL and return its body as text."""
        session = await self._ensure_session()
        async with self._semaphore:
            logger.info("GET %s", url)
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    text = await response.text()
            except asyncio.TimeoutError:
                logger.warning("Timeout: %s", url)
                raise
            except aiohttp.ClientResponseError as exc:
                logger.warning("HTTP %s: %s", exc.status, url)
                raise
            except aiohttp.ClientError as exc:
                logger.warning("Client error: %s (%s)", url, exc.__class__.__name__)
                raise
            logger.info("OK %s (%d bytes)", url, len(text))
            return text

    async def fetch_urls(self, urls: list[str]) -> dict[str, str]:
        """Download URLs concurrently. Failed URLs are omitted from the result."""
        tasks = [asyncio.create_task(self.fetch_url(url)) for url in urls]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            url: outcome
            for url, outcome in zip(urls, outcomes)
            if isinstance(outcome, str)
        }

    async def close(self) -> None:
        """Close the underlying HTTP session if it is open."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "AsyncCrawler":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        async with self._session_lock:
            if self._session is None or self._session.closed:
                connector = aiohttp.TCPConnector(limit=self._max_concurrent)
                self._session = aiohttp.ClientSession(
                    timeout=self._timeout,
                    connector=connector,
                    headers=self._headers,
                )
            return self._session
