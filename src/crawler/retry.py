import asyncio
import logging
import time
from collections import defaultdict
from typing import Awaitable, Callable, Optional

from crawler.errors import CrawlerError, NetworkError, TransientError

logger = logging.getLogger(__name__)


class RetryStrategy:
    """Wraps an async callable with retry-on-classified-error behavior.

    Stats are accumulated across all execute_with_retry calls and exposed via get_stats.
    """

    def __init__(
        self,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        backoff_base: float = 1.0,
        max_backoff: float = 60.0,
        retry_on: Optional[list[type]] = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if backoff_factor <= 0:
            raise ValueError("backoff_factor must be > 0")
        if backoff_base <= 0:
            raise ValueError("backoff_base must be > 0")
        if max_backoff <= 0:
            raise ValueError("max_backoff must be > 0")

        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff
        self._retry_on: tuple[type, ...] = tuple(
            retry_on if retry_on is not None else [TransientError, NetworkError]
        )

        self._attempts_total = 0
        self._retries_total = 0
        self._successes_after_retry = 0
        self._failures_after_retry = 0
        self._total_retry_wait = 0.0
        self._error_counts: dict[str, int] = defaultdict(int)

    async def execute_with_retry(
        self,
        coro_func: Callable[..., Awaitable],
        *args,
        **kwargs,
    ):
        attempt = 0
        retried = False
        while True:
            self._attempts_total += 1
            try:
                result = await coro_func(*args, **kwargs)
                if retried:
                    self._successes_after_retry += 1
                return result
            except Exception as exc:
                self._error_counts[type(exc).__name__] += 1
                if not isinstance(exc, self._retry_on) or attempt >= self._max_retries:
                    if retried:
                        self._failures_after_retry += 1
                    logger.warning(
                        "give up: %s after %d attempt(s) - %s",
                        coro_func.__name__, attempt + 1, exc.__class__.__name__,
                    )
                    raise
                attempt += 1
                self._retries_total += 1
                retried = True
                wait = min(
                    self._backoff_base * (self._backoff_factor ** (attempt - 1)),
                    self._max_backoff,
                )
                self._total_retry_wait += wait
                logger.info(
                    "retry %d/%d for %s after %.2fs (%s)",
                    attempt, self._max_retries, coro_func.__name__,
                    wait, exc.__class__.__name__,
                )
                await asyncio.sleep(wait)

    def get_stats(self) -> dict:
        avg_wait_ms = (
            self._total_retry_wait / self._retries_total * 1000
            if self._retries_total else 0.0
        )
        return {
            "attempts_total": self._attempts_total,
            "retries_total": self._retries_total,
            "successes_after_retry": self._successes_after_retry,
            "failures_after_retry": self._failures_after_retry,
            "avg_retry_wait_ms": avg_wait_ms,
            "error_counts": dict(self._error_counts),
        }


class CircuitBreaker:
    """Per-key circuit breaker. Opens after N consecutive failures and stays open
    for recovery_timeout seconds, then auto-closes on the next is_open() check.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def is_open(self, key: str) -> bool:
        opened_at = self._opened_at.get(key)
        if opened_at is None:
            return False
        if time.monotonic() - opened_at > self._recovery_timeout:
            self._opened_at.pop(key, None)
            self._failures[key] = 0
            logger.info("circuit closed for %s after recovery timeout", key)
            return False
        return True

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)
        if self._opened_at.pop(key, None) is not None:
            logger.info("circuit closed for %s after success", key)

    def record_failure(self, key: str) -> None:
        if key in self._opened_at:
            return
        self._failures[key] = self._failures.get(key, 0) + 1
        if self._failures[key] >= self._failure_threshold:
            self._opened_at[key] = time.monotonic()
            logger.warning(
                "circuit opened for %s after %d consecutive failures",
                key, self._failures[key],
            )
