"""SDValue serialization helpers for host plugin responses."""

from __future__ import annotations

from typing import cast

from .json_types import JsonValue
from .sd_serialization_types import (
    ReprFallback,
    RGBAValue,
    SDSequenceValue,
    SDUsageLike,
    SDValueLike,
    XYValue,
)
from .sd_serialization_values import is_usage_value, serialize_sequence, serialize_usage, serialize_xy_value


def serialize_sd_value(value: ReprFallback | None) -> JsonValue:
    """Serialize a Substance Designer value wrapper into JSON-safe data."""
    if value is None:
        return None
    try:
        raw = cast(SDValueLike, value).get()
    except BaseException:
        return str(value)
    if is_usage_value(raw):
        return serialize_usage(cast(SDUsageLike, raw))
    if hasattr(raw, "x") and hasattr(raw, "y"):
        return serialize_xy_value(cast(XYValue, raw))
    if hasattr(raw, "r") and hasattr(raw, "g"):
        color = cast(RGBAValue, raw)
        return {"r": color.r, "g": color.g, "b": color.b, "a": color.a}
    if hasattr(raw, "getSize") and hasattr(raw, "getItem"):
        return serialize_sequence(cast(SDSequenceValue, raw))
    return str(raw)
