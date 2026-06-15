"""Graph output-size helpers for host plugin preview rendering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from sd.api.sdbasetypes import int2
from sd.api.sdproperty import SDPropertyCategory
from sd.api.sdvalueint2 import SDValueInt2

from ..input_normalization import normalize_resolution_size
from ..json_types import JsonMap, JsonValue
from .graph_types import GraphOutputSizeHost, HostValue

if TYPE_CHECKING:
    from sd.api.sdvalue import SDValue

    class SDValueInt2Factory(Protocol):
        """Factory protocol for host output-size values."""

        @staticmethod
        def sNew(value: int2) -> SDValue:
            """Create an SDValueInt2 from a host int2."""
            ...


def output_size_value(width_log2: int, height_log2: int) -> SDValue:
    """Create a host output-size SDValue while hiding non-host fallback typing."""
    factory = cast("SDValueInt2Factory", SDValueInt2)
    return factory.sNew(int2(width_log2, height_log2))


def get_graph_output_size_value(graph: GraphOutputSizeHost) -> HostValue | None:
    """Return the current graph output size value when the host exposes it."""
    try:
        prop = graph.getPropertyFromId("$outputsize", SDPropertyCategory.Input)
        if prop:
            return graph.getPropertyValue(prop)
    except Exception:
        pass
    try:
        return graph.getInputPropertyValueFromId("$outputsize")
    except Exception:
        return None


def set_graph_output_size_value(graph: GraphOutputSizeHost, width: int, height: int) -> None:
    """Set the graph output size from pixel dimensions."""
    log2_width = resolution_to_log2(width)
    log2_height = resolution_to_log2(height)
    graph.setInputPropertyValueFromId("$outputsize", output_size_value(int(log2_width), int(log2_height)))


def resolution_to_log2(value: int | str) -> int:
    """Return the log2 exponent for a power-of-two preview resolution."""
    number = int(value)
    log2_value = 0
    current = 1
    while current < number:
        current *= 2
        log2_value += 1
    if current != number:
        raise ValueError("Preview resolution must be a power of two, got {}".format(value))
    return log2_value


def set_graph_output_size_log2(graph: GraphOutputSizeHost, width_log2: int, height_log2: int) -> JsonMap:
    """Set the graph output size from log2 dimensions and return the command payload."""
    width_value = int(width_log2)
    height_value = int(height_log2)
    graph.setInputPropertyValueFromId("$outputsize", output_size_value(width_value, height_value))
    return {
        "graph": graph.getIdentifier(),
        "width_log2": width_log2,
        "height_log2": height_log2,
        "size": "{}x{}".format(2**width_value, 2**height_value),
    }


def set_graph_output_size_pixels(graph: GraphOutputSizeHost, size: JsonValue) -> JsonMap:
    """Set graph output size from pixel dimensions."""
    width, height = normalize_resolution_size(size)
    width_log2 = resolution_to_log2(width)
    height_log2 = resolution_to_log2(height)
    return set_graph_output_size_log2(graph, width_log2, height_log2)
