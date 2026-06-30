"""Serialization layer: convert Python values to/from a JSON payload.

Stash stores every value as JSON text. JSON natively covers ``None``, ``bool``,
``int``, ``float``, ``str``, ``list`` and string-keyed ``dict``. Everything else
is handled by a *codec registry*: a value of a registered type is encoded as a
tagged object ``{"__stash__": <tag>, "data": <jsonable>}`` and reconstructed on
read.

Why a recursive transform instead of ``json.dumps(default=...)``: the standard
encoder silently corrupts several common cases — it turns tuples into lists and
coerces non-string dict keys to strings. We walk the value tree ourselves so the
round-trip is lossless and explicit, which matters more than raw speed here
(correctness > performance).

This module never imports ``pickle``. Unknown types raise
:class:`UnsupportedTypeError` rather than falling back to insecure serialization.
"""

from __future__ import annotations

import base64
import datetime
import decimal
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ._exceptions import StashError, UnsupportedTypeError

#: Key used to tag non-native types inside the JSON document.
_TAG = "__stash__"

#: Tags reserved for structural types handled directly by the walkers. Custom
#: codecs may not reuse these.
_STRUCTURAL_TAGS = frozenset({"tuple", "set", "map"})


@dataclass(frozen=True)
class _TypeCodec:
    """How to encode/decode a single leaf type.

    ``encode`` must return a JSON-native value (typically ``str``); ``decode``
    is its inverse.
    """

    tag: str
    type: type
    encode: Callable[[Any], Any]
    decode: Callable[[Any], Any]


_BY_TYPE: dict[type, _TypeCodec] = {}
_BY_TAG: dict[str, _TypeCodec] = {}


def register_type(
    cls: type,
    tag: str,
    encode: Callable[[Any], Any],
    decode: Callable[[Any], Any],
) -> None:
    """Register a codec for a custom leaf type.

    Args:
        cls: The Python type to handle.
        tag: A stable, unique identifier stored in the database. Changing it
            later breaks existing data, so choose carefully.
        encode: Callable turning an instance into a JSON-native value.
        decode: Callable turning that value back into an instance.

    Raises:
        ValueError: If ``tag`` is empty, structural, or already registered to a
            different type.
    """
    if not tag:
        raise ValueError("codec tag must be non-empty")
    if tag in _STRUCTURAL_TAGS:
        raise ValueError(f"codec tag {tag!r} is reserved")
    existing = _BY_TAG.get(tag)
    if existing is not None and existing.type is not cls:
        raise ValueError(f"codec tag {tag!r} is already registered for {existing.type!r}")
    codec = _TypeCodec(tag=tag, type=cls, encode=encode, decode=decode)
    _BY_TYPE[cls] = codec
    _BY_TAG[tag] = codec


def _lookup_codec(value_type: type) -> _TypeCodec | None:
    """Find a codec for ``value_type``, preferring an exact type match.

    Exact match first keeps closely related types (``datetime`` vs ``date``)
    distinct; the isinstance fallback lets user subclasses reuse a base codec.
    """
    codec = _BY_TYPE.get(value_type)
    if codec is not None:
        return codec
    for registered_type, registered_codec in _BY_TYPE.items():
        if issubclass(value_type, registered_type):
            return registered_codec
    return None


