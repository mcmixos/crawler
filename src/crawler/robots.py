import logging
from typing import Awaitable, Callable, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], Awaitable[Optional[str]]]


class RobotsBlocked(Exception):
    """Raised when a URL is disallowed by robots.txt for the active user agent."""

    def __init__(self, url: str) -> None:
        super().__init__(f"Blocked by robots.txt: {url}")
        self.url = url


class RobotsParser:
    """Fetches, parses, and caches robots.txt rules per host origin.

    Note: get_crawl_delay accepts a base_url parameter (extension over the literal TZ
    signature) so that one parser can serve multiple hosts without per-host instances.
    """

    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher
        self._cache: dict[str, RobotFileParser] = {}

    async def fetch_robots(self, base_url: str) -> dict:
        host_origin = self._origin_of(base_url)
        if host_origin is None:
            return {"host": "", "fetched": False, "crawl_delay": None}

        cached = self._cache.get(host_origin)
        if cached is not None:
            return self._summarize(host_origin, cached, fetched=True)

        robots_url = host_origin + "/robots.txt"
        text: Optional[str] = None
        try:
            text = await self._fetcher(robots_url)
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", robots_url, exc)

        rp = RobotFileParser()
        if text:
            rp.parse(text.splitlines())
            fetched = True
        else:
            rp.allow_all = True
            fetched = False
        self._cache[host_origin] = rp
        return self._summarize(host_origin, rp, fetched=fetched)

    def can_fetch(self, url: str, user_agent: str = "*") -> bool:
        host_origin = self._origin_of(url)
        if host_origin is None:
            return True
        rp = self._cache.get(host_origin)
        if rp is None:
            return True
        return rp.can_fetch(user_agent, url)

    def get_crawl_delay(self, base_url: str, user_agent: str = "*") -> float:
        host_origin = self._origin_of(base_url)
        if host_origin is None:
            return 0.0
        rp = self._cache.get(host_origin)
        if rp is None:
            return 0.0
        delay = rp.crawl_delay(user_agent)
        return float(delay) if delay is not None else 0.0

    @staticmethod
    def _origin_of(url: str) -> Optional[str]:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc.lower()}"

    @staticmethod
    def _summarize(host: str, rp: RobotFileParser, fetched: bool) -> dict:
        delay = rp.crawl_delay("*")
        return {
            "host": host,
            "fetched": fetched,
            "crawl_delay": float(delay) if delay is not None else None,
        }
