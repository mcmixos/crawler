import asyncio
import logging
import time

from crawler import AsyncCrawler


URLS = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://httpbin.org/delay/2?n=1",
    "https://httpbin.org/delay/2?n=2",
    "https://httpbin.org/delay/1?n=1",
    "https://httpbin.org/delay/1?n=2",
    "https://httpbin.org/status/404",
    "https://nonexistent-domain-for-test-12345.invalid",
]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def fetch_sequential(crawler: AsyncCrawler, urls: list[str]) -> dict[str, str]:
    results: dict[str, str] = {}
    for url in urls:
        try:
            results[url] = await crawler.fetch_url(url)
        except Exception:
            continue
    return results


async def main() -> None:
    setup_logging()

    async with AsyncCrawler(max_concurrent=10, connect_timeout=5.0) as crawler:
        print(f"\n--- Parallel run ({len(URLS)} URLs) ---")
        t0 = time.perf_counter()
        parallel_results = await crawler.fetch_urls(URLS)
        parallel_elapsed = time.perf_counter() - t0

        print(f"\n--- Sequential run ({len(URLS)} URLs) ---")
        t0 = time.perf_counter()
        sequential_results = await fetch_sequential(crawler, URLS)
        sequential_elapsed = time.perf_counter() - t0

    print()
    print(f"URLs requested:    {len(URLS)}")
    print(f"Parallel:   loaded {len(parallel_results)}/{len(URLS)} in {parallel_elapsed:.2f}s")
    print(f"Sequential: loaded {len(sequential_results)}/{len(URLS)} in {sequential_elapsed:.2f}s")
    if parallel_elapsed > 0:
        print(f"Speedup:    {sequential_elapsed / parallel_elapsed:.2f}x")


if __name__ == "__main__":
    asyncio.run(main())
