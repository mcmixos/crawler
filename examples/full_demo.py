import asyncio
from pathlib import Path

from crawler import AdvancedCrawler


CONFIG_PATH = Path(__file__).parent / "example_config.yaml"
OUTPUT_DIR = Path("output")


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with AdvancedCrawler.from_config(CONFIG_PATH) as crawler:
        await crawler.crawl()
        crawler.export_to_json(OUTPUT_DIR / "full_demo_stats.json")
        crawler.export_to_html_report(OUTPUT_DIR / "full_demo_report.html")
        stats = crawler.get_stats()

    print()
    print("=" * 50)
    print(f"Total pages:     {stats['total_pages']}")
    print(f"Successful:      {stats['successful']}")
    print(f"Failed:          {stats['failed']}")
    print(f"Runtime:         {stats['runtime_seconds']:.2f} s")
    print(f"Avg pages/sec:   {stats['avg_pages_per_sec']:.2f}")
    print(f"Status codes:    {stats['status_distribution']}")
    print(f"Top domains:     {stats['top_domains'][:5]}")
    print()
    print(f"Stats JSON:      output/full_demo_stats.json")
    print(f"HTML report:     output/full_demo_report.html")
    print(f"SQLite DB:       output/full_demo.db")
    print(f"Log file:        output/crawler.log")


if __name__ == "__main__":
    asyncio.run(main())
