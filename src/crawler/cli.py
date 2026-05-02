import argparse
import asyncio
import sys
from typing import Optional

from crawler.advanced import AdvancedCrawler
from crawler.config import CrawlerConfig


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="crawler",
        description="Asynchronous web crawler with config and CLI overrides.",
    )
    parser.add_argument(
        "--config",
        help="Path to YAML config file",
    )
    parser.add_argument(
        "--urls",
        nargs="+",
        help="Start URLs (overrides config.start_urls)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum pages to crawl (overrides config.max_pages)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        help="Maximum link-following depth (overrides config.crawler.max_depth)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        help="Requests per second (overrides config.crawler.requests_per_second)",
    )
    parser.add_argument(
        "--respect-robots",
        action="store_true",
        help="Enable robots.txt enforcement",
    )
    parser.add_argument(
        "--same-domain-only",
        action="store_true",
        help="Restrict crawl to start URL domains",
    )
    parser.add_argument(
        "--output",
        help="Path to JSON stats output (overrides config.storage if needed)",
    )
    parser.add_argument(
        "--report",
        help="Path to HTML report output",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level (overrides config.logging.level)",
    )
    return parser.parse_args(argv)


def _build_config(args: argparse.Namespace) -> CrawlerConfig:
    if args.config:
        config = CrawlerConfig.from_yaml(args.config)
    else:
        config = CrawlerConfig()

    if args.urls:
        config.start_urls = list(args.urls)
    if args.max_pages is not None:
        config.max_pages = args.max_pages
    if args.max_depth is not None:
        config.crawler.max_depth = args.max_depth
    if args.rate_limit is not None:
        config.crawler.requests_per_second = args.rate_limit
    if args.respect_robots:
        config.crawler.respect_robots = True
    if args.same_domain_only:
        config.filters.same_domain_only = True
    if args.log_level:
        config.logging.level = args.log_level

    if not config.start_urls and not config.sitemap_urls:
        raise SystemExit("error: no start URLs (use --urls or --config)")
    return config


async def _run(config: CrawlerConfig, args: argparse.Namespace) -> int:
    async with AdvancedCrawler(config) as crawler:
        await crawler.crawl()
        if args.output:
            crawler.export_to_json(args.output)
        if args.report:
            crawler.export_to_html_report(args.report)
        stats = crawler.get_stats()

    print(f"Total pages:   {stats['total_pages']}")
    print(f"Successful:    {stats['successful']}")
    print(f"Failed:        {stats['failed']}")
    print(f"Runtime:       {stats['runtime_seconds']:.2f} s")
    print(f"Avg pages/sec: {stats['avg_pages_per_sec']:.2f}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    config = _build_config(args)
    return asyncio.run(_run(config, args))


if __name__ == "__main__":
    sys.exit(main())
