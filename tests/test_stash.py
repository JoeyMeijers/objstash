"""Tests for the public Stash object (attribute/item access, persistence)."""

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


def test_set_and_get_attribute(stash: Stash) -> None:
    stash.theme = "dark"
    assert stash.theme == "dark"


def test_missing_attribute_vivifies_empty_namespace(stash: Stash) -> None:
    # Attribute reads auto-vivify so assignment chains can create sections.
    node = stash.nope
    assert not node  # empty namespace is falsy
    assert node.keys() == []
    assert "nope" not in stash  # but nothing was actually persisted


def test_contains_reflects_storage(stash: Stash) -> None:
    assert "x" not in stash
    stash.x = 1
    assert "x" in stash


def test_overwrite_value(stash: Stash) -> None:
    stash.count = 1
    stash.count = 2
    assert stash.count == 2


def test_augmented_assignment(stash: Stash) -> None:
    stash.counter = 0
    stash.counter += 1
    stash.counter += 1
    assert stash.counter == 2


def test_augmented_assignment_on_missing_key_raises(stash: Stash) -> None:
    # A missing key vivifies to a Namespace, which is not a number; the clearest
    # fix for users is setdefault(). The failure should be loud, not silent.
    with pytest.raises(TypeError):
        stash.counter += 1


def test_delete_attribute(stash: Stash) -> None:
    stash.x = 1
    del stash.x
    assert "x" not in stash


def test_delete_missing_attribute_is_noop(stash: Stash) -> None:
    # The attribute surface is forgiving (like vivifying reads): deleting an
    # absent key does nothing. Item access stays strict (test_delete_missing_item).
    del stash.nope
    assert "nope" not in stash


def test_item_access(stash: Stash) -> None:
    stash["a"] = 1
    assert stash["a"] == 1
    assert "a" in stash


def test_item_access_for_reserved_method_name(stash: Stash) -> None:
    # `get` is a method, so attribute access can't store it; item access can.
    stash["get"] = 42
    assert stash["get"] == 42
    assert callable(stash.get)


def test_missing_item_raises_keyerror(stash: Stash) -> None:
    with pytest.raises(KeyError):
        _ = stash["nope"]


def test_delete_missing_item_raises_keyerror(stash: Stash) -> None:
    with pytest.raises(KeyError):
        del stash["nope"]


def test_get_with_default(stash: Stash) -> None:
    assert stash.get("missing") is None
    assert stash.get("missing", 7) == 7
    stash.present = "yes"
    assert stash.get("present") == "yes"


def test_setdefault(stash: Stash) -> None:
    assert stash.setdefault("counter", 0) == 0
    assert stash.setdefault("counter", 99) == 0  # unchanged
    assert stash.counter == 0


def test_keys_iter_len(stash: Stash) -> None:
    stash.b = 1
    stash.a = 2
    assert stash.keys() == ["a", "b"]
    assert sorted(stash) == ["a", "b"]
    assert len(stash) == 2


def test_repr_lists_keys(stash: Stash) -> None:
    stash.a = 1
    assert "a" in repr(stash)


def test_empty_key_rejected(stash: Stash) -> None:
    with pytest.raises(ValueError):
        stash[""] = 1


def test_non_string_key_rejected(stash: Stash) -> None:
    with pytest.raises(TypeError):
        stash[1] = "x"  # type: ignore[index]


def test_dotted_item_key_is_nested_path(stash: Stash) -> None:
    stash["settings.theme"] = "dark"
    assert stash.settings.theme == "dark"
    assert stash["settings.theme"] == "dark"


def test_empty_path_segment_rejected(stash: Stash) -> None:
    for bad in [".a", "a.", "a..b"]:
        with pytest.raises(ValueError, match="empty path segment"):
            stash[bad] = 1


def test_contains_non_string_is_false(stash: Stash) -> None:
    assert 5 not in stash


def test_persistence_across_reopen(tmp_path: Path) -> None:
    db = str(tmp_path / "app.db")
    first = Stash(db)
    first.theme = "dark"
    first.tags = ["x", "y"]
    first.close()

    second = Stash(db)
    assert second.theme == "dark"
    assert second.tags == ["x", "y"]
    second.close()


def test_context_manager_closes(tmp_path: Path) -> None:
    db = str(tmp_path / "app.db")
    with Stash(db) as stash:
        stash.value = 1
    reopened = Stash(db)
    assert reopened.value == 1
    reopened.close()


def test_large_value_roundtrip(stash: Stash) -> None:
    big = list(range(50_000))
    stash.big = big
    assert stash.big == big


def test_private_attributes_are_not_stored(stash: Stash) -> None:
    # Underscore-prefixed names bypass storage (real instance attributes).
    stash._scratch = 1
    assert stash.keys() == []


def test_private_attribute_roundtrip_and_delete(stash: Stash) -> None:
    stash._scratch = 7
    assert stash._scratch == 7
    del stash._scratch
    assert not hasattr(stash, "_scratch")


def test_missing_private_attribute_raises(stash: Stash) -> None:
    with pytest.raises(AttributeError):
        _ = stash._never_set


def test_clear_removes_everything(stash: Stash) -> None:
    stash.a = 1
    stash.settings.theme = "dark"
    stash.tags = [1, 2, 3]
    stash.clear()
    assert stash.to_dict() == {}
    assert len(stash) == 0


def test_clear_empty_stash_is_noop(stash: Stash) -> None:
    stash.clear()
    assert stash.to_dict() == {}


def test_checkpoint_on_memory_is_noop(stash: Stash) -> None:
    stash.x = 1
    stash.checkpoint()  # must not raise on a non-WAL (in-memory) database
    assert stash.x == 1


def test_checkpoint_truncates_wal_and_preserves_data(tmp_path: Path) -> None:
    import os

    db = str(tmp_path / "cp.db")
    first = Stash(db)
    first.a = 1
    for i in range(50):
        first[f"k{i}"] = i
    first.checkpoint()

    wal = db + "-wal"
    assert not os.path.exists(wal) or os.path.getsize(wal) == 0
    first.close()

    # Data survives the checkpoint and a reopen.
    second = Stash(db)
    assert second.a == 1
    assert second["k49"] == 49
    second.close()
