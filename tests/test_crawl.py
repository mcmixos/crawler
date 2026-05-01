import pytest
from aioresponses import aioresponses

from crawler import AsyncCrawler


def _page(*hrefs: str) -> str:
    body = "".join(f"<a href='{h}'>x</a>" for h in hrefs)
    return f"<html><body>{body}</body></html>"


async def test_crawl_visits_linked_pages():
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2", "https://example.test/p3"),
            content_type="text/html",
        )
        m.get("https://example.test/p2", body=_page(), content_type="text/html")
        m.get("https://example.test/p3", body=_page(), content_type="text/html")

        async with AsyncCrawler(max_concurrent=2, max_depth=3) as crawler:
            results = await crawler.crawl(["https://example.test/p1"])

    assert set(results.keys()) == {
        "https://example.test/p1",
        "https://example.test/p2",
        "https://example.test/p3",
    }


async def test_crawl_respects_max_depth():
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2"),
            content_type="text/html",
        )
        m.get(
            "https://example.test/p2",
            body=_page("https://example.test/p3"),
            content_type="text/html",
        )
        m.get("https://example.test/p3", body=_page(), content_type="text/html")

        async with AsyncCrawler(max_depth=1) as crawler:
            results = await crawler.crawl(["https://example.test/p1"])

    assert set(results.keys()) == {
        "https://example.test/p1",
        "https://example.test/p2",
    }


async def test_crawl_max_depth_zero_only_processes_start():
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2"),
            content_type="text/html",
        )

        async with AsyncCrawler(max_depth=0) as crawler:
            results = await crawler.crawl(["https://example.test/p1"])

    assert set(results.keys()) == {"https://example.test/p1"}


async def test_crawl_same_domain_only():
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2", "https://other.test/x"),
            content_type="text/html",
        )
        m.get("https://example.test/p2", body=_page(), content_type="text/html")

        async with AsyncCrawler(max_depth=2) as crawler:
            results = await crawler.crawl(
                ["https://example.test/p1"], same_domain_only=True
            )

    assert set(results.keys()) == {
        "https://example.test/p1",
        "https://example.test/p2",
    }


async def test_crawl_exclude_patterns():
    with aioresponses() as m:
        m.get(
            "https://example.test/start",
            body=_page(
                "https://example.test/page.html",
                "https://example.test/img.png",
            ),
            content_type="text/html",
        )
        m.get(
            "https://example.test/page.html",
            body=_page(),
            content_type="text/html",
        )

        async with AsyncCrawler(max_depth=2) as crawler:
            results = await crawler.crawl(
                ["https://example.test/start"],
                exclude_patterns=[r"\.png$"],
            )

    assert "https://example.test/img.png" not in results
    assert "https://example.test/page.html" in results


async def test_crawl_include_patterns():
    with aioresponses() as m:
        m.get(
            "https://example.test/start",
            body=_page(
                "https://example.test/articles/a1",
                "https://example.test/about",
            ),
            content_type="text/html",
        )
        m.get(
            "https://example.test/articles/a1",
            body=_page(),
            content_type="text/html",
        )

        async with AsyncCrawler(max_depth=2) as crawler:
            results = await crawler.crawl(
                ["https://example.test/start"],
                include_patterns=[r"/articles/"],
            )

    assert "https://example.test/articles/a1" in results
    assert "https://example.test/about" not in results


async def test_crawl_no_duplicate_visits():
    with aioresponses() as m:
        m.get(
            "https://example.test/start",
            body=_page("https://example.test/start"),
            content_type="text/html",
        )

        async with AsyncCrawler() as crawler:
            results = await crawler.crawl(["https://example.test/start"])

    assert len(results) == 1


async def test_crawl_respects_max_pages():
    links = [f"https://example.test/p{i}" for i in range(20)]
    with aioresponses() as m:
        m.get(
            "https://example.test/start",
            body=_page(*links),
            content_type="text/html",
        )
        for url in links:
            m.get(url, body=_page(), content_type="text/html")

        async with AsyncCrawler(max_concurrent=2, max_depth=2) as crawler:
            results = await crawler.crawl(
                ["https://example.test/start"], max_pages=5
            )

    assert 5 <= len(results) <= 5 + 2


async def test_crawl_failed_pages_in_failed_dict():
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2"),
            content_type="text/html",
        )
        m.get("https://example.test/p2", status=500)

        async with AsyncCrawler(max_depth=2) as crawler:
            results = await crawler.crawl(["https://example.test/p1"])

    assert "https://example.test/p1" in results
    assert "https://example.test/p2" not in results


async def test_crawl_invalid_max_pages_rejected():
    async with AsyncCrawler() as crawler:
        with pytest.raises(ValueError):
            await crawler.crawl(["https://example.test/p1"], max_pages=0)


async def test_crawl_empty_start_urls():
    async with AsyncCrawler() as crawler:
        results = await crawler.crawl([])
    assert results == {}


def test_invalid_max_per_host_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(max_per_host=0)


def test_invalid_max_depth_rejected():
    with pytest.raises(ValueError):
        AsyncCrawler(max_depth=-1)
