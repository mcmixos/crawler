import json
from pathlib import Path

from crawler import CrawlerStats


def test_initial_state():
    stats = CrawlerStats()
    d = stats.to_dict()
    assert d["total_pages"] == 0
    assert d["successful"] == 0
    assert d["failed"] == 0
    assert d["status_distribution"] == {}
    assert d["top_domains"] == []


def test_record_success():
    stats = CrawlerStats()
    stats.record_request("https://example.com/a", success=True, status_code=200)
    stats.record_request("https://example.com/b", success=True, status_code=200)
    d = stats.to_dict()
    assert d["successful"] == 2
    assert d["failed"] == 0
    assert d["total_pages"] == 2
    assert d["status_distribution"] == {200: 2}


def test_record_failure():
    stats = CrawlerStats()
    stats.record_request("https://example.com/a", success=False, status_code=500)
    stats.record_request("https://example.com/b", success=False)
    d = stats.to_dict()
    assert d["successful"] == 0
    assert d["failed"] == 2
    assert d["status_distribution"] == {500: 1}


def test_top_domains():
    stats = CrawlerStats()
    for i in range(5):
        stats.record_request(f"https://a.com/p{i}", success=True, status_code=200)
    for i in range(2):
        stats.record_request(f"https://b.com/p{i}", success=True, status_code=200)
    stats.record_request("https://c.com/x", success=True, status_code=200)
    top = stats.top_domains(n=2)
    assert top == [("a.com", 5), ("b.com", 2)]


def test_status_distribution_multiple_codes():
    stats = CrawlerStats()
    stats.record_request("u1", success=True, status_code=200)
    stats.record_request("u2", success=True, status_code=200)
    stats.record_request("u3", success=False, status_code=404)
    stats.record_request("u4", success=False, status_code=500)
    stats.record_request("u5", success=False, status_code=500)
    assert stats.status_distribution() == {200: 2, 404: 1, 500: 2}


def test_export_to_json(tmp_path: Path):
    path = tmp_path / "stats.json"
    stats = CrawlerStats()
    stats.record_request("https://example.com/a", success=True, status_code=200)
    stats.export_to_json(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["total_pages"] == 1
    assert data["successful"] == 1


def test_export_to_html_report_contains_key_data(tmp_path: Path):
    path = tmp_path / "report.html"
    stats = CrawlerStats()
    stats.record_request("https://example.com/a", success=True, status_code=200)
    stats.record_request("https://example.com/b", success=False, status_code=404)
    stats.export_to_html_report(path)
    html_text = path.read_text(encoding="utf-8")
    assert "<title>Crawl Report</title>" in html_text
    assert "Total pages" in html_text
    assert "example.com" in html_text
    assert ">200<" in html_text
    assert ">404<" in html_text


def test_html_report_escapes_special_chars(tmp_path: Path):
    path = tmp_path / "report.html"
    stats = CrawlerStats()
    stats.record_request("https://<script>alert(1)</script>.com/x", success=True, status_code=200)
    stats.export_to_html_report(path)
    html_text = path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text


def test_avg_pages_per_sec_zero_when_no_pages():
    stats = CrawlerStats()
    assert stats.avg_pages_per_sec == 0.0
