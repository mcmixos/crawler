import asyncio

import pytest

from crawler import (
    NetworkError,
    PermanentError,
    RetryStrategy,
    TransientError,
)


async def test_first_call_succeeds_no_retry():
    strategy = RetryStrategy(max_retries=3, backoff_base=0.01)

    async def succeed():
        return "ok"

    result = await strategy.execute_with_retry(succeed)
    assert result == "ok"
    stats = strategy.get_stats()
    assert stats["attempts_total"] == 1
    assert stats["retries_total"] == 0
    assert stats["successes_after_retry"] == 0


async def test_retries_until_success():
    strategy = RetryStrategy(max_retries=3, backoff_base=0.01)
    calls = {"n": 0}

    async def fail_then_succeed():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientError("not yet")
        return "ok"

    result = await strategy.execute_with_retry(fail_then_succeed)
    assert result == "ok"
    stats = strategy.get_stats()
    assert stats["attempts_total"] == 3
    assert stats["retries_total"] == 2
    assert stats["successes_after_retry"] == 1


async def test_exhausts_retries_and_raises():
    strategy = RetryStrategy(max_retries=2, backoff_base=0.01)

    async def always_fails():
        raise TransientError("nope")

    with pytest.raises(TransientError):
        await strategy.execute_with_retry(always_fails)
    stats = strategy.get_stats()
    assert stats["attempts_total"] == 3
    assert stats["retries_total"] == 2
    assert stats["failures_after_retry"] == 1


async def test_does_not_retry_non_listed_error():
    strategy = RetryStrategy(
        max_retries=3, backoff_base=0.01, retry_on=[TransientError]
    )

    async def fails_with_permanent():
        raise PermanentError("bad")

    with pytest.raises(PermanentError):
        await strategy.execute_with_retry(fails_with_permanent)
    stats = strategy.get_stats()
    assert stats["attempts_total"] == 1
    assert stats["retries_total"] == 0


async def test_default_retries_transient_and_network():
    strategy = RetryStrategy(max_retries=2, backoff_base=0.01)
    calls = {"n": 0}

    async def fail_with_network():
        calls["n"] += 1
        if calls["n"] < 2:
            raise NetworkError("flaky net")
        return "ok"

    assert await strategy.execute_with_retry(fail_with_network) == "ok"


async def test_exponential_backoff_grows():
    strategy = RetryStrategy(
        max_retries=3, backoff_base=0.01, backoff_factor=2.0
    )

    async def always_fails():
        raise TransientError("nope")

    with pytest.raises(TransientError):
        await strategy.execute_with_retry(always_fails)

    stats = strategy.get_stats()
    # 3 retries: 0.01 + 0.02 + 0.04 = 0.07s total
    assert stats["retries_total"] == 3
    assert stats["avg_retry_wait_ms"] > 0
    # Average should be about 23ms ((10+20+40)/3)
    assert 15 < stats["avg_retry_wait_ms"] < 35


async def test_backoff_capped_at_max():
    strategy = RetryStrategy(
        max_retries=2, backoff_base=10.0, backoff_factor=10.0, max_backoff=0.05
    )

    async def always_fails():
        raise TransientError("nope")

    with pytest.raises(TransientError):
        await strategy.execute_with_retry(always_fails)

    stats = strategy.get_stats()
    # All waits capped at 0.05s = 50ms
    assert stats["avg_retry_wait_ms"] == pytest.approx(50.0, rel=0.01)


async def test_passes_args_and_kwargs_through():
    strategy = RetryStrategy(max_retries=0)

    async def echo(a, b, c=None):
        return (a, b, c)

    assert await strategy.execute_with_retry(echo, 1, 2, c=3) == (1, 2, 3)


async def test_stats_track_error_types():
    strategy = RetryStrategy(max_retries=2, backoff_base=0.01)

    async def transient_then_perm():
        if strategy.get_stats()["attempts_total"] < 3:
            raise TransientError("a")
        raise PermanentError("b")

    with pytest.raises(PermanentError):
        await strategy.execute_with_retry(transient_then_perm)

    counts = strategy.get_stats()["error_counts"]
    assert counts.get("TransientError", 0) == 2
    assert counts.get("PermanentError", 0) == 1


def test_invalid_max_retries():
    with pytest.raises(ValueError):
        RetryStrategy(max_retries=-1)


def test_invalid_backoff_factor():
    with pytest.raises(ValueError):
        RetryStrategy(backoff_factor=0)


def test_invalid_backoff_base():
    with pytest.raises(ValueError):
        RetryStrategy(backoff_base=0)


def test_invalid_max_backoff():
    with pytest.raises(ValueError):
        RetryStrategy(max_backoff=0)
