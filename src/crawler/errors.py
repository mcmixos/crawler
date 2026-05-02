import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


class CrawlerError(Exception):
    """Base class for all crawler errors. Optional `status` carries HTTP status when relevant."""

    def __init__(self, message: str, status: "int | None" = None) -> None:
        super().__init__(message)
        self.status = status


class TransientError(CrawlerError):
    """Temporary errors that may succeed on retry: 5xx, 429, slow responses."""


class NetworkError(CrawlerError):
    """Network-layer errors: connection refused, DNS failure, timeouts."""


class PermanentError(CrawlerError):
    """Errors that will not succeed on retry: 4xx (except 429), invalid URL, etc."""


class ParseError(CrawlerError):
    """Errors raised while parsing HTML or other structured content."""


class CircuitOpenError(PermanentError):
    """Raised when a circuit breaker has temporarily blocked requests to a host."""


_RETRYABLE_STATUSES = {429}


def classify_exception(exc: BaseException) -> CrawlerError:
    """Wrap a low-level aiohttp/asyncio exception into the crawler error hierarchy."""
    if isinstance(exc, CrawlerError):
        return exc

    if isinstance(exc, asyncio.TimeoutError):
        return NetworkError(f"Timeout: {exc}")

    if isinstance(exc, aiohttp.ClientResponseError):
        status = exc.status
        if status in _RETRYABLE_STATUSES or status >= 500:
            return TransientError(f"HTTP {status}: {exc.message}", status=status)
        return PermanentError(f"HTTP {status}: {exc.message}", status=status)

    if isinstance(exc, aiohttp.ClientConnectionError):
        return NetworkError(f"Connection error: {exc}")

    if isinstance(exc, aiohttp.ClientPayloadError):
        return TransientError(f"Payload error: {exc}")

    if isinstance(exc, aiohttp.ClientError):
        return PermanentError(f"Client error: {exc.__class__.__name__}: {exc}")

    return PermanentError(f"Unknown error: {exc.__class__.__name__}: {exc}")
