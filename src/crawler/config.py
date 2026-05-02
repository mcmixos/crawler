from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class CrawlerSettings:
    max_concurrent: int = 10
    max_per_host: int = 5
    max_depth: int = 3
    requests_per_second: Optional[float] = None
    min_delay: float = 0.0
    jitter: float = 0.0
    respect_robots: bool = False
    max_retries: int = 0
    backoff_base: float = 1.0
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: Optional[float] = None
    user_agent: str = "AsyncCrawler/0.1"


@dataclass
class FilterSettings:
    same_domain_only: bool = False
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class StorageSettings:
    type: Optional[str] = None
    path: Optional[str] = None
    batch_size: int = 100


@dataclass
class LoggingSettings:
    level: str = "INFO"
    file: Optional[str] = None
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class CrawlerConfig:
    crawler: CrawlerSettings = field(default_factory=CrawlerSettings)
    filters: FilterSettings = field(default_factory=FilterSettings)
    storage: StorageSettings = field(default_factory=StorageSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    start_urls: list[str] = field(default_factory=list)
    sitemap_urls: list[str] = field(default_factory=list)
    max_pages: int = 100

    @classmethod
    def from_yaml(cls, path: "str | Path") -> "CrawlerConfig":
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlerConfig":
        return _build_dataclass(cls, data or {})


def _build_dataclass(cls, data: dict):
    if not is_dataclass(cls):
        return data
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        if is_dataclass(f.type) and isinstance(value, dict):
            kwargs[f.name] = _build_dataclass(f.type, value)
        elif isinstance(f.default_factory, type) and isinstance(value, dict):
            # Field has a dataclass default_factory; recurse if the type is dataclass.
            inner = f.default_factory().__class__
            if is_dataclass(inner):
                kwargs[f.name] = _build_dataclass(inner, value)
            else:
                kwargs[f.name] = value
        else:
            kwargs[f.name] = value
    return cls(**kwargs)
