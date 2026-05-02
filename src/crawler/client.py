import asyncio
import logging
import random
import re
import time
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from crawler.concurrency import SemaphoreManager
from crawler.parser import HTMLParser
from crawler.queue import CrawlerQueue
from crawler.rate_limiter import RateLimiter
from crawler.robots import RobotsBlocked, RobotsParser

logger = logging.getLogger(__name__)

_VALID_SCHEMES = {"http", "https"}


class AsyncCrawler:
    """Asynchronous web crawler: HTTP client, HTML parser, BFS traversal with priority
    queue, semaphore-based concurrency control, rate limiting, and robots.txt enforcement.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_per_host: int = 5,
        max_depth: int = 3,
        requests_per_second: Optional[float] = None,
        min_delay: float = 0.0,
        jitter: float = 0.0,
        respect_robots: bool = False,
        max_retries: int = 0,
        backoff_base: float = 1.0,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        user_agent: "str | list[str]" = "AsyncCrawler/0.1",
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if max_per_host < 1:
            raise ValueError("max_per_host must be >= 1")
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if requests_per_second is not None and requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if min_delay < 0:
            raise ValueError("min_delay must be >= 0")
        if jitter < 0:
            raise ValueError("jitter must be >= 0")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_base <= 0:
            raise ValueError("backoff_base must be > 0")
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("timeouts must be positive")

        if isinstance(user_agent, str):
            self._user_agents = [user_agent]
        else:
            agents = list(user_agent)
            if not agents:
                raise ValueError("user_agent list must not be empty")
            self._user_agents = agents

        self._max_concurrent = max_concurrent
        self._max_depth = max_depth
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._respect_robots = respect_robots
        self._timeout = aiohttp.ClientTimeout(
            connect=connect_timeout,
            sock_read=read_timeout,
        )
        self._sem_manager = SemaphoreManager(
            max_concurrent=max_concurrent,
            max_per_host=max_per_host,
        )
        self._session_lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._parser = HTMLParser()

        if requests_per_second is None and min_delay <= 0:
            self._rate_limiter: Optional[RateLimiter] = None
        else:
            self._rate_limiter = RateLimiter(
                requests_per_second=requests_per_second if requests_per_second is not None else 1e6,
                per_domain=True,
                min_delay=min_delay,
                jitter=jitter,
            )

        self._robots: Optional[RobotsParser] = (
            RobotsParser(fetcher=self._fetch_robots_text) if respect_robots else None
        )
        self._robots_loaded: set[str] = set()
        self._robots_init_lock = asyncio.Lock()

        self._request_count = 0
        self._total_request_time = 0.0
        self._blocked_count = 0
        self._retry_count = 0
        self._stats_start_time: Optional[float] = None

    async def fetch_url(self, url: str) -> str:
        """Download a single URL and return its body as text.

        Honors robots.txt (if respect_robots), rate limit (if configured), and retries
        transient errors (5xx, 429, timeout, connection) up to max_retries times.
        """
        session = await self._ensure_session()
        domain = urlparse(url).netloc.lower()
        ua = self._pick_user_agent()

        if self._robots is not None:
            await self._ensure_robots(url)
            if not self._robots.can_fetch(url, ua):
                self._blocked_count += 1
                logger.info("robots blocked: %s", url)
                raise RobotsBlocked(url)

        if self._rate_limiter is not None:
            await self._rate_limiter.acquire(domain)

        async with self._sem_manager.acquire(url):
            return await self._fetch_with_retry(session, url, ua)

    async def _fetch_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        ua: str,
    ) -> str:
        attempt = 0
        while True:
            request_start = time.perf_counter()
            try:
                logger.info("GET %s", url)
                async with session.get(url, headers={"User-Agent": ua}) as response:
                    response.raise_for_status()
                    text = await response.text()
                self._record_success(request_start)
                logger.info("OK %s (%d bytes)", url, len(text))
                return text
            except aiohttp.ClientResponseError as exc:
                if not self._is_retryable_status(exc.status) or attempt >= self._max_retries:
                    logger.warning("HTTP %s: %s", exc.status, url)
                    raise
                logger.warning(
                    "HTTP %s (retry %d/%d): %s",
                    exc.status, attempt + 1, self._max_retries, url,
                )
            except (asyncio.TimeoutError, aiohttp.ClientConnectionError) as exc:
                if attempt >= self._max_retries:
                    logger.warning("%s: %s", exc.__class__.__name__, url)
                    raise
                logger.warning(
                    "%s (retry %d/%d): %s",
                    exc.__class__.__name__, attempt + 1, self._max_retries, url,
                )
            except aiohttp.ClientError as exc:
                logger.warning("Client error: %s (%s)", url, exc.__class__.__name__)
                raise

            attempt += 1
            self._retry_count += 1
            await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))

    @staticmethod
    def _is_retryable_status(status: int) -> bool:
        return status >= 500 or status == 429

    def _pick_user_agent(self) -> str:
        if len(self._user_agents) == 1:
            return self._user_agents[0]
        return random.choice(self._user_agents)

    def _record_success(self, request_start: float) -> None:
        if self._stats_start_time is None:
            self._stats_start_time = time.monotonic()
        self._request_count += 1
        self._total_request_time += time.perf_counter() - request_start

    async def _fetch_robots_text(self, url: str) -> Optional[str]:
        """Fetch robots.txt without going through robots/rate-limit/semaphore checks."""
        session = await self._ensure_session()
        headers = {"User-Agent": self._user_agents[0]}
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                return await response.text()
        except Exception:
            return None

    async def _ensure_robots(self, url: str) -> None:
        if self._robots is None:
            return
        domain = urlparse(url).netloc.lower()
        if domain in self._robots_loaded:
            return
        async with self._robots_init_lock:
            if domain in self._robots_loaded:
                return
            info = await self._robots.fetch_robots(url)
            self._robots_loaded.add(domain)
            crawl_delay = info.get("crawl_delay")
            if crawl_delay:
                if self._rate_limiter is not None:
                    self._rate_limiter.set_domain_interval(domain, crawl_delay)
                else:
                    logger.warning(
                        "robots.txt for %s sets Crawl-delay=%s but no rate limiter "
                        "is configured - delay will not be enforced",
                        domain, crawl_delay,
                    )

    def get_stats(self) -> dict:
        if self._stats_start_time is None or self._request_count == 0:
            return {
                "requests": 0,
                "rate_per_sec": 0.0,
                "avg_interval_ms": 0.0,
                "avg_request_ms": 0.0,
                "blocked_by_robots": self._blocked_count,
                "retries": self._retry_count,
            }
        elapsed = max(time.monotonic() - self._stats_start_time, 1e-6)
        avg_interval_ms = (
            elapsed / (self._request_count - 1) * 1000
            if self._request_count > 1 else 0.0
        )
        avg_request_ms = self._total_request_time / self._request_count * 1000
        rate_per_sec = self._request_count / elapsed if self._request_count > 1 else 0.0
        return {
            "requests": self._request_count,
            "rate_per_sec": rate_per_sec,
            "avg_interval_ms": avg_interval_ms,
            "avg_request_ms": avg_request_ms,
            "blocked_by_robots": self._blocked_count,
            "retries": self._retry_count,
        }

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
        cond = asyncio.Condition()
        active = 0
        start_time = time.perf_counter()

        async def worker() -> None:
            nonlocal active
            while True:
                async with cond:
                    while True:
                        if done_event.is_set():
                            return
                        if queue.get_stats()["processed"] >= max_pages:
                            done_event.set()
                            cond.notify_all()
                            return
                        if not queue.empty():
                            break
                        if active == 0:
                            done_event.set()
                            cond.notify_all()
                            return
                        await cond.wait()
                    url = await queue.get_next()
                    active += 1

                try:
                    data = await self.fetch_and_parse(url)
                    queue.mark_processed(url, data)
                    depth = queue.get_depth(url)
                    if depth < self._max_depth and queue.get_stats()["processed"] < max_pages:
                        async with cond:
                            added = False
                            for link in data["links"]:
                                if self._should_visit(
                                    link, base_hosts, same_domain_only, include_re, exclude_re
                                ):
                                    if queue.add_url(link, depth=depth + 1):
                                        added = True
                            if added:
                                cond.notify_all()
                except RobotsBlocked:
                    pass
                except Exception as exc:
                    queue.mark_failed(url, f"{exc.__class__.__name__}: {exc}")
                finally:
                    async with cond:
                        active -= 1
                        cond.notify_all()

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
            "%s | processed=%d queued=%d failed=%d blocked=%d retries=%d active=%d rate=%.1f/s",
            prefix,
            stats["processed"],
            stats["queued"],
            stats["failed"],
            self._blocked_count,
            self._retry_count,
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
                )
            return self._session
