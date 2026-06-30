"""Tests for the serialization layer (round-trips, edge cases, errors)."""

from __future__ import annotations

import datetime
import math
import uuid
from decimal import Decimal
from typing import Any

import pytest

from objstash import UnsupportedTypeError, register_type
from objstash._codecs import decode, encode


def roundtrip(value: object) -> Any:
    return decode(*encode(value))


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        0,
        -123,
        2**70,  # arbitrary-precision int
        3.14,
        -0.0,
        "",
        "héllo 🐍",
        [],
        [1, "two", None, [3, 4]],
        {},
        {"a": 1, "nested": {"b": [1, 2]}},
    ],
)
def test_json_native_roundtrip(value: object) -> None:
    assert roundtrip(value) == value


def test_float_specials_roundtrip() -> None:
    assert math.isnan(roundtrip(float("nan")))
    assert roundtrip(float("inf")) == float("inf")
    assert roundtrip(float("-inf")) == float("-inf")


def test_tuple_stays_tuple() -> None:
    result = roundtrip((1, 2, 3))
    assert result == (1, 2, 3)
    assert isinstance(result, tuple)


def test_set_roundtrip() -> None:
    result = roundtrip({1, 2, 3})
    assert result == {1, 2, 3}
    assert isinstance(result, set)


def test_dict_with_int_keys_roundtrip() -> None:
    value = {1: "a", 2: "b"}
    result = roundtrip(value)
    assert result == value
    assert all(isinstance(k, int) for k in result)


def test_dict_with_tuple_keys_roundtrip() -> None:
    value = {(1, 2): "x", (3, 4): "y"}
    assert roundtrip(value) == value


def test_dict_literal_reserved_key_roundtrip() -> None:
    # A user dict that happens to use our reserved tag must survive intact.
    value = {"__stash__": "set", "items": [1, 2]}
    assert roundtrip(value) == value


def test_builtin_type_roundtrips() -> None:
    now = datetime.datetime(2026, 6, 27, 14, 30, 5)
    assert roundtrip(now) == now
    assert roundtrip(datetime.date(2026, 6, 27)) == datetime.date(2026, 6, 27)
    assert roundtrip(datetime.time(14, 30)) == datetime.time(14, 30)
    assert roundtrip(Decimal("3.14159")) == Decimal("3.14159")
    some_uuid = uuid.uuid4()
    assert roundtrip(some_uuid) == some_uuid
    assert roundtrip(b"\x00\x01binary\xff") == b"\x00\x01binary\xff"


def test_datetime_and_date_are_distinct_codecs() -> None:
    # datetime is a subclass of date; exact-type lookup must not confuse them.
    result = roundtrip(datetime.datetime(2026, 1, 1, 12, 0, 0))
    assert isinstance(result, datetime.datetime)


def test_unsupported_type_raises() -> None:
    with pytest.raises(UnsupportedTypeError):
        encode(object())


def test_circular_reference_raises() -> None:
    data: list[object] = [1, 2]
    data.append(data)
    with pytest.raises(Exception, match="circular"):
        encode(data)


def test_payload_is_inspectable_json() -> None:
    codec, payload = encode({"theme": "dark"})
    assert codec == "json"
    assert payload == '{"theme":"dark"}'


def test_decode_rejects_unknown_storage_codec() -> None:
    with pytest.raises(Exception, match="codec"):
        decode("pickle", "{}")


def test_decode_rejects_unknown_tag() -> None:
    with pytest.raises(Exception, match="codec tag"):
        decode("json", '{"__stash__": "no-such-tag", "data": 1}')


def test_register_custom_type() -> None:
    class Point:
        def __init__(self, x: int, y: int) -> None:
            self.x, self.y = x, y

        def __eq__(self, other: object) -> bool:
            return isinstance(other, Point) and (self.x, self.y) == (other.x, other.y)

    register_type(Point, "test-point", lambda p: [p.x, p.y], lambda d: Point(d[0], d[1]))
    assert roundtrip(Point(1, 2)) == Point(1, 2)


def test_register_rejects_reserved_and_empty_tags() -> None:
    with pytest.raises(ValueError):
        register_type(complex, "set", lambda v: v, lambda v: v)
    with pytest.raises(ValueError):
        register_type(complex, "", lambda v: v, lambda v: v)


def test_register_rejects_tag_reuse_for_different_type() -> None:
    register_type(complex, "test-reuse", str, complex)
    with pytest.raises(ValueError):
        register_type(bytearray, "test-reuse", str, bytearray)


def test_codec_output_composes_with_builtin_codecs() -> None:
    # A custom codec whose encoded form contains another non-JSON type must
    # round-trip: codec output is recursed back through the registry.
    from dataclasses import asdict, dataclass

    @dataclass
    class Event:
        name: str
        when: datetime.datetime

    register_type(Event, "test-event", asdict, lambda d: Event(**d))
    original = Event("launch", datetime.datetime(2026, 6, 28, 9, 30))
    restored = roundtrip(original)
    assert restored == original
    assert isinstance(restored.when, datetime.datetime)


def test_codec_output_composes_with_structural_types() -> None:
    # Encoded form contains a set (a structural type), which must survive too.
    from dataclasses import asdict, dataclass

    @dataclass
    class Bag:
        items: set[int]

    register_type(Bag, "test-bag", asdict, lambda d: Bag(**d))
    restored = roundtrip(Bag({1, 2, 3}))
    assert restored == Bag({1, 2, 3})
    assert isinstance(restored.items, set)
