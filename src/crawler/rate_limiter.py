import asyncio
import logging
import random
import time
from typing import Optional

logger = logging.getLogger(__name__)

_GLOBAL_KEY = "__global__"


class RateLimiter:
    """Enforces a minimum interval between requests, optionally per-domain.

    Uses a "next allowed time" timestamp per key. acquire() reserves the next slot
    immediately and sleeps if the slot is in the future, so concurrent callers form
    an ordered queue without needing an explicit lock.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        per_domain: bool = True,
        min_delay: float = 0.0,
        jitter: float = 0.0,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if min_delay < 0:
            raise ValueError("min_delay must be >= 0")
        if jitter < 0:
            raise ValueError("jitter must be >= 0")

        self._base_interval = max(1.0 / requests_per_second, min_delay)
        self._jitter = jitter
        self._per_domain = per_domain
        self._next_allowed: dict[str, float] = {}
        self._domain_overrides: dict[str, float] = {}

    async def acquire(self, domain: Optional[str] = None) -> None:
        key = domain if (self._per_domain and domain) else _GLOBAL_KEY
        interval = self._domain_overrides.get(key, self._base_interval)
        if self._jitter > 0:
            interval += random.uniform(0.0, self._jitter)

        now = time.monotonic()
        slot = max(now, self._next_allowed.get(key, 0.0))
        self._next_allowed[key] = slot + interval

        wait = slot - now
        if wait > 0:
            await asyncio.sleep(wait)

    def set_domain_interval(self, domain: str, interval: float) -> None:
        """Raise the minimum interval for a specific domain (e.g. from robots Crawl-delay).

        Only takes effect if the new interval is greater than the current one for the domain.
        """
        if interval < 0:
            raise ValueError("interval must be >= 0")
        key = domain if self._per_domain else _GLOBAL_KEY
        current = self._domain_overrides.get(key, self._base_interval)
        if interval > current:
            self._domain_overrides[key] = interval
