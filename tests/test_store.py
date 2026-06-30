"""Tests for the SQLite store, including thread and multi-connection access."""

from __future__ import annotations

import threading
from pathlib import Path

from objstash import Stash
from objstash._store import Store


def test_put_get_delete_roundtrip() -> None:
    store = Store(":memory:")
    assert store.get("k") is None
    store.put("k", "json", '"v"')
    assert store.get("k") == ("json", '"v"')
    assert store.delete("k") is True
    assert store.delete("k") is False
    assert store.get("k") is None
    store.close()


def test_put_replaces_existing() -> None:
    store = Store(":memory:")
    store.put("k", "json", "1")
    store.put("k", "json", "2")
    assert store.get("k") == ("json", "2")
    store.close()


def test_keys_sorted() -> None:
    store = Store(":memory:")
    store.put("c", "json", "1")
    store.put("a", "json", "1")
    store.put("b", "json", "1")
    assert store.keys() == ["a", "b", "c"]
    store.close()


def test_second_connection_sees_writes(tmp_path: Path) -> None:
    # Read-through across separate connections (simulates two processes).
    db = str(tmp_path / "shared.db")
    writer = Store(db)
    writer.put("k", "json", '"hello"')

    reader = Store(db)
    assert reader.get("k") == ("json", '"hello"')

    writer.put("k", "json", '"updated"')
    assert reader.get("k") == ("json", '"updated"')  # last-write-wins, no stale cache

    writer.close()
    reader.close()


def test_concurrent_writes_from_threads(tmp_path: Path) -> None:
    stash = Stash(str(tmp_path / "threads.db"))
    key_count = 100

    def write(start: int) -> None:
        for i in range(start, start + key_count):
            stash[f"k{i}"] = i

    threads = [threading.Thread(target=write, args=(n * key_count,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(stash.keys()) == 4 * key_count
    assert stash["k0"] == 0
    assert stash[f"k{4 * key_count - 1}"] == 4 * key_count - 1
    stash.close()
