import asyncio
import json
import logging
from pathlib import Path

from bs4 import BeautifulSoup

from crawler import AsyncCrawler, HTMLParser


URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://www.iana.org/help/example-domains",
]

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "parse_results.json"

logger = logging.getLogger("parse_demo")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def process(crawler: AsyncCrawler, parser: HTMLParser, url: str) -> dict:
    html = await crawler.fetch_url(url)
    soup = await asyncio.to_thread(BeautifulSoup, html, "lxml")
    metadata = parser.extract_metadata(soup)
    return {
        "url": url,
        "title": metadata["title"],
        "text": parser.extract_text(soup),
        "links": parser.extract_links(soup, url),
        "metadata": metadata,
        "headings": parser.extract_headings(soup),
        "images_count": len(parser.extract_images(soup, url)),
    }


async def main() -> None:
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parser = HTMLParser()
    async with AsyncCrawler(max_concurrent=5) as crawler:
        tasks = [process(crawler, parser, url) for url in URLS]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[dict] = []
    for url, outcome in zip(URLS, outcomes):
        if isinstance(outcome, Exception):
            logger.warning("Skipping %s: %s", url, outcome.__class__.__name__)
            continue
        results.append(outcome)

    OUTPUT_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n--- Parsed {len(results)}/{len(URLS)} pages ---")
    for r in results:
        h = r["headings"]
        print(
            f"{r['url']}\n"
            f"  title:    {r['title']}\n"
            f"  text:     {len(r['text'])} chars\n"
            f"  links:    {len(r['links'])}\n"
            f"  images:   {r['images_count']}\n"
            f"  headings: h1={len(h['h1'])} h2={len(h['h2'])} h3={len(h['h3'])}"
        )
    print(f"\nFull results saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
