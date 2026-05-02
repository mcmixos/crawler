import asyncio
import json
import logging
from pathlib import Path

from crawler import AsyncCrawler


START_URLS = [
    "https://httpbin.org/links/10/0",
    "https://httpbin.org/deny",
]

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "polite_results.json"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def main() -> None:
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with AsyncCrawler(
        max_concurrent=5,
        max_per_host=2,
        max_depth=1,
        requests_per_second=2.0,
        min_delay=0.3,
        jitter=0.2,
        respect_robots=True,
        max_retries=2,
        backoff_base=0.5,
        user_agent="PoliteBot/1.0",
    ) as crawler:
        results = await crawler.crawl(
            start_urls=START_URLS,
            max_pages=15,
            same_domain_only=True,
        )
        stats = crawler.get_stats()

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Crawled {len(results)} pages, saved to {OUTPUT_FILE}")
    print(f"Requests:        {stats['requests']}")
    print(f"Rate:            {stats['rate_per_sec']:.2f} req/s")
    print(f"Avg interval:    {stats['avg_interval_ms']:.0f} ms")
    print(f"Avg request:     {stats['avg_request_ms']:.0f} ms")
    print(f"Robots-blocked:  {stats['blocked_by_robots']}")
    print(f"Retries:         {stats['retries']}")


if __name__ == "__main__":
    asyncio.run(main())
