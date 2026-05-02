import json
from pathlib import Path

import aiosqlite
import pytest

from crawler import CSVStorage, DataStorage, JSONStorage, SQLiteStorage


def _record(url: str = "https://example.com/", **overrides) -> dict:
    base = {
        "url": url,
        "title": "Example",
        "text": "Some body text",
        "links": ["https://example.com/a", "https://example.com/b"],
        "metadata": {"description": "desc", "keywords": "k1, k2"},
        "crawled_at": "2024-01-01T00:00:00+00:00",
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
    }
    base.update(overrides)
    return base


async def test_json_save_and_readback(tmp_path: Path):
    path = tmp_path / "out.jsonl"
    async with JSONStorage(path) as storage:
        await storage.save(_record("https://example.com/a"))
        await storage.save(_record("https://example.com/b"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["url"] == "https://example.com/a"
    assert parsed[1]["url"] == "https://example.com/b"
    assert parsed[0]["metadata"]["description"] == "desc"


async def test_json_handles_unicode(tmp_path: Path):
    path = tmp_path / "out.jsonl"
    async with JSONStorage(path) as storage:
        await storage.save(_record(title="Заголовок 中文 🚀"))

    line = path.read_text(encoding="utf-8")
    assert "Заголовок" in line
    assert "中文" in line
    assert "🚀" in line


async def test_json_close_idempotent(tmp_path: Path):
    storage = JSONStorage(tmp_path / "out.jsonl")
    await storage.close()
    await storage.close()


async def test_csv_save_and_readback(tmp_path: Path):
    path = tmp_path / "out.csv"
    async with CSVStorage(path) as storage:
        await storage.save(_record("https://example.com/a"))
        await storage.save(_record("https://example.com/b"))

    import csv as csvmod
    with open(path, encoding="utf-8", newline="") as f:
        reader = csvmod.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["url"] == "https://example.com/a"
    assert rows[1]["url"] == "https://example.com/b"
    # Complex fields are JSON-encoded
    assert json.loads(rows[0]["links"]) == [
        "https://example.com/a", "https://example.com/b",
    ]
    assert json.loads(rows[0]["metadata"])["description"] == "desc"


async def test_csv_explicit_columns_filter(tmp_path: Path):
    path = tmp_path / "out.csv"
    async with CSVStorage(path, columns=["url", "title"]) as storage:
        await storage.save(_record())

    import csv as csvmod
    with open(path, encoding="utf-8", newline="") as f:
        reader = csvmod.DictReader(f)
        rows = list(reader)
    assert list(rows[0].keys()) == ["url", "title"]


async def test_csv_handles_unicode(tmp_path: Path):
    path = tmp_path / "out.csv"
    async with CSVStorage(path) as storage:
        await storage.save(_record(title="русский текст"))

    text = path.read_text(encoding="utf-8")
    assert "русский текст" in text


async def test_sqlite_save_and_query(tmp_path: Path):
    path = tmp_path / "out.db"
    async with SQLiteStorage(path) as storage:
        await storage.save(_record("https://example.com/a"))
        await storage.save(_record("https://example.com/b", title="Page B"))

    async with aiosqlite.connect(path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM pages") as cur:
            count = (await cur.fetchone())[0]
        async with conn.execute(
            "SELECT url, title, status_code FROM pages ORDER BY url"
        ) as cur:
            rows = await cur.fetchall()
    assert count == 2
    assert rows[0] == ("https://example.com/a", "Example", 200)
    assert rows[1] == ("https://example.com/b", "Page B", 200)


async def test_sqlite_insert_or_replace_on_duplicate_url(tmp_path: Path):
    path = tmp_path / "out.db"
    url = "https://example.com/x"
    async with SQLiteStorage(path) as storage:
        await storage.save(_record(url, title="First"))
        await storage.save(_record(url, title="Second"))

    async with aiosqlite.connect(path) as conn:
        async with conn.execute("SELECT title FROM pages WHERE url = ?", (url,)) as cur:
            row = await cur.fetchone()
    assert row == ("Second",)


async def test_sqlite_batch_flush_on_close(tmp_path: Path):
    path = tmp_path / "out.db"
    async with SQLiteStorage(path, batch_size=1000) as storage:
        for i in range(5):
            await storage.save(_record(f"https://example.com/p{i}"))
        # Buffer not flushed yet (batch_size=1000)

    async with aiosqlite.connect(path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM pages") as cur:
            count = (await cur.fetchone())[0]
    assert count == 5


async def test_sqlite_explicit_init_db(tmp_path: Path):
    path = tmp_path / "out.db"
    storage = SQLiteStorage(path)
    await storage.init_db()
    await storage.close()

    async with aiosqlite.connect(path) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pages'"
        ) as cur:
            row = await cur.fetchone()
    assert row == ("pages",)


async def test_sqlite_links_and_metadata_are_json(tmp_path: Path):
    path = tmp_path / "out.db"
    async with SQLiteStorage(path) as storage:
        await storage.save(_record())

    async with aiosqlite.connect(path) as conn:
        async with conn.execute(
            "SELECT links_json, metadata_json FROM pages"
        ) as cur:
            row = await cur.fetchone()
    assert json.loads(row[0]) == [
        "https://example.com/a", "https://example.com/b",
    ]
    assert json.loads(row[1])["description"] == "desc"


async def test_sqlite_close_idempotent(tmp_path: Path):
    storage = SQLiteStorage(tmp_path / "out.db")
    await storage.close()
    await storage.close()


async def test_sqlite_rejects_record_without_url(tmp_path: Path):
    path = tmp_path / "out.db"
    storage = SQLiteStorage(path, max_save_retries=0)
    try:
        with pytest.raises(ValueError):
            await storage.save({"title": "no url here"})
    finally:
        await storage.close()


class _FailingStorage(DataStorage):
    """Counts attempts; fails the first N times before succeeding."""

    def __init__(self, fail_n: int, **kwargs):
        super().__init__(**kwargs)
        self._fail_n = fail_n
        self.attempts = 0
        self.saved: list[dict] = []

    async def _do_save(self, data: dict) -> None:
        self.attempts += 1
        if self.attempts <= self._fail_n:
            raise RuntimeError("transient")
        self.saved.append(data)

    async def close(self) -> None:
        pass


async def test_save_retries_then_succeeds():
    storage = _FailingStorage(fail_n=2, max_save_retries=3, retry_backoff=0.01)
    await storage.save({"x": 1})
    assert storage.attempts == 3
    assert storage.saved == [{"x": 1}]


async def test_save_raises_after_retries_exhausted():
    storage = _FailingStorage(fail_n=10, max_save_retries=2, retry_backoff=0.01)
    with pytest.raises(RuntimeError):
        await storage.save({"x": 1})
    assert storage.attempts == 3


def test_invalid_max_save_retries():
    with pytest.raises(ValueError):
        JSONStorage("nowhere", max_save_retries=-1)


def test_invalid_retry_backoff():
    with pytest.raises(ValueError):
        JSONStorage("nowhere", retry_backoff=0)


def test_invalid_batch_size(tmp_path: Path):
    with pytest.raises(ValueError):
        SQLiteStorage(tmp_path / "out.db", batch_size=0)