def _to_jsonable(obj: Any, ancestors: frozenset[int]) -> Any:
    """Recursively convert ``obj`` into a JSON-native structure.

    ``ancestors`` holds the ``id()`` of containers currently being encoded so
    that circular references fail loudly instead of overflowing the stack.
    """
    # A mutation proxy (see _proxies) serializes as its underlying container.
    # Detected by marker to avoid importing _proxies (which imports this module).
    if getattr(obj, "__stash_proxy__", False):
        return _to_jsonable(obj._data, ancestors)

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    if isinstance(obj, (list, tuple, set, dict)):
        if id(obj) in ancestors:
            raise StashError("cannot serialize a circular reference")
        ancestors = ancestors | {id(obj)}

    if isinstance(obj, list):
        return [_to_jsonable(item, ancestors) for item in obj]
    if isinstance(obj, tuple):
        return {_TAG: "tuple", "items": [_to_jsonable(item, ancestors) for item in obj]}
    if isinstance(obj, set):
        return {_TAG: "set", "items": [_to_jsonable(item, ancestors) for item in obj]}
    if isinstance(obj, dict):
        # Plain string-keyed dicts map straight to JSON objects, unless they
        # contain our reserved tag — then we must use the explicit "map" form to
        # avoid colliding with a real codec on read.
        if _TAG not in obj and all(isinstance(key, str) for key in obj):
            return {key: _to_jsonable(val, ancestors) for key, val in obj.items()}
        return {
            _TAG: "map",
            "items": [
                [_to_jsonable(key, ancestors), _to_jsonable(val, ancestors)]
                for key, val in obj.items()
            ],
        }

    codec = _lookup_codec(type(obj))
    if codec is None:
        raise UnsupportedTypeError(
            f"no codec registered for type {type(obj).__name__!r}; "
            f"register one with stash.register_type(...)"
        )
    # Recurse into the codec's output so it may contain other registered types
    # (e.g. a dataclass with a datetime field). Built-in codecs return
    # primitives, for which this is a no-op.
    return {_TAG: codec.tag, "data": _to_jsonable(codec.encode(obj), ancestors)}


def _from_jsonable(obj: Any) -> Any:
    """Inverse of :func:`_to_jsonable`."""
    if isinstance(obj, list):
        return [_from_jsonable(item) for item in obj]
    if isinstance(obj, dict):
        tag = obj.get(_TAG)
        if tag is None:
            return {key: _from_jsonable(val) for key, val in obj.items()}
        if tag == "tuple":
            return tuple(_from_jsonable(item) for item in obj["items"])
        if tag == "set":
            return {_from_jsonable(item) for item in obj["items"]}
        if tag == "map":
            return {_from_jsonable(key): _from_jsonable(val) for key, val in obj["items"]}
        codec = _BY_TAG.get(tag)
        if codec is None:
            raise StashError(f"unknown codec tag {tag!r}; was it registered before reading?")
        # Mirror the recursion in _to_jsonable: reconstruct nested registered
        # types before handing the data to the codec's decode.
        return codec.decode(_from_jsonable(obj["data"]))
    return obj


def encode(value: Any) -> tuple[str, str]:
    """Serialize ``value`` into a ``(codec, payload)`` pair for storage.

    ``codec`` names the top-level format (always ``"json"`` today); ``payload``
    is the JSON document.
    """
    jsonable = _to_jsonable(value, frozenset())
    payload = json.dumps(jsonable, ensure_ascii=False, separators=(",", ":"))
    return ("json", payload)


def decode(codec: str, payload: str) -> Any:
    """Reconstruct a value previously produced by :func:`encode`."""
    if codec != "json":
        raise StashError(f"unknown storage codec {codec!r}")
    return _from_jsonable(json.loads(payload))


def _register_builtins() -> None:
    """Register codecs for common stdlib types not covered by JSON."""
    register_type(
        datetime.datetime, "datetime", lambda v: v.isoformat(), datetime.datetime.fromisoformat
    )
    register_type(datetime.date, "date", lambda v: v.isoformat(), datetime.date.fromisoformat)
    register_type(datetime.time, "time", lambda v: v.isoformat(), datetime.time.fromisoformat)
    register_type(decimal.Decimal, "decimal", str, decimal.Decimal)
    register_type(uuid.UUID, "uuid", str, uuid.UUID)
    register_type(
        bytes,
        "bytes",
        lambda v: base64.b64encode(v).decode("ascii"),
        lambda v: base64.b64decode(v),
    )


_register_builtins()
