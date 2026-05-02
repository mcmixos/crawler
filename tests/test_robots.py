import pytest

from crawler import RobotsParser


def make_fetcher(text):
    """Build a fetcher that always returns the given text. Records called URLs."""
    calls = []

    async def fetcher(url):
        calls.append(url)
        return text

    fetcher.calls = calls
    return fetcher


async def test_fetch_robots_returns_summary():
    fetcher = make_fetcher("User-agent: *\nDisallow: /admin\nCrawl-delay: 2")
    parser = RobotsParser(fetcher)
    info = await parser.fetch_robots("https://example.com")
    assert info["host"] == "https://example.com"
    assert info["fetched"] is True
    assert info["crawl_delay"] == 2.0


async def test_fetch_robots_uses_correct_url():
    fetcher = make_fetcher("User-agent: *\nDisallow: /")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com/some/path")
    assert fetcher.calls == ["https://example.com/robots.txt"]


async def test_can_fetch_allowed_path():
    fetcher = make_fetcher("User-agent: *\nDisallow: /admin")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.can_fetch("https://example.com/page") is True


async def test_can_fetch_disallowed_path():
    fetcher = make_fetcher("User-agent: *\nDisallow: /admin")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.can_fetch("https://example.com/admin/users") is False


async def test_can_fetch_specific_user_agent():
    robots = (
        "User-agent: BadBot\nDisallow: /\n\n"
        "User-agent: *\nAllow: /\n"
    )
    fetcher = make_fetcher(robots)
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.can_fetch("https://example.com/page", "BadBot") is False
    assert parser.can_fetch("https://example.com/page", "GoodBot") is True


async def test_get_crawl_delay_returns_value():
    fetcher = make_fetcher("User-agent: *\nCrawl-delay: 5")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.get_crawl_delay("https://example.com") == 5.0


async def test_get_crawl_delay_returns_zero_when_unset():
    fetcher = make_fetcher("User-agent: *\nDisallow: /admin")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.get_crawl_delay("https://example.com") == 0.0


async def test_caching_skips_second_fetch():
    fetcher = make_fetcher("User-agent: *\nDisallow: /admin")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    await parser.fetch_robots("https://example.com/other")
    assert len(fetcher.calls) == 1


async def test_no_robots_allows_all():
    fetcher = make_fetcher(None)
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://example.com")
    assert parser.can_fetch("https://example.com/anything") is True


async def test_can_fetch_before_load_returns_true():
    fetcher = make_fetcher("Disallow: /")
    parser = RobotsParser(fetcher)
    assert parser.can_fetch("https://example.com/anything") is True


async def test_invalid_url_returns_empty_summary():
    fetcher = make_fetcher("Disallow: /")
    parser = RobotsParser(fetcher)
    info = await parser.fetch_robots("not-a-url")
    assert info["fetched"] is False
    assert len(fetcher.calls) == 0


async def test_fetcher_exception_treated_as_no_robots():
    async def failing_fetcher(url):
        raise RuntimeError("network down")

    parser = RobotsParser(failing_fetcher)
    info = await parser.fetch_robots("https://example.com")
    assert info["fetched"] is False
    assert parser.can_fetch("https://example.com/anything") is True


async def test_host_origin_case_insensitive():
    fetcher = make_fetcher("Disallow: /admin")
    parser = RobotsParser(fetcher)
    await parser.fetch_robots("https://EXAMPLE.com")
    await parser.fetch_robots("https://example.com")
    assert len(fetcher.calls) == 1


async def test_get_crawl_delay_unknown_domain_returns_zero():
    fetcher = make_fetcher("Disallow: /")
    parser = RobotsParser(fetcher)
    # never called fetch_robots
    assert parser.get_crawl_delay("https://example.com") == 0.0
