"""Tests for batch() transactions and concurrent access (phase 4)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from objstash import Stash


@pytest.fixture
def stash() -> Iterator[Stash]:
    instance = Stash(":memory:")
    yield instance
    instance.close()


def test_batch_writes_are_all_applied(stash: Stash) -> None:
    with stash.batch():
        for i in range(100):
            stash[f"k{i}"] = i
    assert len(stash) == 100
    assert stash["k0"] == 0
    assert stash["k99"] == 99


def test_batch_rolls_back_on_exception(stash: Stash) -> None:
    stash.kept = "before"
    with pytest.raises(RuntimeError), stash.batch():
        stash.a = 1
        stash.b = 2
        raise RuntimeError("boom")
    assert "a" not in stash
    assert "b" not in stash
    assert stash.kept == "before"  # writes before the batch are untouched


def test_batch_read_your_writes(stash: Stash) -> None:
    with stash.batch():
        stash.x = 10
        assert stash.x == 10  # visible within the same transaction
    assert stash.x == 10


def test_nested_batches_commit_once(stash: Stash) -> None:
    with stash.batch():
        stash.a = 1
        with stash.batch():
            stash.b = 2
        stash.c = 3
    assert stash.to_dict() == {"a": 1, "b": 2, "c": 3}


def test_nested_batch_exception_rolls_back_everything(stash: Stash) -> None:
    with pytest.raises(ValueError), stash.batch():
        stash.a = 1
        with stash.batch():
            stash.b = 2
            raise ValueError("inner")
    assert "a" not in stash
    assert "b" not in stash


def test_batch_with_mutation_proxies(stash: Stash) -> None:
    stash.tags = []
    with stash.batch():
        for i in range(50):
            stash.tags.append(i)
    assert stash.tags == list(range(50))


def test_batch_not_visible_to_other_connection_until_commit(tmp_path: Path) -> None:
    db = str(tmp_path / "iso.db")
    writer = Stash(db)
    reader = Stash(db)
    try:
        writer.committed = "yes"
        assert reader.committed == "yes"

        with writer.batch():
            writer.pending = "value"
            # A separate connection must not see uncommitted writes.
            assert "pending" not in reader
        # After the batch commits it becomes visible.
        assert reader.pending == "value"
    finally:
        writer.close()
        reader.close()


def test_concurrent_writes_distinct_keys(tmp_path: Path) -> None:
    stash = Stash(str(tmp_path / "threads.db"))
    per_thread = 100

    def write(start: int) -> None:
        for i in range(start, start + per_thread):
            stash[f"k{i}"] = i

    threads = [threading.Thread(target=write, args=(n * per_thread,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(stash) == 4 * per_thread
    stash.close()


def test_concurrent_batches_are_serialized(tmp_path: Path) -> None:
    stash = Stash(str(tmp_path / "batches.db"))
    iterations = 50

    def bump() -> None:
        for _ in range(iterations):
            with stash.batch():
                stash.counter = stash.get("counter", 0) + 1

    threads = [threading.Thread(target=bump) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # The lock held across each batch serializes the read-modify-write, so no
    # increments are lost.
    assert stash.counter == 4 * iterations
    stash.close()
