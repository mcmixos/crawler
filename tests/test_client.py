import asyncio

import aiohttp
import pytest
from aioresponses import aioresponses

from crawler import AsyncCrawler, NetworkError, PermanentError, TransientError


async def test_fetch_url_returns_body():
    url = "https://example.test/page"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="hello")
        async with AsyncCrawler() as crawler:
            result = await crawler.fetch_url(url)
    assert result == "hello"


async def test_fetch_url_raises_on_404():
    url = "https://example.test/missing"
    with aioresponses() as mocked:
        mocked.get(url, status=404)
        async with AsyncCrawler() as crawler:
            with pytest.raises(PermanentError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 404


async def test_fetch_url_raises_on_500():
    url = "https://example.test/boom"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        async with AsyncCrawler() as crawler:
            with pytest.raises(TransientError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 500


async def test_fetch_url_raises_on_timeout():
    url = "https://example.test/slow"
    with aioresponses() as mocked:
        mocked.get(url, exception=asyncio.TimeoutError())
        async with AsyncCrawler() as crawler:
            with pytest.raises(NetworkError):
                await crawler.fetch_url(url)


async def test_fetch_url_raises_on_network_error():
    url = "https://example.test/down"
    with aioresponses() as mocked:
        mocked.get(url, exception=aiohttp.ClientConnectionError("connection refused"))
        async with AsyncCrawler() as crawler:
            with pytest.raises(NetworkError):
                await crawler.fetch_url(url)


async def test_fetch_urls_excludes_failures():
    ok_url = "https://example.test/ok"
    bad_url = "https://example.test/bad"
    with aioresponses() as mocked:
        mocked.get(ok_url, status=200, body="ok")
        mocked.get(bad_url, status=500)
        async with AsyncCrawler() as crawler:
            results = await crawler.fetch_urls([ok_url, bad_url])
    assert results == {ok_url: "ok"}


async def test_fetch_urls_returns_all_successful():
    urls = [f"https://example.test/{i}" for i in range(5)]
    with aioresponses() as mocked:
        for i, url in enumerate(urls):
            mocked.get(url, status=200, body=str(i))
        async with AsyncCrawler(max_concurrent=5) as crawler:
            results = await crawler.fetch_urls(urls)
    assert results == {url: str(i) for i, url in enumerate(urls)}


async def test_fetch_urls_empty_input():
    async with AsyncCrawler() as crawler:
        results = await crawler.fetch_urls([])
    assert results == {}


async def test_close_releases_session():
    async with AsyncCrawler() as crawler:
        session = await crawler._ensure_session()
        assert not session.closed
    assert session.closed


async def test_close_is_idempotent():
    crawler = AsyncCrawler()
    await crawler.close()
    await crawler.close()


async def test_session_recreated_after_close():
    url = "https://example.test/page"
    crawler = AsyncCrawler()
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="first")
        assert await crawler.fetch_url(url) == "first"
    await crawler.close()
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="second")
        assert await crawler.fetch_url(url) == "second"
    await crawler.close()


def test_invalid_max_concurrent_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(max_concurrent=0)


def test_invalid_timeout_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(connect_timeout=0)
    with pytest.raises(ValueError):
        AsyncCrawler(read_timeout=-1)


async def test_fetch_and_parse_returns_structured_data():
    url = "https://example.test/page"
    html = (
        "<html><head><title>Hi</title>"
        "<meta name='description' content='desc'></head>"
        "<body><h1>Heading</h1>"
        "<a href='/relative'>rel</a>"
        "<a href='https://other.test/abs'>abs</a></body></html>"
    )
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=html, content_type="text/html")
        async with AsyncCrawler() as crawler:
            result = await crawler.fetch_and_parse(url)
    assert result["url"] == url
    assert result["title"] == "Hi"
    assert "https://example.test/relative" in result["links"]
    assert "https://other.test/abs" in result["links"]
    assert result["metadata"]["description"] == "desc"


async def test_fetch_and_parse_propagates_fetch_errors():
    url = "https://example.test/bad"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        async with AsyncCrawler() as crawler:
            with pytest.raises(TransientError):
                await crawler.fetch_and_parse(url)


async def test_fetch_url_retries_on_500_and_succeeds():
    url = "https://example.test/flaky"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        mocked.get(url, status=200, body="ok")
        async with AsyncCrawler(max_retries=2, backoff_base=0.01) as crawler:
            result = await crawler.fetch_url(url)
    assert result == "ok"


async def test_fetch_url_retries_on_429():
    url = "https://example.test/throttled"
    with aioresponses() as mocked:
        mocked.get(url, status=429)
        mocked.get(url, status=200, body="ok")
        async with AsyncCrawler(max_retries=1, backoff_base=0.01) as crawler:
            result = await crawler.fetch_url(url)
    assert result == "ok"


