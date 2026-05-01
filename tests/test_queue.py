from crawler import CrawlerQueue


def test_add_url_returns_true_for_new_url():
    q = CrawlerQueue()
    assert q.add_url("https://x.com") is True


def test_add_url_dedupes():
    q = CrawlerQueue()
    assert q.add_url("https://x.com") is True
    assert q.add_url("https://x.com") is False
    assert q.get_stats()["queued"] == 1


async def test_get_next_returns_higher_priority_first():
    q = CrawlerQueue()
    q.add_url("low", priority=1)
    q.add_url("high", priority=10)
    q.add_url("mid", priority=5)
    assert await q.get_next() == "high"
    assert await q.get_next() == "mid"
    assert await q.get_next() == "low"


async def test_get_next_fifo_within_same_priority():
    q = CrawlerQueue()
    q.add_url("a")
    q.add_url("b")
    q.add_url("c")
    assert await q.get_next() == "a"
    assert await q.get_next() == "b"
    assert await q.get_next() == "c"


async def test_get_next_returns_none_when_empty():
    q = CrawlerQueue()
    assert await q.get_next() is None


async def test_get_next_returns_none_after_exhaustion():
    q = CrawlerQueue()
    q.add_url("only")
    assert await q.get_next() == "only"
    assert await q.get_next() is None


def test_mark_processed_stores_data():
    q = CrawlerQueue()
    q.add_url("u1")
    q.mark_processed("u1", {"foo": "bar"})
    assert q.processed_urls["u1"] == {"foo": "bar"}


def test_mark_processed_default_data():
    q = CrawlerQueue()
    q.add_url("u1")
    q.mark_processed("u1")
    assert q.processed_urls["u1"] == {}


def test_mark_failed_stores_error():
    q = CrawlerQueue()
    q.add_url("u1")
    q.mark_failed("u1", "boom")
    assert q.failed_urls["u1"] == "boom"


def test_get_stats_reports_correct_counts():
    q = CrawlerQueue()
    q.add_url("u1")
    q.add_url("u2")
    q.add_url("u3")
    q.mark_processed("u1")
    q.mark_failed("u2", "err")
    stats = q.get_stats()
    assert stats["queued"] == 3
    assert stats["visited"] == 3
    assert stats["processed"] == 1
    assert stats["failed"] == 1


async def test_get_stats_queued_drops_after_pop():
    q = CrawlerQueue()
    q.add_url("u1")
    q.add_url("u2")
    assert q.get_stats()["queued"] == 2
    await q.get_next()
    assert q.get_stats()["queued"] == 1


def test_depth_tracking():
    q = CrawlerQueue()
    q.add_url("u1", depth=0)
    q.add_url("u2", depth=3)
    assert q.get_depth("u1") == 0
    assert q.get_depth("u2") == 3


def test_get_depth_unknown_returns_zero():
    q = CrawlerQueue()
    assert q.get_depth("never-added") == 0


async def test_visited_urls_persists_after_pop():
    q = CrawlerQueue()
    q.add_url("u1")
    await q.get_next()
    assert "u1" in q.visited_urls


def test_empty_method():
    q = CrawlerQueue()
    assert q.empty() is True
    q.add_url("u")
    assert q.empty() is False
