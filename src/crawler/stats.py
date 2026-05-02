import html
import json
import logging
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CrawlerStats:
    """Collects per-request stats and renders them as JSON or HTML."""

    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._status_counts: Counter[int] = Counter()
        self._domain_counts: Counter[str] = Counter()
        self._successful = 0
        self._failed = 0
        self._total_duration = 0.0

    def record_request(
        self,
        url: str,
        success: bool,
        status_code: Optional[int] = None,
        duration: float = 0.0,
    ) -> None:
        if success:
            self._successful += 1
        else:
            self._failed += 1
        if status_code is not None:
            self._status_counts[status_code] += 1
        host = urlparse(url).netloc.lower()
        if host:
            self._domain_counts[host] += 1
        if duration > 0:
            self._total_duration += duration

    @property
    def total_pages(self) -> int:
        return self._successful + self._failed

    @property
    def runtime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def avg_pages_per_sec(self) -> float:
        runtime = self.runtime_seconds
        return self.total_pages / runtime if runtime > 0 else 0.0

    @property
    def avg_request_ms(self) -> float:
        if self._successful == 0:
            return 0.0
        return self._total_duration / self._successful * 1000

    def top_domains(self, n: int = 10) -> list[tuple[str, int]]:
        return self._domain_counts.most_common(n)

    def status_distribution(self) -> dict[int, int]:
        return dict(self._status_counts)

    def to_dict(self) -> dict:
        return {
            "total_pages": self.total_pages,
            "successful": self._successful,
            "failed": self._failed,
            "runtime_seconds": round(self.runtime_seconds, 3),
            "avg_pages_per_sec": round(self.avg_pages_per_sec, 3),
            "avg_request_ms": round(self.avg_request_ms, 1),
            "status_distribution": self.status_distribution(),
            "top_domains": self.top_domains(),
        }

    def export_to_json(self, path: "str | Path") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def export_to_html_report(self, path: "str | Path") -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._render_html(), encoding="utf-8")

    def _render_html(self) -> str:
        data = self.to_dict()
        generated = datetime.now(timezone.utc).isoformat()
        status_rows = "".join(
            f"<tr><td>{html.escape(str(code))}</td><td>{count}</td></tr>"
            for code, count in sorted(data["status_distribution"].items())
        ) or "<tr><td colspan='2'>(none)</td></tr>"
        domain_rows = "".join(
            f"<tr><td>{html.escape(domain)}</td><td>{count}</td></tr>"
            for domain, count in data["top_domains"]
        ) or "<tr><td colspan='2'>(none)</td></tr>"
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Crawl Report</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; color: #222; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.3em; }}
h2 {{ margin-top: 2em; color: #444; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 0.5em; }}
th, td {{ padding: 0.5em 0.8em; text-align: left; border-bottom: 1px solid #eee; }}
th {{ background: #f5f5f5; }}
.summary td:first-child {{ width: 40%; font-weight: 600; }}
.muted {{ color: #888; font-size: 0.9em; }}
</style>
</head>
<body>
<h1>Crawl Report</h1>
<p class="muted">Generated: {html.escape(generated)}</p>

<h2>Summary</h2>
<table class="summary">
<tr><td>Total pages</td><td>{data["total_pages"]}</td></tr>
<tr><td>Successful</td><td>{data["successful"]}</td></tr>
<tr><td>Failed</td><td>{data["failed"]}</td></tr>
<tr><td>Runtime</td><td>{data["runtime_seconds"]} s</td></tr>
<tr><td>Avg pages/sec</td><td>{data["avg_pages_per_sec"]}</td></tr>
<tr><td>Avg request</td><td>{data["avg_request_ms"]} ms</td></tr>
</table>

<h2>Status code distribution</h2>
<table>
<tr><th>Status</th><th>Count</th></tr>
{status_rows}
</table>

<h2>Top domains</h2>
<table>
<tr><th>Domain</th><th>Pages</th></tr>
{domain_rows}
</table>
</body>
</html>
"""
