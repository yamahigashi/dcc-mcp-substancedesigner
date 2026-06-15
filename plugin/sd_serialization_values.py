"""Concrete SDValue serialization helpers."""

from __future__ import annotations

from typing import cast

from .json_types import JsonMap, JsonValue
from .sd_serialization_types import ReprFallback, SDSequenceValue, SDUsageLike, SDValueLike, WValue, XYValue, ZValue


def serialize_xy_value(value: XYValue) -> dict[str, JsonValue]:
    """Serialize a vector-like value with at least x and y components."""
    serialized: dict[str, JsonValue] = {"x": value.x, "y": value.y}
    if hasattr(value, "z"):
        serialized["z"] = cast(ZValue, value).z
    if hasattr(value, "w"):
        serialized["w"] = cast(WValue, value).w
    return serialized


def serialize_usage(value: SDUsageLike) -> JsonMap:
    """Serialize an SDUsage value without losing metadata."""
    return {
        "name": value.getName(),
        "components": value.getComponents(),
        "color_space": value.getColorSpace(),
    }


def serialize_sequence(value: SDSequenceValue) -> list[JsonValue]:
    """Serialize an SD sequence value, preserving typed usage metadata."""
    items: list[JsonValue] = []
    try:
        for index in range(value.getSize()):
            item = value.getItem(index)
            if hasattr(item, "get"):
                raw = cast(SDValueLike, item).get()
                if is_usage_value(raw):
                    items.append(serialize_usage(cast(SDUsageLike, raw)))
                else:
                    items.append(str(raw))
            else:
                items.append(str(item))
    except BaseException:
        return [str(value)]
    return items


def is_usage_value(value: ReprFallback) -> bool:
    """Return whether a raw SD value exposes usage metadata."""
    return all(hasattr(value, name) for name in ("getName", "getComponents", "getColorSpace"))
