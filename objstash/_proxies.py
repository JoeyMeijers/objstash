"""Mutation proxies that persist in-place changes to stored containers.

Reading a stored ``list``/``dict``/``set`` returns a proxy wrapping the freshly
decoded value together with a ``save`` callback. Every mutating operation changes
the underlying container in place and then re-serializes the *whole top-level
value* to its key — JSON has no partial update, so the unit of persistence is the
key, not the sub-object.

Child containers are wrapped lazily on access and share the parent's ``save``
callback, so deep mutation persists too::

    stash.cfg = {"users": [{"name": "a"}]}
    stash.cfg["users"][0]["name"] = "b"   # rewrites the whole "cfg" value

Proxies are thin views over a point-in-time snapshot: a separate read decodes a
fresh copy. Aliases obtained from the *same* read share state; values fetched by
an earlier read are not retro-updated by a later write (last-write-wins, per
ADR-0001).

Proxies are detected by the serializer via the ``__stash_proxy__`` marker (a
duck-typed check that avoids a circular import), so assigning a proxy elsewhere
stores its underlying value.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any


def wrap(value: Any, save: Callable[[], None]) -> Any:
    """Wrap a container in a proxy bound to ``save``; return scalars unchanged."""
    if isinstance(value, list):
        return ListProxy(value, save)
    if isinstance(value, dict):
        return DictProxy(value, save)
    if isinstance(value, set):
        return SetProxy(value, save)
    return value


class _Proxy:
    """Shared behaviour for container proxies."""

    #: Marker used by the serializer to unwrap proxies without importing them.
    __stash_proxy__ = True

    __slots__ = ("_data", "_save")

    def __init__(self, data: Any, save: Callable[[], None]) -> None:
        self._data = data
        self._save = save

    def _wrap(self, value: Any) -> Any:
        return wrap(value, self._save)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, item: object) -> bool:
        return item in self._data

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Proxy):
            other = other._data
        return bool(self._data == other)

    def __repr__(self) -> str:
        return repr(self._data)

    # Mutable, like the wrapped container.
    __hash__ = None  # type: ignore[assignment]


class ListProxy(_Proxy):
    """A ``list`` view whose mutations are persisted."""

    __slots__ = ()

    def __getitem__(self, index: Any) -> Any:
        result = self._data[index]
        if isinstance(index, slice):
            return result  # a fresh copy; wrapping would be misleading
        return self._wrap(result)

    def __setitem__(self, index: Any, value: Any) -> None:
        self._data[index] = value
        self._save()

    def __delitem__(self, index: Any) -> None:
        del self._data[index]
        self._save()

    def __iter__(self) -> Iterator[Any]:
        return (self._wrap(item) for item in self._data)

    def __reversed__(self) -> Iterator[Any]:
        return (self._wrap(item) for item in reversed(self._data))

    def __add__(self, other: Any) -> list[Any]:
        combined: list[Any] = self._data + list(other)
        return combined

    def __iadd__(self, other: Any) -> ListProxy:
        self._data.extend(other)
        self._save()
        return self

    def __imul__(self, count: int) -> ListProxy:
        self._data *= count
        self._save()
        return self

    def append(self, value: Any) -> None:
        self._data.append(value)
        self._save()

    def extend(self, values: Any) -> None:
        self._data.extend(values)
        self._save()

    def insert(self, index: int, value: Any) -> None:
        self._data.insert(index, value)
        self._save()

    def remove(self, value: Any) -> None:
        self._data.remove(value)
        self._save()

    def pop(self, index: int = -1) -> Any:
        value = self._data.pop(index)
        self._save()
        return value

    def clear(self) -> None:
        self._data.clear()
        self._save()

    def sort(self, **kwargs: Any) -> None:
        self._data.sort(**kwargs)
        self._save()

    def reverse(self) -> None:
        self._data.reverse()
        self._save()


class DictProxy(_Proxy):
    """A ``dict`` view whose mutations are persisted."""

    __slots__ = ()

    def __getitem__(self, key: Any) -> Any:
        return self._wrap(self._data[key])

    def __setitem__(self, key: Any, value: Any) -> None:
        self._data[key] = value
        self._save()

    def __delitem__(self, key: Any) -> None:
        del self._data[key]
        self._save()

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def keys(self) -> Any:
        return self._data.keys()

    def values(self) -> list[Any]:
        return [self._wrap(value) for value in self._data.values()]

    def items(self) -> list[tuple[Any, Any]]:
        return [(key, self._wrap(value)) for key, value in self._data.items()]

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self._data:
            return self._wrap(self._data[key])
        return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            self._data[key] = default
            self._save()
        return self._wrap(self._data[key])

    def pop(self, key: Any, *default: Any) -> Any:
        value = self._data.pop(key, *default)
        self._save()
        return value

    def popitem(self) -> tuple[Any, Any]:
        item: tuple[Any, Any] = self._data.popitem()
        self._save()
        return item

    def clear(self) -> None:
        self._data.clear()
        self._save()

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._data.update(*args, **kwargs)
        self._save()

    def __ior__(self, other: Any) -> DictProxy:
        self._data.update(other)
        self._save()
        return self


class SetProxy(_Proxy):
    """A ``set`` view whose mutations are persisted."""

    __slots__ = ()

    def __iter__(self) -> Iterator[Any]:
        return iter(self._data)

    def add(self, value: Any) -> None:
        self._data.add(value)
        self._save()

    def discard(self, value: Any) -> None:
        self._data.discard(value)
        self._save()

    def remove(self, value: Any) -> None:
        self._data.remove(value)
        self._save()

    def pop(self) -> Any:
        value = self._data.pop()
        self._save()
        return value

    def clear(self) -> None:
        self._data.clear()
        self._save()

    def update(self, *others: Any) -> None:
        self._data.update(*others)
        self._save()

    def __ior__(self, other: Any) -> SetProxy:
        self._data |= other
        self._save()
        return self

    def __iand__(self, other: Any) -> SetProxy:
        self._data &= other
        self._save()
        return self

    def __isub__(self, other: Any) -> SetProxy:
        self._data -= other
        self._save()
        return self

    def __ixor__(self, other: Any) -> SetProxy:
        self._data ^= other
        self._save()
        return self
