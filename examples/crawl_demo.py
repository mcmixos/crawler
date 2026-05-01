import asyncio
import json
import logging
from pathlib import Path

from crawler import AsyncCrawler


START_URLS = ["https://httpbin.org/links/10/0"]

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "crawl_results.json"


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
        max_per_host=3,
        max_depth=2,
    ) as crawler:
        results = await crawler.crawl(
            start_urls=START_URLS,
            max_pages=20,
            same_domain_only=True,
        )

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nCrawled {len(results)} pages, saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
