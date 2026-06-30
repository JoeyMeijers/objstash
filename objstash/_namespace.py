"""Nested namespaces over the flat key/value store.

Keys are dotted paths: ``stash.settings.theme = "dark"`` stores the value under
``"settings.theme"``. A *namespace* is any path that has descendants but no
scalar of its own; reading it yields a :class:`Namespace` bound to that prefix.

:class:`_Node` holds the behaviour shared by the root :class:`~stash.Stash` and
nested :class:`Namespace` objects. The two differ only in how a child key is
formed (the root has an empty prefix) and in lifecycle (the root owns the
database connection).

Read semantics:

* **Attribute access auto-vivifies.** ``node.unknown`` returns an empty
  ``Namespace`` rather than raising, so assignment chains like
  ``stash.window.width = 1200`` create sections on demand.
* **Item access is strict.** ``node["unknown"]`` raises ``KeyError``.
* **Membership is exact.** ``"settings" in node`` is true only when a scalar or
  a descendant actually exists.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ._codecs import decode, encode
from ._proxies import wrap
from ._store import Store


def _check_key(key: str) -> str:
    """Validate a key used through item access and return it unchanged.

    Dotted keys are allowed and address nested paths
    (``node["a.b"]`` == ``node.a.b``), but empty path segments are rejected.
    """
    if not isinstance(key, str):
        raise TypeError(f"Stash keys must be str, not {type(key).__name__}")
    if not key:
        raise ValueError("Stash key must be non-empty")
    if "" in key.split("."):
        raise ValueError(f"key {key!r} has an empty path segment")
    return key


class _Node:
    """Behaviour shared by the root stash and nested namespaces."""

    # Set via object.__setattr__ in subclasses so they bypass our __setattr__.
    _store: Store
    _prefix: str

    def _key(self, name: str) -> str:
        """Return the full storage key for a child ``name`` of this node."""
        return f"{self._prefix}.{name}" if self._prefix else name

    @property
    def _scan(self) -> str:
        """Prefix that matches this node's descendants (``""`` for the root)."""
        return f"{self._prefix}." if self._prefix else ""

    # -- core operations (shared by attribute and item access) --------------

    def _resolve(self, key: str) -> Any:
        """Return the value at ``key``, or a (possibly empty) child namespace."""
        row = self._store.get(key)
        if row is not None:
            return self._wrap_value(key, decode(row[0], row[1]))
        return Namespace(self._store, key)

    def _wrap_value(self, key: str, value: Any) -> Any:
        """Wrap a stored container so in-place mutations persist back to ``key``."""
        if not isinstance(value, (list, dict, set)):
            return value
        store = self._store

        def save() -> None:
            store.put(key, *encode(value))

        return wrap(value, save)

    def _assign(self, key: str, value: Any) -> None:
        """Store ``value`` at ``key``, replacing any namespace or ancestor scalar.

        Assigning a scalar where a namespace lived clears the old subtree;
        assigning into a path clears any scalar sitting on an ancestor, so a
        path is unambiguously either a value or a namespace.
        """
        self._store.delete_prefix(key + ".")
        parts = key.split(".")
        for depth in range(1, len(parts)):
            self._store.delete(".".join(parts[:depth]))
        codec, payload = encode(value)
        self._store.put(key, codec, payload)

    def _delete(self, key: str) -> bool:
        """Delete the scalar and/or subtree at ``key``; return whether anything went."""
        removed_scalar = self._store.delete(key)
        removed_children = self._store.delete_prefix(key + ".")
        return removed_scalar or removed_children > 0

    def _exists(self, key: str) -> bool:
        return self._store.get(key) is not None or self._store.has_prefix(key + ".")

    # -- attribute access ---------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Only invoked when normal lookup fails (i.e. not for real methods/attrs).
        if name.startswith("_"):
            raise AttributeError(name)
        return self._resolve(self._key(name))

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        self._assign(self._key(name), value)

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            object.__delattr__(self, name)
            return
        # Forgiving, like attribute reads: deleting an absent key is a no-op.
        # Use item access (``del node["x"]``) if you want a strict KeyError.
        self._delete(self._key(name))

    # -- item access (strict; dotted keys address nested paths) -------------

    def __getitem__(self, key: str) -> Any:
        full = self._key(_check_key(key))
        row = self._store.get(full)
        if row is not None:
            return self._wrap_value(full, decode(row[0], row[1]))
        if self._store.has_prefix(full + "."):
            return Namespace(self._store, full)
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._assign(self._key(_check_key(key)), value)

    def __delitem__(self, key: str) -> None:
        if not self._delete(self._key(_check_key(key))):
            raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._exists(self._key(key))

    # -- dict-like helpers --------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value or namespace at ``key``, or ``default`` if absent."""
        full = self._key(_check_key(key))
        row = self._store.get(full)
        if row is not None:
            return self._wrap_value(full, decode(row[0], row[1]))
        if self._store.has_prefix(full + "."):
            return Namespace(self._store, full)
        return default

    def setdefault(self, key: str, default: Any) -> Any:
        """Return the existing value at ``key`` or store and return ``default``."""
        full = self._key(_check_key(key))
        row = self._store.get(full)
        if row is not None:
            return self._wrap_value(full, decode(row[0], row[1]))
        if self._store.has_prefix(full + "."):
            return Namespace(self._store, full)
        self._assign(full, default)
        return self._wrap_value(full, default)

    def clear(self) -> None:
        """Delete everything under this node.

        On the root :class:`~stash.Stash` this wipes the whole store; on a
        namespace it removes only that subtree.
        """
        self._store.delete_prefix(self._scan)

    def keys(self) -> list[str]:
        """Return the immediate child names of this node, sorted."""
        names: list[str] = []
        seen: set[str] = set()
        start = len(self._scan)
        for full in self._store.keys_with_prefix(self._scan):
            segment = full[start:].split(".", 1)[0]
            if segment not in seen:
                seen.add(segment)
                names.append(segment)
        names.sort()
        return names

    def to_dict(self) -> dict[str, Any]:
        """Return this node's subtree as a plain nested dictionary (no proxies)."""
        result: dict[str, Any] = {}
        for name in self.keys():
            key = self._key(name)
            row = self._store.get(key)
            if row is not None:
                result[name] = decode(row[0], row[1])
            else:
                result[name] = Namespace(self._store, key).to_dict()
        return result

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self.keys())

    def __bool__(self) -> bool:
        return self._store.has_prefix(self._scan)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Node):
            return self.to_dict() == other.to_dict()
        if isinstance(other, dict):
            return self.to_dict() == other
        return NotImplemented

    # Defining __eq__ without __hash__ makes instances unhashable, which is
    # correct: a namespace is a mutable view, like a dict.


class Namespace(_Node):
    """A nested view bound to a key prefix (e.g. ``settings`` or ``a.b``)."""

    def __init__(self, store: Store, prefix: str) -> None:
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_prefix", prefix)

    def __repr__(self) -> str:
        return f"Namespace({self._prefix!r}, {self.to_dict()!r})"
