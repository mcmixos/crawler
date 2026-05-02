import logging
from typing import Awaitable, Callable, Optional
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

Fetcher = Callable[[str], Awaitable[Optional[str]]]

_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_MAX_RECURSION_DEPTH = 5


class SitemapParser:
    """Fetches and parses sitemap.xml, recursing into sitemap indexes."""

    def __init__(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def fetch_sitemap(self, sitemap_url: str) -> list[str]:
        """Return all URLs from a sitemap or sitemap index. Empty list on failure."""
        seen: set[str] = set()
        result: list[str] = []
        await self._fetch_recursive(sitemap_url, depth=0, seen=seen, result=result)
        return result

    async def _fetch_recursive(
        self,
        url: str,
        depth: int,
        seen: set[str],
        result: list[str],
    ) -> None:
        if depth >= _MAX_RECURSION_DEPTH:
            logger.warning("sitemap recursion depth limit reached at %s", url)
            return
        if url in seen:
            return
        seen.add(url)

        try:
            text = await self._fetcher(url)
        except Exception as exc:
            logger.warning("failed to fetch sitemap %s: %s", url, exc)
            return
        if not text:
            return

        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            logger.warning("failed to parse sitemap %s: %s", url, exc)
            return

        tag = self._strip_ns(root.tag)
        if tag == "sitemapindex":
            for sitemap in root.findall(f"{_NS}sitemap"):
                loc = sitemap.find(f"{_NS}loc")
                if loc is not None and loc.text:
                    await self._fetch_recursive(
                        loc.text.strip(), depth + 1, seen, result,
                    )
        elif tag == "urlset":
            for entry in root.findall(f"{_NS}url"):
                loc = entry.find(f"{_NS}loc")
                if loc is not None and loc.text:
                    result.append(loc.text.strip())
        else:
            logger.warning("unrecognized sitemap root element: %s", tag)

    @staticmethod
    def _strip_ns(tag: str) -> str:
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag
