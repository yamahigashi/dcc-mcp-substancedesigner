"""Graph frame creation helpers for visual grouping."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, cast

from sd.api.sdbasetypes import ColorRGBA, float2
from sd.api.sdgraphobjectframe import SDGraphObjectFrame

from ..input_normalization import normalize_color, normalize_float2
from ..json_types import JsonMap, JsonValue
from ..node.node_queries import get_node_pos
from ..node.node_types import HostNode

if TYPE_CHECKING:
    from sd.api.sdgraph import SDGraph

DEFAULT_FRAME_COLOR: tuple[float, float, float, float] = (0.2, 0.5, 0.7, 0.18)
DEFAULT_FRAME_SIZE: tuple[float, float] = (480.0, 320.0)


class FrameGraph(Protocol):
    """Protocol for graphs that can own graph object frames."""


class FrameNode(Protocol):
    """Protocol for nodes used to derive frame bounds."""

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        ...

    def getPosition(self) -> FramePosition:
        """Return the node position."""
        ...


class FramePosition(Protocol):
    """Protocol for graph editor positions."""

    x: float
    y: float


class FrameObject(Protocol):
    """Protocol for Substance Designer graph object frames."""

    def setPosition(self, position: float2) -> None:
        """Set the frame position."""
        ...

    def setSize(self, size: float2) -> None:
        """Set the frame size."""
        ...

    def setTitle(self, title: str) -> None:
        """Set the frame title."""
        ...

    def setDescription(self, description: str) -> None:
        """Set the frame description."""
        ...

    def setColor(self, color: ColorRGBA) -> None:
        """Set the frame color."""
        ...


def create_frame(
    graph: FrameGraph,
    nodes: Sequence[FrameNode],
    label: str,
    description: str,
    position: JsonValue,
    size: JsonValue,
    padding: float,
    color: JsonValue,
) -> JsonMap:
    """Create a frame around explicit bounds or target nodes."""
    if not label.strip():
        raise ValueError("label must be a non-empty string.")
    frame_position, frame_size = resolve_frame_bounds(nodes, position, size, padding)
    frame_color = resolve_frame_color(color)
    frame = cast(FrameObject, SDGraphObjectFrame.sNew(cast("SDGraph", graph)))
    frame.setPosition(float2(frame_position[0], frame_position[1]))
    frame.setSize(float2(frame_size[0], frame_size[1]))
    frame.setTitle(label)
    if description:
        frame.setDescription(description)
    frame.setColor(ColorRGBA(frame_color[0], frame_color[1], frame_color[2], frame_color[3]))
    return {
        "label": label,
        "description": description,
        "position": [frame_position[0], frame_position[1]],
        "size": [frame_size[0], frame_size[1]],
        "color": [frame_color[0], frame_color[1], frame_color[2], frame_color[3]],
        "node_ids": [node.getIdentifier() for node in nodes],
        "grouped": bool(nodes),
    }


def resolve_frame_bounds(
    nodes: Sequence[FrameNode],
    position: JsonValue,
    size: JsonValue,
    padding: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Resolve frame position and size from explicit values or node bounds."""
    if position is not None and size is not None:
        return resolve_float2(position, "position"), resolve_float2(size, "size")
    if not nodes:
        resolved_position = resolve_float2(position, "position") if position is not None else (0.0, 0.0)
        resolved_size = resolve_float2(size, "size") if size is not None else DEFAULT_FRAME_SIZE
        return resolved_position, resolved_size
    node_positions = [get_node_pos(cast(HostNode, node)) for node in nodes]
    min_x = min(pos[0] for pos in node_positions) - padding
    min_y = min(pos[1] for pos in node_positions) - padding
    max_x = max(pos[0] for pos in node_positions) + padding
    max_y = max(pos[1] for pos in node_positions) + padding
    resolved_position = resolve_float2(position, "position") if position is not None else (min_x, min_y)
    resolved_size = resolve_float2(size, "size") if size is not None else (max_x - min_x, max_y - min_y)
    return resolved_position, resolved_size


def resolve_frame_color(color: JsonValue) -> tuple[float, float, float, float]:
    """Resolve a four-channel frame color."""
    resolved = normalize_color(color, "color") if color is not None else None
    if resolved is None:
        return DEFAULT_FRAME_COLOR
    return resolved[0], resolved[1], resolved[2], resolved[3]


def resolve_float2(values: JsonValue, field_name: str) -> tuple[float, float]:
    """Resolve a two-channel float value."""
    resolved = normalize_float2(values, field_name)
    if resolved is None:
        raise ValueError("{} must contain two numeric entries.".format(field_name))
    return resolved[0], resolved[1]


def coordinate(value: JsonValue, field_name: str) -> float:
    """Return a scalar graph coordinate."""
    if isinstance(value, (bool, int, float, str)):
        return float(value)
    raise ValueError("{} must be a scalar value.".format(field_name))
