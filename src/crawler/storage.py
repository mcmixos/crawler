import asyncio
import csv
import io
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import aiofiles
import aiosqlite

logger = logging.getLogger(__name__)


class DataStorage(ABC):
    """Abstract storage backend with built-in retry on save failures."""

    def __init__(
        self,
        max_save_retries: int = 2,
        retry_backoff: float = 0.1,
    ) -> None:
        if max_save_retries < 0:
            raise ValueError("max_save_retries must be >= 0")
        if retry_backoff <= 0:
            raise ValueError("retry_backoff must be > 0")
        self._max_save_retries = max_save_retries
        self._retry_backoff = retry_backoff

    async def save(self, data: dict) -> None:
        """Save a single record. Retries internally; raises only after all retries fail."""
        for attempt in range(self._max_save_retries + 1):
            try:
                await self._do_save(data)
                return
            except Exception as exc:
                if attempt >= self._max_save_retries:
                    logger.error(
                        "save failed after %d attempt(s): %s", attempt + 1, exc,
                    )
                    raise
                wait = self._retry_backoff * (2 ** attempt)
                logger.warning(
                    "save retry %d/%d after %.2fs: %s",
                    attempt + 1, self._max_save_retries, wait, exc,
                )
                await asyncio.sleep(wait)

    @abstractmethod
    async def _do_save(self, data: dict) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...

    async def __aenter__(self) -> "DataStorage":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()


class JSONStorage(DataStorage):
    """Append-only JSON Lines (NDJSON) storage. One JSON object per line."""

    def __init__(
        self,
        path: "str | Path",
        max_save_retries: int = 2,
        retry_backoff: float = 0.1,
    ) -> None:
        super().__init__(max_save_retries, retry_backoff)
        self._path = Path(path)
        self._file = None
        self._lock = asyncio.Lock()

    async def _ensure_open(self) -> None:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = await aiofiles.open(self._path, "a", encoding="utf-8")

    async def _do_save(self, data: dict) -> None:
        async with self._lock:
            await self._ensure_open()
            line = json.dumps(data, ensure_ascii=False, default=str) + "\n"
            await self._file.write(line)
            await self._file.flush()

    async def close(self) -> None:
        async with self._lock:
            if self._file is not None:
                await self._file.close()
                self._file = None


class CSVStorage(DataStorage):
    """Async CSV storage. Headers auto-detected from the first save (or passed explicitly).

    Complex values (list, dict) are JSON-encoded into the cell.
    Always opens in write mode - existing files are overwritten.
    """

    def __init__(
        self,
        path: "str | Path",
        columns: Optional[list[str]] = None,
        encoding: str = "utf-8",
        max_save_retries: int = 2,
        retry_backoff: float = 0.1,
    ) -> None:
        super().__init__(max_save_retries, retry_backoff)
        self._path = Path(path)
        self._columns = list(columns) if columns is not None else None
        self._encoding = encoding
        self._file = None
        self._header_written = False
        self._lock = asyncio.Lock()

    async def _ensure_open(self) -> None:
        if self._file is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._file = await aiofiles.open(
                self._path, "w", encoding=self._encoding, newline="",
            )

    async def _do_save(self, data: dict) -> None:
        async with self._lock:
            await self._ensure_open()
            if self._columns is None:
                self._columns = list(data.keys())
            if not self._header_written:
                buf = io.StringIO()
                writer = csv.DictWriter(
                    buf, fieldnames=self._columns, extrasaction="ignore",
                )
                writer.writeheader()
                await self._file.write(buf.getvalue())
                self._header_written = True
            row = {k: self._serialize(v) for k, v in data.items() if k in self._columns}
            buf = io.StringIO()
            writer = csv.DictWriter(
                buf, fieldnames=self._columns, extrasaction="ignore",
            )
            writer.writerow(row)
            await self._file.write(buf.getvalue())
            await self._file.flush()

    @staticmethod
    def _serialize(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    async def close(self) -> None:
        async with self._lock:
            if self._file is not None:
                await self._file.close()
                self._file = None


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    title TEXT,
    text TEXT,
    links_json TEXT,
    metadata_json TEXT,
    crawled_at TEXT,
    status_code INTEGER,
    content_type TEXT
)
"""

_CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at)"
)

_INSERT_SQL = """
INSERT OR REPLACE INTO pages
(url, title, text, links_json, metadata_json, crawled_at, status_code, content_type)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteStorage(DataStorage):
    """SQLite storage with batch inserts for performance.

    Buffers up to `batch_size` records before flushing to disk; final flush on close.
    """

    def __init__(
        self,
        path: "str | Path",
        batch_size: int = 100,
        max_save_retries: int = 2,
        retry_backoff: float = 0.1,
    ) -> None:
        super().__init__(max_save_retries, retry_backoff)
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._path = Path(path)
        self._batch_size = batch_size
        self._conn: Optional[aiosqlite.Connection] = None
        self._buffer: list[dict] = []
        self._lock = asyncio.Lock()

    async def init_db(self) -> None:
        """Create the schema explicitly. Idempotent. Lazy init also works on first save."""
        async with self._lock:
            await self._ensure_open_locked()

    async def _ensure_open_locked(self) -> None:
        if self._conn is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self._path)
            await self._conn.execute(_CREATE_TABLE_SQL)
            await self._conn.execute(_CREATE_INDEX_SQL)
            await self._conn.commit()

    async def _do_save(self, data: dict) -> None:
        if not data.get("url"):
            raise ValueError("data must include a non-empty 'url'")
        async with self._lock:
            await self._ensure_open_locked()
            self._buffer.append(data)
            if len(self._buffer) >= self._batch_size:
                await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer or self._conn is None:
            return
        rows = [self._row_from_data(d) for d in self._buffer]
        await self._conn.executemany(_INSERT_SQL, rows)
        await self._conn.commit()
        self._buffer.clear()

    @staticmethod
    def _row_from_data(d: dict) -> tuple:
        url = d.get("url")
        if not url:
            raise ValueError("data must include a non-empty 'url'")
        return (
            url,
            d.get("title"),
            d.get("text"),
            json.dumps(d.get("links", []), ensure_ascii=False),
            json.dumps(d.get("metadata", {}), ensure_ascii=False),
            d.get("crawled_at"),
            d.get("status_code"),
            d.get("content_type"),
        )

    async def close(self) -> None:
        async with self._lock:
            if self._conn is not None:
                await self._flush_locked()
                await self._conn.close()
                self._conn = None
