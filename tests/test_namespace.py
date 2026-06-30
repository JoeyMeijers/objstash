"""Tests for nested namespaces (phase 2)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from objstash import Namespace, Stash


@pytest.fixture
def stash() -> Iterator[Stash]:
    instance = Stash(":memory:")
    yield instance
    instance.close()


def test_create_and_read_nested(stash: Stash) -> None:
    stash.settings.theme = "dark"
    stash.window.width = 1200
    stash.window.height = 800
    assert stash.settings.theme == "dark"
    assert stash.window.width == 1200
    assert stash.window.height == 800


def test_deeply_nested(stash: Stash) -> None:
    stash.a.b.c.d = 42
    assert stash.a.b.c.d == 42
    assert isinstance(stash.a.b.c, Namespace)


def test_namespace_is_a_namespace_instance(stash: Stash) -> None:
    stash.settings.theme = "dark"
    assert isinstance(stash.settings, Namespace)


def test_namespace_to_dict(stash: Stash) -> None:
    stash.window.width = 1200
    stash.window.height = 800
    stash.window.title.text = "hi"
    assert stash.window.to_dict() == {"width": 1200, "height": 800, "title": {"text": "hi"}}


def test_root_to_dict_is_nested(stash: Stash) -> None:
    stash.theme = "dark"
    stash.window.width = 1200
    assert stash.to_dict() == {"theme": "dark", "window": {"width": 1200}}


def test_namespace_equality_with_dict(stash: Stash) -> None:
    stash.window.width = 1200
    stash.window.height = 800
    assert stash.window == {"width": 1200, "height": 800}
    assert stash.window != {"width": 1200}


def test_empty_namespace_is_falsy(stash: Stash) -> None:
    assert not stash.nothing_here
    stash.something.value = 1
    assert stash.something


def test_keys_returns_top_level_names(stash: Stash) -> None:
    stash.settings.theme = "dark"
    stash.settings.lang = "en"
    stash.counter = 0
    assert stash.keys() == ["counter", "settings"]
    assert stash.settings.keys() == ["lang", "theme"]


def test_membership_is_exact(stash: Stash) -> None:
    stash.settings.theme = "dark"
    assert "settings" in stash
    assert "theme" in stash.settings
    assert "missing" not in stash
    assert "missing" not in stash.settings


def test_namespace_item_access(stash: Stash) -> None:
    stash.settings["theme"] = "dark"
    assert stash.settings["theme"] == "dark"
    with pytest.raises(KeyError):
        _ = stash.settings["missing"]


def test_assigning_scalar_replaces_namespace(stash: Stash) -> None:
    stash.thing.a = 1
    stash.thing.b = 2
    assert stash.thing == {"a": 1, "b": 2}
    stash.thing = "now a scalar"
    assert stash.thing == "now a scalar"
    assert "thing" in stash
    # The old subtree is gone, not shadowed.
    assert stash.to_dict() == {"thing": "now a scalar"}


def test_assigning_into_path_clears_ancestor_scalar(stash: Stash) -> None:
    stash["a"] = 1
    stash["a.b"] = 2  # "a" must become a namespace, not coexist as a scalar
    assert isinstance(stash.a, Namespace)
    assert stash.a.to_dict() == {"b": 2}


def test_delete_namespace_removes_subtree(stash: Stash) -> None:
    stash.settings.theme = "dark"
    stash.settings.lang = "en"
    del stash.settings
    assert "settings" not in stash
    assert stash.to_dict() == {}


def test_delete_missing_nested_attribute_is_noop(stash: Stash) -> None:
    stash.settings.theme = "dark"
    del stash.settings.missing  # forgiving: no-op
    del stash.absent.deep  # also a no-op on a vivified namespace
    assert stash.settings.theme == "dark"


def test_delete_single_nested_key(stash: Stash) -> None:
    stash.settings.theme = "dark"
    stash.settings.lang = "en"
    del stash.settings.theme
    assert stash.settings.to_dict() == {"lang": "en"}


def test_nested_setdefault(stash: Stash) -> None:
    assert stash.settings.setdefault("theme", "light") == "light"
    assert stash.settings.setdefault("theme", "dark") == "light"
    assert stash.settings.theme == "light"


def test_nested_get_with_default(stash: Stash) -> None:
    assert stash.settings.get("theme", "light") == "light"
    stash.settings.theme = "dark"
    assert stash.settings.get("theme") == "dark"


def test_namespace_iteration_and_len(stash: Stash) -> None:
    stash.s.a = 1
    stash.s.b = 2
    assert sorted(stash.s) == ["a", "b"]
    assert len(stash.s) == 2


def test_namespace_repr(stash: Stash) -> None:
    stash.settings.theme = "dark"
    text = repr(stash.settings)
    assert "settings" in text
    assert "theme" in text


def test_namespace_unhashable(stash: Stash) -> None:
    stash.settings.theme = "dark"
    obj: object = stash.settings
    with pytest.raises(TypeError):
        hash(obj)


def test_namespace_delete_missing_item_raises(stash: Stash) -> None:
    stash.settings.theme = "dark"
    with pytest.raises(KeyError):
        del stash.settings["missing"]


def test_get_returns_namespace_for_existing_section(stash: Stash) -> None:
    stash.a.b = 1
    assert isinstance(stash.get("a"), Namespace)
    assert isinstance(stash.a.get("a", None) or stash.get("a"), Namespace)


def test_namespace_equality_with_other_type_is_false(stash: Stash) -> None:
    stash.window.width = 1200
    assert stash.window != 5
    assert (stash.window == 5) is False


def test_key_segment_with_underscore_is_not_a_wildcard(stash: Stash) -> None:
    # Underscores are valid in keys; the LIKE prefix scan must not treat them
    # as wildcards when listing/deleting a namespace.
    stash.a_b.x = 1
    stash.aXb.y = 2  # would match "a_b%" if "_" were an unescaped wildcard
    assert stash.a_b.to_dict() == {"x": 1}
    del stash.a_b
    assert "aXb" in stash  # the sibling survived


def test_namespace_clear_removes_only_its_subtree(stash: Stash) -> None:
    stash.keep = 1
    stash.settings.theme = "dark"
    stash.settings.lang = "en"
    stash.settings.window.width = 1200
    stash.settings.clear()
    assert "settings" not in stash
    assert stash.keep == 1


def test_nested_persistence_across_reopen(tmp_path: Path) -> None:
    db = str(tmp_path / "nested.db")
    first = Stash(db)
    first.settings.theme = "dark"
    first.settings.window.width = 1200
    first.close()

    second = Stash(db)
    assert second.settings.theme == "dark"
    assert second.settings.window.width == 1200
    assert second.to_dict() == {"settings": {"theme": "dark", "window": {"width": 1200}}}
    second.close()
