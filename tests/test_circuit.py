import asyncio

import pytest

from crawler import CircuitBreaker


def test_starts_closed():
    cb = CircuitBreaker()
    assert cb.is_open("a.com") is False


def test_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)
    assert cb.is_open("a.com") is False
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is False
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is False
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is True


def test_record_success_resets_failures():
    cb = CircuitBreaker(failure_threshold=3)
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    cb.record_success("a.com")
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is False


def test_record_success_closes_open_circuit():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is True
    cb.record_success("a.com")
    assert cb.is_open("a.com") is False


async def test_recovers_after_timeout():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is True
    await asyncio.sleep(0.15)
    assert cb.is_open("a.com") is False


def test_isolation_between_keys():
    cb = CircuitBreaker(failure_threshold=2)
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is True
    assert cb.is_open("b.com") is False
    cb.record_failure("b.com")
    assert cb.is_open("b.com") is False


def test_already_open_does_not_recount():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    # Subsequent failures while open should not reset the timer
    cb.record_failure("a.com")
    cb.record_failure("a.com")
    assert cb.is_open("a.com") is True


def test_invalid_failure_threshold():
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)


def test_invalid_recovery_timeout():
    with pytest.raises(ValueError):
        CircuitBreaker(recovery_timeout=0)
