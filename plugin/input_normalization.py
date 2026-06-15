"""User-facing bridge input normalization helpers."""

from __future__ import annotations

import re

from .json_types import JsonValue

DEFAULT_PORT_SENTINELS = {"", "default", "*", "auto"}


def string_identifier(value: JsonValue, name: str) -> str:
    """Return a user-facing identifier from a string, integer, or common object shape."""
    if isinstance(value, bool):
        raise ValueError("{} must be a non-empty string, integer, or object with an id.".format(name))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        for key in ("id", "identifier", "property_id", "parameter_id", "input_id", "output_id", "port"):
            item = value.get(key)
            if isinstance(item, (str, int)) and not isinstance(item, bool) and str(item).strip():
                return str(item)
        source = value.get("source")
        if isinstance(source, dict):
            try:
                return string_identifier(source, name)
            except ValueError:
                pass
    raise ValueError("{} must be a non-empty string, integer, or object with an id.".format(name))


def optional_string_identifier(value: JsonValue, name: str) -> str | None:
    """Return an optional user-facing identifier."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in DEFAULT_PORT_SENTINELS:
        return None
    return string_identifier(value, name)


def normalize_float2(value: JsonValue, name: str) -> list[float] | None:
    """Return a two-number vector from list or common mapping forms."""
    if value is None:
        return None
    if isinstance(value, dict):
        pair = _mapping_pair(value, (("x", "y"), ("left", "top"), ("width", "height"), ("0", "1")))
        if pair is not None:
            return [_number(pair[0], "{}[0]".format(name)), _number(pair[1], "{}[1]".format(name))]
    if isinstance(value, list) and len(value) >= 2:
        return [_number(value[0], "{}[0]".format(name)), _number(value[1], "{}[1]".format(name))]
    raise ValueError("{} must contain two numbers.".format(name))


def normalize_color(value: JsonValue, name: str) -> list[float] | None:
    """Return an RGBA vector from list or common color mapping forms."""
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("rgba", "rgb", "value", "components"):
            item = value.get(key)
            if isinstance(item, list):
                return normalize_color(item, name)
        if all(key in value for key in ("r", "g", "b")):
            return [
                _number(value["r"], "{}.r".format(name)),
                _number(value["g"], "{}.g".format(name)),
                _number(value["b"], "{}.b".format(name)),
                _number(value.get("a", 1.0), "{}.a".format(name)),
            ]
        if all(key in value for key in ("red", "green", "blue")):
            return [
                _number(value["red"], "{}.red".format(name)),
                _number(value["green"], "{}.green".format(name)),
                _number(value["blue"], "{}.blue".format(name)),
                _number(value.get("alpha", 1.0), "{}.alpha".format(name)),
            ]
    if isinstance(value, list):
        if len(value) < 3:
            raise ValueError("{} must contain at least three color numbers.".format(name))
        alpha = value[3] if len(value) > 3 else 1.0
        return [
            _number(value[0], "{}[0]".format(name)),
            _number(value[1], "{}[1]".format(name)),
            _number(value[2], "{}[2]".format(name)),
            _number(alpha, "{}[3]".format(name)),
        ]
    raise ValueError("{} must be an RGBA list or color object.".format(name))


def normalize_resolution_size(value: JsonValue) -> tuple[int, int]:
    """Return pixel width and height from scalar, mapping, or WIDTHxHEIGHT text."""
    if isinstance(value, dict):
        width = value.get("width") or value.get("w") or value.get("x")
        height = value.get("height") or value.get("h") or value.get("y") or width
        return _positive_int(width, "width"), _positive_int(height, "height")
    if isinstance(value, int) and not isinstance(value, bool):
        return _positive_int(value, "size"), _positive_int(value, "size")
    if isinstance(value, str):
        text = value.strip().lower()
        match = re.fullmatch(r"(\d+)\s*[x,]\s*(\d+)", text)
        if match:
            return _positive_int(match.group(1), "width"), _positive_int(match.group(2), "height")
        return _positive_int(text, "size"), _positive_int(text, "size")
    raise ValueError("resolution size must be a number, WIDTHxHEIGHT string, or width/height object.")


def _mapping_pair(
    value: dict[str, JsonValue], key_pairs: tuple[tuple[str, str], ...]
) -> tuple[JsonValue, JsonValue] | None:
    for first, second in key_pairs:
        if first in value and second in value:
            return value[first], value[second]
    return None


def _number(value: JsonValue, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError("{} must be a number.".format(name))
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("{} must be a number.".format(name)) from exc
    raise ValueError("{} must be a number.".format(name))


def _positive_int(value: JsonValue, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError("{} must be a positive integer.".format(name))
    if not isinstance(value, (int, float, str)):
        raise ValueError("{} must be a positive integer.".format(name))
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError("{} must be a positive integer.".format(name)) from exc
    if number <= 0:
        raise ValueError("{} must be a positive integer.".format(name))
    return number
