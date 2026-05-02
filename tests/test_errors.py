import asyncio
from types import SimpleNamespace

import aiohttp

from crawler import (
    CrawlerError,
    NetworkError,
    PermanentError,
    TransientError,
    classify_exception,
)


def _client_response_error(status: int, message: str = "msg") -> aiohttp.ClientResponseError:
    request_info = SimpleNamespace(real_url="http://x", method="GET", headers={})
    return aiohttp.ClientResponseError(
        request_info=request_info,
        history=(),
        status=status,
        message=message,
    )


def test_classify_passes_through_crawler_errors():
    exc = TransientError("already classified")
    assert classify_exception(exc) is exc


def test_classify_timeout_to_network():
    result = classify_exception(asyncio.TimeoutError())
    assert isinstance(result, NetworkError)


def test_classify_500_to_transient():
    result = classify_exception(_client_response_error(500))
    assert isinstance(result, TransientError)
    assert result.status == 500


def test_classify_503_to_transient():
    result = classify_exception(_client_response_error(503))
    assert isinstance(result, TransientError)
    assert result.status == 503


def test_classify_429_to_transient():
    result = classify_exception(_client_response_error(429))
    assert isinstance(result, TransientError)
    assert result.status == 429


def test_classify_404_to_permanent():
    result = classify_exception(_client_response_error(404))
    assert isinstance(result, PermanentError)
    assert result.status == 404


def test_classify_403_to_permanent():
    result = classify_exception(_client_response_error(403))
    assert isinstance(result, PermanentError)
    assert result.status == 403


def test_classify_401_to_permanent():
    result = classify_exception(_client_response_error(401))
    assert isinstance(result, PermanentError)
    assert result.status == 401


def test_classify_connection_error_to_network():
    result = classify_exception(aiohttp.ClientConnectionError("refused"))
    assert isinstance(result, NetworkError)


def test_classify_payload_error_to_transient():
    result = classify_exception(aiohttp.ClientPayloadError("partial"))
    assert isinstance(result, TransientError)


def test_classify_unknown_exception_to_permanent():
    result = classify_exception(RuntimeError("???"))
    assert isinstance(result, PermanentError)


def test_error_classes_inherit_from_crawler_error():
    for cls in (TransientError, NetworkError, PermanentError):
        assert issubclass(cls, CrawlerError)


def test_status_attribute_optional():
    err = PermanentError("no status here")
    assert err.status is None
