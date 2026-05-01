import asyncio

import pytest

from crawler import SemaphoreManager


async def _track_concurrency(sm: SemaphoreManager, urls: list[str], hold: float = 0.05):
    in_flight: list[str] = []
    max_total = 0
    per_host_max: dict[str, int] = {}
    per_host_now: dict[str, int] = {}

    async def task(url: str) -> None:
        nonlocal max_total
        host = url.split("/")[2].lower()
        async with sm.acquire(url):
            in_flight.append(url)
            per_host_now[host] = per_host_now.get(host, 0) + 1
            per_host_max[host] = max(per_host_max.get(host, 0), per_host_now[host])
            max_total = max(max_total, len(in_flight))
            await asyncio.sleep(hold)
            in_flight.remove(url)
            per_host_now[host] -= 1

    await asyncio.gather(*(task(u) for u in urls))
    return max_total, per_host_max


async def test_global_limit_enforced():
    sm = SemaphoreManager(max_concurrent=2, max_per_host=10)
    urls = [f"https://h{i}.test/" for i in range(6)]
    max_total, _ = await _track_concurrency(sm, urls)
    assert max_total <= 2


async def test_per_host_limit_enforced():
    sm = SemaphoreManager(max_concurrent=10, max_per_host=2)
    urls = [f"https://example.test/p{i}" for i in range(6)]
    _, per_host_max = await _track_concurrency(sm, urls)
    assert per_host_max["example.test"] <= 2


async def test_different_hosts_independent():
    sm = SemaphoreManager(max_concurrent=10, max_per_host=1)
    urls = [f"https://h{i}.test/" for i in range(5)]
    max_total, per_host_max = await _track_concurrency(sm, urls)
    assert max_total == 5
    assert all(v <= 1 for v in per_host_max.values())


async def test_active_counter_zero_when_idle():
    sm = SemaphoreManager()
    assert sm.active == 0


async def test_active_counter_tracks_in_flight():
    sm = SemaphoreManager(max_concurrent=10, max_per_host=10)
    seen: list[int] = []

    async def task(url: str) -> None:
        async with sm.acquire(url):
            seen.append(sm.active)
            await asyncio.sleep(0.05)

    await asyncio.gather(*(task(f"https://h.test/{i}") for i in range(3)))
    assert sm.active == 0
    assert max(seen) == 3


async def test_host_case_insensitive():
    sm = SemaphoreManager(max_concurrent=10, max_per_host=1)
    urls = ["https://EXAMPLE.test/a", "https://example.test/b"]
    _, per_host_max = await _track_concurrency(sm, urls)
    assert per_host_max == {"example.test": 1}


def test_invalid_max_concurrent_rejected():
    with pytest.raises(ValueError):
        SemaphoreManager(max_concurrent=0)


def test_invalid_max_per_host_rejected():
    with pytest.raises(ValueError):
        SemaphoreManager(max_per_host=0)
