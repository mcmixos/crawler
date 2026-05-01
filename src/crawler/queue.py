import heapq
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CrawlerQueue:
    """Priority queue with depth tracking and visited/processed/failed bookkeeping.

    Public properties (visited_urls, processed_urls, failed_urls) return live
    references to internal state - do not mutate from outside.
    """

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._counter = 0
        self._seen: set[str] = set()
        self._depths: dict[str, int] = {}
        self._processed: dict[str, dict] = {}
        self._failed: dict[str, str] = {}

    def add_url(self, url: str, priority: int = 0, depth: int = 0) -> bool:
        """Add a URL with priority and depth. Returns False if URL was already seen."""
        if url in self._seen:
            return False
        self._seen.add(url)
        self._depths[url] = depth
        heapq.heappush(self._heap, (-priority, self._counter, url))
        self._counter += 1
        return True

    async def get_next(self) -> Optional[str]:
        """Pop the highest-priority URL, or None if the queue is empty."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap)[2]

    def mark_processed(self, url: str, data: Optional[dict] = None) -> None:
        self._processed[url] = data if data is not None else {}

    def mark_failed(self, url: str, error: str) -> None:
        self._failed[url] = error

    def get_depth(self, url: str) -> int:
        return self._depths.get(url, 0)

    def empty(self) -> bool:
        return not self._heap

    def get_stats(self) -> dict:
        return {
            "queued": len(self._heap),
            "visited": len(self._seen),
            "processed": len(self._processed),
            "failed": len(self._failed),
        }

    @property
    def visited_urls(self) -> set[str]:
        return self._seen

    @property
    def processed_urls(self) -> dict[str, dict]:
        return self._processed

    @property
    def failed_urls(self) -> dict[str, str]:
        return self._failed
