import asyncio
import json
import logging
from pathlib import Path

import aiofiles
import aiosqlite

from crawler import AsyncCrawler, CSVStorage, JSONStorage, SQLiteStorage


START_URLS = ["https://httpbin.org/links/10/0"]
OUTPUT_DIR = Path("output")
JSON_PATH = OUTPUT_DIR / "pages.jsonl"
CSV_PATH = OUTPUT_DIR / "pages.csv"
DB_PATH = OUTPUT_DIR / "pages.db"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def crawl_to_json() -> None:
    async with JSONStorage(JSON_PATH) as storage:
        async with AsyncCrawler(
            storage=storage,
            max_concurrent=3,
            max_depth=1,
        ) as crawler:
            await crawler.crawl(
                start_urls=START_URLS,
                max_pages=10,
                same_domain_only=True,
            )


async def load_jsonl() -> list[dict]:
    pages = []
    async with aiofiles.open(JSON_PATH, encoding="utf-8") as f:
        async for line in f:
            line = line.strip()
            if line:
                pages.append(json.loads(line))
    return pages


async def save_to_csv(pages: list[dict]) -> None:
    async with CSVStorage(CSV_PATH) as storage:
        for page in pages:
            await storage.save(page)


async def save_to_sqlite(pages: list[dict]) -> None:
    async with SQLiteStorage(DB_PATH) as storage:
        for page in pages:
            await storage.save(page)


async def query_sqlite() -> tuple[int, list[tuple]]:
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM pages") as cur:
            count = (await cur.fetchone())[0]
        async with conn.execute(
            "SELECT url, title, status_code FROM pages ORDER BY url LIMIT 5"
        ) as cur:
            rows = await cur.fetchall()
    return count, rows


async def main() -> None:
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    print("\n--- Crawling to JSON Lines ---")
    await crawl_to_json()

    print("\n--- Reading back from JSON ---")
    pages = await load_jsonl()
    print(f"Loaded {len(pages)} pages from {JSON_PATH}")

    print("\n--- Saving to CSV ---")
    await save_to_csv(pages)
    print(f"Wrote {len(pages)} rows to {CSV_PATH}")

    print("\n--- Saving to SQLite ---")
    await save_to_sqlite(pages)
    print(f"Inserted {len(pages)} rows into {DB_PATH}")

    print("\n--- Querying SQLite ---")
    count, rows = await query_sqlite()
    print(f"pages table: {count} rows")
    for url, title, status in rows:
        print(f"  [{status}] {url} - {title}")


if __name__ == "__main__":
    asyncio.run(main())
