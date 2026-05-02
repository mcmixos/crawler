import asyncio
import json
import logging
from pathlib import Path

from crawler import (
    AsyncCrawler,
    CircuitBreaker,
    NetworkError,
    RetryStrategy,
    TransientError,
)


START_URLS = [
    "https://httpbin.org/status/200",
    "https://httpbin.org/status/500",
    "https://httpbin.org/status/503",
    "https://httpbin.org/status/429",
    "https://httpbin.org/status/404",
    "https://httpbin.org/status/403",
    "https://httpbin.org/delay/1",
    "https://nonexistent-host-for-resilience-demo.invalid",
]

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "resilient_results.json"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


async def main() -> None:
    setup_logging()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    retry = RetryStrategy(
        max_retries=2,
        backoff_base=0.5,
        backoff_factor=2.0,
        retry_on=[TransientError, NetworkError],
    )
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0)

    results: dict[str, str] = {}
    async with AsyncCrawler(
        max_concurrent=3,
        max_per_host=2,
        retry_strategy=retry,
        circuit_breaker=breaker,
        connect_timeout=5.0,
        total_timeout=15.0,
        user_agent="ResilientBot/1.0",
    ) as crawler:
        for url in START_URLS:
            try:
                await crawler.fetch_url(url)
                results[url] = "ok"
            except Exception as exc:
                results[url] = f"{type(exc).__name__}: {exc}"
        stats = crawler.get_stats()

    OUTPUT_FILE.write_text(
        json.dumps({"results": results, "stats": stats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Results saved to {OUTPUT_FILE}")
    print(f"Requests:           {stats['requests']}")
    print(f"Retries:            {stats['retries']}")
    print(f"Retry successes:    {stats['retry_successes']}")
    print(f"Retry failures:     {stats['retry_failures']}")
    print(f"Avg retry wait:     {stats['retry_avg_wait_ms']:.0f} ms")
    print(f"Permanent failures: {len(stats['permanent_failure_urls'])}")
    print(f"Error counts:       {stats['error_counts']}")


if __name__ == "__main__":
    asyncio.run(main())
