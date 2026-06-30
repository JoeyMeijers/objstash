"""Tests for transparent mutation persistence (phase 3)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from objstash import Stash


@pytest.fixture
def stash() -> Iterator[Stash]:
    instance = Stash(":memory:")
    yield instance
    instance.close()


# -- lists ------------------------------------------------------------------


def test_list_append_persists(stash: Stash) -> None:
    stash.tags = []
    stash.tags.append("x")
    stash.tags.append("y")
    assert stash.tags == ["x", "y"]


def test_list_all_mutators_persist(stash: Stash) -> None:
    stash.nums = [3, 1, 2]
    stash.nums.extend([5, 4])
    stash.nums.insert(0, 0)
    stash.nums.remove(3)
    stash.nums.sort()
    assert stash.nums == [0, 1, 2, 4, 5]
    stash.nums.reverse()
    assert stash.nums == [5, 4, 2, 1, 0]
    popped = stash.nums.pop()
    assert popped == 0
    assert stash.nums == [5, 4, 2, 1]
    stash.nums[0] = 9
    assert stash.nums == [9, 4, 2, 1]
    del stash.nums[1]
    assert stash.nums == [9, 2, 1]
    stash.nums.clear()
    assert stash.nums == []


def test_list_iadd_and_imul_persist(stash: Stash) -> None:
    stash.a = [1]
    stash.a += [2, 3]
    assert stash.a == [1, 2, 3]
    stash.b = [0]
    stash.b *= 3
    assert stash.b == [0, 0, 0]


def test_list_persists_to_disk(tmp_path: Path) -> None:
    db = str(tmp_path / "p.db")
    first = Stash(db)
    first.tags = []
    first.tags.append("saved")
    first.close()

    second = Stash(db)
    assert second.tags == ["saved"]
    second.close()


# -- dicts ------------------------------------------------------------------


def test_dict_setitem_persists(stash: Stash) -> None:
    stash.config = {}
    stash.config["theme"] = "dark"
    stash.config["lang"] = "en"
    assert stash.config == {"theme": "dark", "lang": "en"}


def test_dict_mutators_persist(stash: Stash) -> None:
    stash.d = {"a": 1}
    stash.d.update({"b": 2, "c": 3})
    assert stash.d == {"a": 1, "b": 2, "c": 3}
    assert stash.d.pop("a") == 1
    assert "a" not in stash.d
    stash.d.setdefault("z", 9)
    assert stash.d["z"] == 9
    stash.d.setdefault("z", 100)  # existing, unchanged
    assert stash.d["z"] == 9
    del stash.d["b"]
    assert stash.d == {"c": 3, "z": 9}
    stash.d |= {"w": 0}
    assert stash.d["w"] == 0
    stash.d.clear()
    assert stash.d == {}


# -- sets -------------------------------------------------------------------


def test_set_mutators_persist(stash: Stash) -> None:
    stash.s = {1, 2}
    stash.s.add(3)
    stash.s.discard(1)
    assert stash.s == {2, 3}
    stash.s.update({4, 5})
    assert stash.s == {2, 3, 4, 5}
    stash.s -= {4, 5}
    assert stash.s == {2, 3}
    stash.s |= {9}
    assert 9 in stash.s
    stash.s.remove(9)
    assert 9 not in stash.s
    stash.s.clear()
    assert stash.s == set()


# -- nested -----------------------------------------------------------------


def test_nested_container_mutation_persists(stash: Stash) -> None:
    stash.cfg = {"users": [{"name": "a"}]}
    stash.cfg["users"][0]["name"] = "b"
    stash.cfg["users"].append({"name": "c"})
    assert stash.cfg == {"users": [{"name": "b"}, {"name": "c"}]}


def test_deeply_nested_list_in_dict_in_list(stash: Stash) -> None:
    stash.data = [{"items": []}]
    stash.data[0]["items"].append(42)
    assert stash.data == [{"items": [42]}]


def test_container_inside_namespace_persists(stash: Stash) -> None:
    stash.profile.tags = []
    stash.profile.tags.append("admin")
    assert stash.profile.tags == ["admin"]
    assert stash.profile.to_dict() == {"tags": ["admin"]}


# -- aliasing & snapshots ---------------------------------------------------


def test_alias_from_same_read_shares_state(stash: Stash) -> None:
    stash.tags = []
    alias = stash.tags
    alias.append("x")
    assert stash.tags == ["x"]


def test_separate_reads_are_independent_snapshots(stash: Stash) -> None:
    stash.tags = ["a"]
    first = stash.tags
    stash.tags = ["b"]  # overwrite via a new assignment
    first.append("c")  # mutates the old snapshot, rewriting the key
    # last write wins: the snapshot's save rewrote the whole value
    assert stash.tags == ["a", "c"]


# -- interop ----------------------------------------------------------------


def test_proxy_is_equal_to_plain_container(stash: Stash) -> None:
    stash.tags = ["a", "b"]
    assert stash.tags == ["a", "b"]
    assert list(stash.tags) == ["a", "b"]
    assert len(stash.tags) == 2
    assert "a" in stash.tags


def test_assigning_a_proxy_stores_its_value(stash: Stash) -> None:
    stash.a = [1, 2, 3]
    stash.b = stash.a  # assigning a proxy must store the underlying list
    assert stash.b == [1, 2, 3]
    stash.a.append(4)
    assert stash.b == [1, 2, 3]  # independent copy, not a live link


def test_dict_values_and_items_are_wrapped(stash: Stash) -> None:
    stash.cfg = {"a": [1]}
    for value in stash.cfg.values():
        value.append(2)
    assert stash.cfg == {"a": [1, 2]}


def test_list_iteration_yields_mutable_children(stash: Stash) -> None:
    stash.rows = [[1], [2]]
    for row in stash.rows:
        row.append(0)
    assert stash.rows == [[1, 0], [2, 0]]


def test_to_dict_returns_plain_containers(stash: Stash) -> None:
    stash.cfg = {"tags": [1, 2]}
    plain = stash.to_dict()
    assert plain == {"cfg": {"tags": [1, 2]}}
    assert type(plain["cfg"]) is dict
    assert type(plain["cfg"]["tags"]) is list


def test_setdefault_returns_mutable_container(stash: Stash) -> None:
    tags = stash.setdefault("tags", [])
    tags.append("x")
    assert stash.tags == ["x"]


def test_list_slice_returns_plain_copy(stash: Stash) -> None:
    stash.nums = [1, 2, 3, 4]
    chunk = stash.nums[1:3]
    assert chunk == [2, 3]
    chunk.append(99)  # must NOT affect the stored list
    assert stash.nums == [1, 2, 3, 4]


def test_list_concatenation_returns_plain_list(stash: Stash) -> None:
    stash.nums = [1, 2]
    combined = stash.nums + [3]
    assert combined == [1, 2, 3]
    assert stash.nums == [1, 2]  # unchanged


def test_repr_shows_underlying_value(stash: Stash) -> None:
    stash.tags = ["a"]
    assert repr(stash.tags) == "['a']"


def test_list_reversed(stash: Stash) -> None:
    stash.nums = [1, 2, 3]
    assert list(reversed(stash.nums)) == [3, 2, 1]


def test_dict_keys_items_iter(stash: Stash) -> None:
    stash.d = {"a": 1, "b": 2}
    assert set(stash.d.keys()) == {"a", "b"}
    assert dict(stash.d.items()) == {"a": 1, "b": 2}
    assert set(stash.d) == {"a", "b"}  # __iter__ yields keys
    assert dict(stash.d) == {"a": 1, "b": 2}  # via keys() + __getitem__


def test_dict_get_returns_default_and_value(stash: Stash) -> None:
    stash.d = {"a": 1}
    assert stash.d.get("missing") is None
    assert stash.d.get("missing", 7) == 7
    assert stash.d.get("a") == 1


def test_dict_popitem(stash: Stash) -> None:
    stash.d = {"a": 1}
    key, value = stash.d.popitem()
    assert (key, value) == ("a", 1)
    assert stash.d == {}


def test_set_iter_pop_and_algebra(stash: Stash) -> None:
    stash.s = {1, 2, 3}
    assert set(stash.s) == {1, 2, 3}
    popped = stash.s.pop()
    assert popped in {1, 2, 3}
    assert len(stash.s) == 2

    stash.t = {1, 2, 3, 4}
    stash.t &= {2, 3, 4, 5}
    assert stash.t == {2, 3, 4}
    stash.t ^= {3, 9}
    assert stash.t == {2, 4, 9}


def test_proxy_equals_proxy(stash: Stash) -> None:
    stash.a = [1, 2]
    stash.b = [1, 2]
    assert stash.a == stash.b
    stash.c = [9]
    assert stash.a != stash.c
