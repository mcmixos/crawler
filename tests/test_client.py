import asyncio

import aiohttp
import pytest
from aioresponses import aioresponses

from crawler import AsyncCrawler


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
            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 404


async def test_fetch_url_raises_on_500():
    url = "https://example.test/boom"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        async with AsyncCrawler() as crawler:
            with pytest.raises(aiohttp.ClientResponseError) as exc_info:
                await crawler.fetch_url(url)
    assert exc_info.value.status == 500


async def test_fetch_url_raises_on_timeout():
    url = "https://example.test/slow"
    with aioresponses() as mocked:
        mocked.get(url, exception=asyncio.TimeoutError())
        async with AsyncCrawler() as crawler:
            with pytest.raises(asyncio.TimeoutError):
                await crawler.fetch_url(url)


async def test_fetch_url_raises_on_network_error():
    url = "https://example.test/down"
    with aioresponses() as mocked:
        mocked.get(url, exception=aiohttp.ClientConnectionError("connection refused"))
        async with AsyncCrawler() as crawler:
            with pytest.raises(aiohttp.ClientError):
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
