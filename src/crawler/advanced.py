import logging
import time
from pathlib import Path
from typing import Optional

from crawler.client import AsyncCrawler
from crawler.config import CrawlerConfig
from crawler.logging_setup import setup_logging
from crawler.sitemap import SitemapParser
from crawler.stats import CrawlerStats
from crawler.storage import (
    CSVStorage,
    DataStorage,
    JSONStorage,
    SQLiteStorage,
)

logger = logging.getLogger(__name__)


class AdvancedCrawler:
    """High-level crawler facade: builds AsyncCrawler from config, manages storage,
    sitemap discovery, statistics, and reports.
    """

    def __init__(self, config: CrawlerConfig) -> None:
        self._config = config
        setup_logging(
            level=config.logging.level,
            file=config.logging.file,
            max_bytes=config.logging.max_bytes,
            backup_count=config.logging.backup_count,
        )
        self._stats = CrawlerStats()
        self._storage: Optional[DataStorage] = self._build_storage(config)
        self._crawler = AsyncCrawler(
            max_concurrent=config.crawler.max_concurrent,
            max_per_host=config.crawler.max_per_host,
            max_depth=config.crawler.max_depth,
            requests_per_second=config.crawler.requests_per_second,
            min_delay=config.crawler.min_delay,
            jitter=config.crawler.jitter,
            respect_robots=config.crawler.respect_robots,
            max_retries=config.crawler.max_retries,
            backoff_base=config.crawler.backoff_base,
            connect_timeout=config.crawler.connect_timeout,
            read_timeout=config.crawler.read_timeout,
            total_timeout=config.crawler.total_timeout,
            user_agent=config.crawler.user_agent,
            storage=self._storage,
        )
        self._sitemap = SitemapParser(self._crawler._fetch_robots_text)

    @classmethod
    def from_config(cls, path: "str | Path") -> "AdvancedCrawler":
        return cls(CrawlerConfig.from_yaml(path))

    async def crawl(self) -> dict[str, dict]:
        urls = list(self._config.start_urls)

        for sitemap_url in self._config.sitemap_urls:
            logger.info("loading sitemap %s", sitemap_url)
            discovered = await self._sitemap.fetch_sitemap(sitemap_url)
            logger.info("sitemap %s yielded %d URLs", sitemap_url, len(discovered))
            urls.extend(discovered)

        if not urls:
            logger.warning("no start URLs - nothing to crawl")
            return {}

        results = await self._crawler.crawl(
            start_urls=urls,
            max_pages=self._config.max_pages,
            same_domain_only=self._config.filters.same_domain_only,
            include_patterns=self._config.filters.include_patterns or None,
            exclude_patterns=self._config.filters.exclude_patterns or None,
        )

        for url, data in results.items():
            self._stats.record_request(
                url,
                success=True,
                status_code=data.get("status_code"),
            )
        for url in self._crawler._permanent_failures:
            self._stats.record_request(url, success=False)

        return results

    def get_stats(self) -> dict:
        merged = dict(self._stats.to_dict())
        merged["crawler_internal"] = self._crawler.get_stats()
        return merged

    def export_to_json(self, path: "str | Path") -> None:
        self._stats.export_to_json(path)

    def export_to_html_report(self, path: "str | Path") -> None:
        self._stats.export_to_html_report(path)

    async def close(self) -> None:
        await self._crawler.close()
        if self._storage is not None:
            await self._storage.close()

    async def __aenter__(self) -> "AdvancedCrawler":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @staticmethod
    def _build_storage(config: CrawlerConfig) -> Optional[DataStorage]:
        kind = (config.storage.type or "").lower()
        if not kind or kind == "none":
            return None
        if not config.storage.path:
            raise ValueError(f"storage.type={kind!r} requires storage.path")
        if kind == "json":
            return JSONStorage(config.storage.path)
        if kind == "csv":
            return CSVStorage(config.storage.path)
        if kind == "sqlite":
            return SQLiteStorage(
                config.storage.path, batch_size=config.storage.batch_size,
            )
        raise ValueError(f"unknown storage.type: {kind!r}")
