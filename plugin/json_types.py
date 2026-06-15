"""Shared JSON type aliases for host plugin payloads."""

from __future__ import annotations

from typing import TypeAlias, cast

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonArray: TypeAlias = list[JsonValue]
JsonMap: TypeAlias = dict[str, JsonValue]


def cast_json_map(value: object, name: str = "value") -> JsonMap:
    """Return value as a JSON object or raise a boundary error."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be a JSON object.")
    return cast(JsonMap, value)


def as_str(value: JsonValue, name: str = "value") -> str:
    """Return value as a string or raise a boundary error."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string.")
    return value


def as_int(value: JsonValue, name: str = "value") -> int:
    """Return value as an integer or raise a boundary error."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    return value


def as_list_of_maps(value: JsonValue, name: str = "value") -> list[JsonMap]:
    """Return value as a list of JSON objects or raise a boundary error."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list.")
    return [cast_json_map(item, f"{name}[{index}]") for index, item in enumerate(value)]