async def test_fetch_url_does_not_retry_404():
    url = "https://example.test/missing"
    with aioresponses() as mocked:
        mocked.get(url, status=404)
        async with AsyncCrawler(max_retries=3, backoff_base=0.01) as crawler:
            with pytest.raises(PermanentError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 404


async def test_fetch_url_exhausts_retries_and_raises():
    url = "https://example.test/dead"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        mocked.get(url, status=500)
        mocked.get(url, status=500)
        async with AsyncCrawler(max_retries=2, backoff_base=0.01) as crawler:
            with pytest.raises(TransientError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 500


async def test_get_stats_initially_zero():
    async with AsyncCrawler() as crawler:
        stats = crawler.get_stats()
    assert stats["requests"] == 0
    assert stats["blocked_by_robots"] == 0
    assert stats["retries"] == 0


async def test_get_stats_tracks_requests():
    url1 = "https://example.test/page1"
    url2 = "https://example.test/page2"
    with aioresponses() as mocked:
        mocked.get(url1, status=200, body="a")
        mocked.get(url2, status=200, body="b")
        async with AsyncCrawler() as crawler:
            await crawler.fetch_url(url1)
            await crawler.fetch_url(url2)
            stats = crawler.get_stats()
    assert stats["requests"] == 2
    assert stats["rate_per_sec"] > 0


async def test_get_stats_tracks_retries():
    url = "https://example.test/flaky"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        mocked.get(url, status=200, body="ok")
        async with AsyncCrawler(max_retries=1, backoff_base=0.01) as crawler:
            await crawler.fetch_url(url)
            stats = crawler.get_stats()
    assert stats["retries"] == 1


def test_invalid_max_retries_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(max_retries=-1)


def test_invalid_backoff_base_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(backoff_base=0)


def test_invalid_requests_per_second_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(requests_per_second=0)


def test_empty_user_agent_list_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(user_agent=[])


def test_invalid_total_timeout_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(total_timeout=0)


async def test_permanent_failure_recorded():
    url = "https://example.test/missing"
    with aioresponses() as mocked:
        mocked.get(url, status=404)
        async with AsyncCrawler() as crawler:
            with pytest.raises(PermanentError):
                await crawler.fetch_url(url)
            stats = crawler.get_stats()
    assert url in stats["permanent_failure_urls"]


async def test_circuit_breaker_blocks_after_failures():
    from crawler import CircuitBreaker, CircuitOpenError

    url = "https://example.test/dead"
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        mocked.get(url, status=500)
        async with AsyncCrawler(circuit_breaker=cb) as crawler:
            with pytest.raises(TransientError):
                await crawler.fetch_url(url)
            with pytest.raises(TransientError):
                await crawler.fetch_url(url)
            with pytest.raises(CircuitOpenError):
                await crawler.fetch_url(url)


async def test_fetch_with_meta_returns_status_and_content_type():
    url = "https://example.test/page"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="hi", content_type="text/plain")
        async with AsyncCrawler() as crawler:
            meta = await crawler.fetch_with_meta(url)
    assert meta["text"] == "hi"
    assert meta["status_code"] == 200
    assert "text/plain" in meta["content_type"]


async def test_fetch_and_parse_includes_metadata_fields():
    url = "https://example.test/page"
    html = "<html><head><title>T</title></head><body></body></html>"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=html, content_type="text/html")
        async with AsyncCrawler() as crawler:
            data = await crawler.fetch_and_parse(url)
    assert data["status_code"] == 200
    assert "text/html" in data["content_type"]
    assert "crawled_at" in data
    assert "T" in data["title"]


async def test_crawl_saves_to_storage():
    from crawler import DataStorage

    class _Recorder(DataStorage):
        def __init__(self):
            super().__init__()
            self.saved = []

        async def _do_save(self, data):
            self.saved.append(data["url"])

        async def close(self):
            pass

    p1 = "https://example.test/p1"
    p2 = "https://example.test/p2"
    storage = _Recorder()
    with aioresponses() as m:
        m.get(p1, body=f"<a href='{p2}'>x</a>", content_type="text/html")
        m.get(p2, body="<html></html>", content_type="text/html")
        async with AsyncCrawler(storage=storage, max_depth=2) as crawler:
            await crawler.crawl([p1])

    assert set(storage.saved) == {p1, p2}


async def test_crawl_continues_when_storage_fails():
    from crawler import DataStorage

    class _AlwaysFails(DataStorage):
        def __init__(self):
            super().__init__(max_save_retries=0)

        async def _do_save(self, data):
            raise RuntimeError("disk full")

        async def close(self):
            pass

    p1 = "https://example.test/p1"
    storage = _AlwaysFails()
    with aioresponses() as m:
        m.get(p1, body="<html></html>", content_type="text/html")
        async with AsyncCrawler(storage=storage) as crawler:
            results = await crawler.crawl([p1])

    assert p1 in results


async def test_circuit_breaker_resets_on_success():
    from crawler import CircuitBreaker

    bad = "https://example.test/bad"
    good = "https://example.test/good"
    cb = CircuitBreaker(failure_threshold=2)
    with aioresponses() as mocked:
        mocked.get(bad, status=500)
        mocked.get(good, status=200, body="ok")
        mocked.get(bad, status=500)
        async with AsyncCrawler(circuit_breaker=cb) as crawler:
            with pytest.raises(TransientError):
                await crawler.fetch_url(bad)
            await crawler.fetch_url(good)
            with pytest.raises(TransientError):
                await crawler.fetch_url(bad)
            assert cb.is_open("example.test") is False
