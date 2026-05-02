import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from crawler import AdvancedCrawler, CrawlerConfig


def _config_dict(start_urls, **overrides):
    base = {
        "start_urls": start_urls,
        "max_pages": 10,
        "crawler": {"max_concurrent": 2, "max_depth": 1},
    }
    base.update(overrides)
    return base


def _page(*hrefs: str) -> str:
    body = "".join(f"<a href='{h}'>x</a>" for h in hrefs)
    return f"<html><body>{body}</body></html>"


async def test_crawl_runs_and_records_stats():
    config = CrawlerConfig.from_dict(_config_dict(["https://example.test/p1"]))
    with aioresponses() as m:
        m.get(
            "https://example.test/p1",
            body=_page("https://example.test/p2"),
            content_type="text/html",
        )
        m.get("https://example.test/p2", body=_page(), content_type="text/html")
        async with AdvancedCrawler(config) as crawler:
            results = await crawler.crawl()
            stats = crawler.get_stats()

    assert "https://example.test/p1" in results
    assert "https://example.test/p2" in results
    assert stats["successful"] == 2
    assert stats["failed"] == 0


async def test_export_json_and_html(tmp_path: Path):
    config = CrawlerConfig.from_dict(_config_dict(["https://example.test/p1"]))
    with aioresponses() as m:
        m.get("https://example.test/p1", body=_page(), content_type="text/html")
        async with AdvancedCrawler(config) as crawler:
            await crawler.crawl()
            json_path = tmp_path / "stats.json"
            html_path = tmp_path / "report.html"
            crawler.export_to_json(json_path)
            crawler.export_to_html_report(html_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["successful"] == 1
    html_text = html_path.read_text(encoding="utf-8")
    assert "Crawl Report" in html_text


async def test_storage_built_from_config(tmp_path: Path):
    db_path = tmp_path / "out.db"
    config = CrawlerConfig.from_dict(_config_dict(
        ["https://example.test/p1"],
        storage={"type": "sqlite", "path": str(db_path), "batch_size": 5},
    ))
    with aioresponses() as m:
        m.get("https://example.test/p1", body=_page(), content_type="text/html")
        async with AdvancedCrawler(config) as crawler:
            await crawler.crawl()

    import aiosqlite
    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM pages") as cur:
            count = (await cur.fetchone())[0]
    assert count == 1


async def test_no_start_urls_returns_empty():
    config = CrawlerConfig.from_dict({"start_urls": [], "max_pages": 10})
    async with AdvancedCrawler(config) as crawler:
        results = await crawler.crawl()
    assert results == {}


async def test_invalid_storage_type_raises():
    config = CrawlerConfig.from_dict({
        "start_urls": ["https://x.com"],
        "storage": {"type": "mongodb", "path": "x"},
    })
    with pytest.raises(ValueError):
        AdvancedCrawler(config)


async def test_storage_type_requires_path():
    config = CrawlerConfig.from_dict({
        "start_urls": ["https://x.com"],
        "storage": {"type": "json"},
    })
    with pytest.raises(ValueError):
        AdvancedCrawler(config)


async def test_sitemap_urls_loaded():
    sitemap_xml = """<?xml version='1.0'?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.test/from-sitemap</loc></url>
</urlset>"""
    config = CrawlerConfig.from_dict({
        "start_urls": [],
        "sitemap_urls": ["https://example.test/sitemap.xml"],
        "max_pages": 5,
        "crawler": {"max_concurrent": 1, "max_depth": 0},
    })
    with aioresponses() as m:
        m.get(
            "https://example.test/sitemap.xml",
            body=sitemap_xml,
            content_type="application/xml",
        )
        m.get(
            "https://example.test/from-sitemap",
            body=_page(),
            content_type="text/html",
        )
        async with AdvancedCrawler(config) as crawler:
            results = await crawler.crawl()

    assert "https://example.test/from-sitemap" in results
