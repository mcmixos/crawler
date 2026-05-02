from pathlib import Path

import pytest

from crawler import (
    CrawlerConfig,
    CrawlerSettings,
    FilterSettings,
    LoggingSettings,
    StorageSettings,
)


def test_defaults():
    config = CrawlerConfig()
    assert config.max_pages == 100
    assert config.start_urls == []
    assert config.sitemap_urls == []
    assert config.crawler.max_concurrent == 10
    assert config.crawler.respect_robots is False
    assert config.filters.same_domain_only is False
    assert config.storage.type is None
    assert config.logging.level == "INFO"


def test_from_dict_partial():
    config = CrawlerConfig.from_dict({
        "start_urls": ["https://example.com"],
        "max_pages": 50,
        "crawler": {"max_concurrent": 20, "respect_robots": True},
    })
    assert config.start_urls == ["https://example.com"]
    assert config.max_pages == 50
    assert config.crawler.max_concurrent == 20
    assert config.crawler.respect_robots is True
    assert config.crawler.max_depth == 3


def test_from_dict_full():
    data = {
        "start_urls": ["https://a.com", "https://b.com"],
        "sitemap_urls": ["https://a.com/sitemap.xml"],
        "max_pages": 200,
        "crawler": {
            "max_concurrent": 5,
            "max_per_host": 2,
            "max_depth": 1,
            "requests_per_second": 1.5,
            "respect_robots": True,
            "user_agent": "Bot/1.0",
        },
        "filters": {
            "same_domain_only": True,
            "exclude_patterns": [r"\.pdf$"],
        },
        "storage": {
            "type": "sqlite",
            "path": "out.db",
            "batch_size": 50,
        },
        "logging": {
            "level": "DEBUG",
            "file": "logs/x.log",
        },
    }
    config = CrawlerConfig.from_dict(data)
    assert config.crawler.requests_per_second == 1.5
    assert config.crawler.user_agent == "Bot/1.0"
    assert config.filters.exclude_patterns == [r"\.pdf$"]
    assert config.storage.type == "sqlite"
    assert config.storage.batch_size == 50
    assert config.logging.level == "DEBUG"
    assert config.logging.file == "logs/x.log"


def test_from_yaml(tmp_path: Path):
    yaml_text = """\
start_urls:
  - https://example.com
max_pages: 25
crawler:
  max_concurrent: 4
filters:
  same_domain_only: true
"""
    path = tmp_path / "config.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    config = CrawlerConfig.from_yaml(path)
    assert config.start_urls == ["https://example.com"]
    assert config.max_pages == 25
    assert config.crawler.max_concurrent == 4
    assert config.filters.same_domain_only is True


def test_from_empty_yaml(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("", encoding="utf-8")
    config = CrawlerConfig.from_yaml(path)
    assert config.max_pages == 100
    assert config.start_urls == []


def test_dataclasses_are_separate_instances():
    config1 = CrawlerConfig()
    config2 = CrawlerConfig()
    config1.start_urls.append("x")
    assert config2.start_urls == []
