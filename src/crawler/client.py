import asyncio
import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from crawler.concurrency import SemaphoreManager
from crawler.parser import HTMLParser
from crawler.queue import CrawlerQueue

logger = logging.getLogger(__name__)

_VALID_SCHEMES = {"http", "https"}


class AsyncCrawler:
    """Asynchronous HTTP client with bounded concurrency and a shared session."""

    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_host: int = 5,
        max_depth: int = 3,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        user_agent: str = "AsyncCrawler/0.1",
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if max_per_host < 1:
            raise ValueError("max_per_host must be >= 1")
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("timeouts must be positive")

        self._max_concurrent = max_concurrent
        self._max_depth = max_depth
        self._timeout = aiohttp.ClientTimeout(
            connect=connect_timeout,
            sock_read=read_timeout,
        )
        self._headers = {"User-Agent": user_agent}
        self._sem_manager = SemaphoreManager(
            max_concurrent=max_concurrent,
            max_per_host=max_per_host,
        )
        self._session_lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._parser = HTMLParser()

    async def fetch_url(self, url: str) -> str:
        """Download a single URL and return its body as text."""
        session = await self._ensure_session()
        async with self._sem_manager.acquire(url):
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

    async def fetch_and_parse(self, url: str) -> dict:
        """Fetch a URL and parse its HTML body into structured data."""
        html = await self.fetch_url(url)
        return await self._parser.parse_html(html, url)

    async def crawl(
        self,
        start_urls: list[str],
        max_pages: int = 100,
        same_domain_only: bool = False,
        include_patterns: Optional[list[str]] = None,
        exclude_patterns: Optional[list[str]] = None,
    ) -> dict[str, dict]:
        """Crawl pages starting from start_urls, following discovered links.

        Returns {url: parsed_data} for every page successfully fetched and parsed.
        Soft-caps at max_pages (may overshoot by up to max_concurrent due to in-flight tasks).
        """
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")

        queue = CrawlerQueue()
        base_hosts = {urlparse(u).netloc.lower() for u in start_urls}
        include_re = [re.compile(p) for p in (include_patterns or [])]
        exclude_re = [re.compile(p) for p in (exclude_patterns or [])]

        for url in start_urls:
            queue.add_url(url, depth=0)

        done_event = asyncio.Event()
        active = 0
        start_time = time.perf_counter()

        async def worker() -> None:
            nonlocal active
            while not done_event.is_set():
                if queue.get_stats()["processed"] >= max_pages:
                    if active == 0:
                        done_event.set()
                        return
                    await asyncio.sleep(0.05)
                    continue

                url = await queue.get_next()
                if url is None:
                    if active == 0 and queue.empty():
                        done_event.set()
                        return
                    await asyncio.sleep(0.05)
                    continue

                active += 1
                try:
                    try:
                        data = await self.fetch_and_parse(url)
                    except Exception as exc:
                        queue.mark_failed(url, f"{exc.__class__.__name__}: {exc}")
                        continue

                    queue.mark_processed(url, data)

                    depth = queue.get_depth(url)
                    if depth >= self._max_depth:
                        continue
                    if queue.get_stats()["processed"] >= max_pages:
                        continue

                    for link in data["links"]:
                        if not self._should_visit(
                            link, base_hosts, same_domain_only, include_re, exclude_re
                        ):
                            continue
                        queue.add_url(link, depth=depth + 1)
                finally:
                    active -= 1

        async def reporter() -> None:
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    self._log_progress(queue, start_time)
            self._log_progress(queue, start_time, final=True)

        workers = [asyncio.create_task(worker()) for _ in range(self._max_concurrent)]
        progress_task = asyncio.create_task(reporter())

        try:
            await asyncio.gather(*workers)
        finally:
            done_event.set()
            await progress_task

        return dict(queue.processed_urls)

    @staticmethod
    def _should_visit(
        url: str,
        base_hosts: set[str],
        same_domain_only: bool,
        include_re: list[re.Pattern],
        exclude_re: list[re.Pattern],
    ) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in _VALID_SCHEMES or not parsed.netloc:
            return False
        if same_domain_only and parsed.netloc.lower() not in base_hosts:
            return False
        if include_re and not any(rx.search(url) for rx in include_re):
            return False
        if exclude_re and any(rx.search(url) for rx in exclude_re):
            return False
        return True

    def _log_progress(self, queue: CrawlerQueue, start_time: float, final: bool = False) -> None:
        stats = queue.get_stats()
        elapsed = max(time.perf_counter() - start_time, 1e-6)
        rate = stats["processed"] / elapsed
        prefix = "crawl done" if final else "crawl"
        logger.info(
            "%s | processed=%d queued=%d failed=%d active=%d rate=%.1f/s",
            prefix,
            stats["processed"],
            stats["queued"],
            stats["failed"],
            self._sem_manager.active,
            rate,
        )

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
