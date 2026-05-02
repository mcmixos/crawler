import pytest

from crawler._utils import BoundedDict


def test_basic_set_get():
    d = BoundedDict(3)
    d["a"] = 1
    d["b"] = 2
    assert d["a"] == 1
    assert d["b"] == 2


def test_evicts_oldest_on_overflow():
    d = BoundedDict(3)
    d["a"] = 1
    d["b"] = 2
    d["c"] = 3
    d["d"] = 4
    assert "a" not in d
    assert list(d.keys()) == ["b", "c", "d"]


def test_update_existing_does_not_evict():
    d = BoundedDict(2)
    d["a"] = 1
    d["b"] = 2
    d["a"] = 99
    assert "b" in d
    assert d["a"] == 99
    assert list(d.keys()) == ["a", "b"]


def test_size_one():
    d = BoundedDict(1)
    d["a"] = 1
    d["b"] = 2
    assert "a" not in d
    assert d["b"] == 2


def test_invalid_max_size():
    with pytest.raises(ValueError):
        BoundedDict(0)


def test_works_as_dict():
    d = BoundedDict(10)
    d["a"] = 1
    d["b"] = 2
    assert len(d) == 2
    assert dict(d) == {"a": 1, "b": 2}
    del d["a"]
    assert "a" not in d


def test_iteration_order_preserved():
    d = BoundedDict(5)
    for ch in "abcde":
        d[ch] = ord(ch)
    assert list(d.keys()) == list("abcde")
    d["f"] = ord("f")
    assert list(d.keys()) == list("bcdef")
