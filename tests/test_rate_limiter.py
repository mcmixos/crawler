import asyncio
import time

import pytest

from crawler import RateLimiter


async def test_first_acquire_does_not_wait():
    limiter = RateLimiter(requests_per_second=1.0)
    start = time.monotonic()
    await limiter.acquire("a.com")
    assert time.monotonic() - start < 0.05


async def test_second_acquire_waits_for_interval():
    limiter = RateLimiter(requests_per_second=10.0)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("a.com")
    elapsed = time.monotonic() - start
    assert 0.08 <= elapsed <= 0.25


async def test_per_domain_independent():
    limiter = RateLimiter(requests_per_second=10.0, per_domain=True)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("b.com")
    assert time.monotonic() - start < 0.05


async def test_global_mode_serializes_across_domains():
    limiter = RateLimiter(requests_per_second=10.0, per_domain=False)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("b.com")
    assert time.monotonic() - start >= 0.08


async def test_concurrent_acquires_serialize_for_same_domain():
    limiter = RateLimiter(requests_per_second=10.0)
    start = time.monotonic()
    await asyncio.gather(*(limiter.acquire("a.com") for _ in range(3)))
    elapsed = time.monotonic() - start
    assert 0.18 <= elapsed <= 0.4


async def test_min_delay_floors_rate():
    limiter = RateLimiter(requests_per_second=100.0, min_delay=0.1)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("a.com")
    assert time.monotonic() - start >= 0.08


async def test_jitter_adds_extra_delay():
    limiter = RateLimiter(requests_per_second=10.0, jitter=0.1)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("a.com")
    elapsed = time.monotonic() - start
    assert 0.08 <= elapsed <= 0.3


async def test_set_domain_interval_overrides_for_one_domain():
    limiter = RateLimiter(requests_per_second=100.0)
    limiter.set_domain_interval("slow.com", 0.2)
    await limiter.acquire("slow.com")
    start = time.monotonic()
    await limiter.acquire("slow.com")
    assert time.monotonic() - start >= 0.18


async def test_set_domain_interval_does_not_lower_below_base():
    limiter = RateLimiter(requests_per_second=10.0)
    limiter.set_domain_interval("a.com", 0.05)
    await limiter.acquire("a.com")
    start = time.monotonic()
    await limiter.acquire("a.com")
    assert time.monotonic() - start >= 0.08


async def test_acquire_without_domain_uses_global_slot():
    limiter = RateLimiter(requests_per_second=10.0)
    await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()
    assert time.monotonic() - start >= 0.08


def test_invalid_rps_rejected():
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=0)
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=-1)


def test_invalid_min_delay_rejected():
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=1, min_delay=-1)


def test_invalid_jitter_rejected():
    with pytest.raises(ValueError):
        RateLimiter(requests_per_second=1, jitter=-1)


def test_set_domain_interval_negative_rejected():
    limiter = RateLimiter(requests_per_second=1)
    with pytest.raises(ValueError):
        limiter.set_domain_interval("a.com", -1)
