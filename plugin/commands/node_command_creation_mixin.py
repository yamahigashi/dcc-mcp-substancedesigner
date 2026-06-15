"""Node creation bridge command mixin."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from ..graph.graph_frames import FrameGraph, FrameNode
from ..graph.graph_frames import create_frame as create_frame_payload
from ..host.host_resources import node_identifier
from ..json_types import JsonMap, JsonValue
from ..node.node_operations import create_instance_node as create_instance_node_payload
from ..node.node_operations import create_node as create_node_payload
from ..node.node_operations import create_output_node as create_output_node_payload
from ..node.node_types import MutableGraph, ResourcePackageManager
from .command_protocols import NodeCommandHost


class NodeCreationCommandMixin:
    """Node creation command implementations."""

    def create_node(
        self,
        definition_id: str | None = None,
        definition: str | None = None,
        node_type: str | None = None,
        resource_url: str | None = None,
        graph_identifier: str | None = None,
        position: JsonValue = None,
    ) -> JsonMap:
        """Create a regular node in a graph."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        definition_id = node_definition_id(definition_id, definition, node_type, resource_url)
        if definition_id.startswith("pkg://"):
            return create_instance_node_payload(
                cast(MutableGraph, graph), cast(ResourcePackageManager, host._pkg_mgr()), definition_id, position
            )
        return create_node_payload(cast(MutableGraph, graph), definition_id, position)

    def create_instance_node(
        self,
        resource_url: str,
        graph_identifier: str | None = None,
        position: JsonValue = None,
        package_hint: JsonValue = None,
    ) -> JsonMap:
        """Create a library instance node from a resource URL."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        return create_instance_node_payload(
            cast(MutableGraph, graph),
            cast(ResourcePackageManager, host._pkg_mgr()),
            resource_url,
            position,
            package_hint,
        )

    def create_output_node(
        self,
        usage: str = "baseColor",
        graph_identifier: str | None = None,
        position: JsonValue = None,
    ) -> JsonMap:
        """Create a graph output node for a PBR usage."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        return create_output_node_payload(cast(MutableGraph, graph), usage, position)

    def create_frame(
        self,
        label: str,
        node_ids: Sequence[JsonValue] | None = None,
        description: str = "",
        graph_identifier: str | None = None,
        position: JsonValue = None,
        size: JsonValue = None,
        padding: float = 160.0,
        color: JsonValue = None,
    ) -> JsonMap:
        """Create a graph frame for visual grouping and user-facing labels."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_ids = [node_identifier(node_id, "node_ids") for node_id in node_ids or ()]
        nodes = [host._find_node(graph, node_id) for node_id in node_ids or ()]
        return create_frame_payload(
            cast(FrameGraph, graph),
            [cast(FrameNode, node) for node in nodes],
            label,
            description,
            position,
            size,
            padding,
            color,
        )


def node_definition_id(
    definition_id: str | None,
    definition: str | None,
    node_type: str | None,
    resource_url: str | None,
) -> str:
    """Resolve common node creation aliases into a definition id or pkg URL."""
    raw = resource_url or definition_id or definition or node_type
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("definition_id, definition, node_type, or resource_url is required.")
    if raw.startswith("pkg://") or "::" in raw:
        return raw
    return "sbs::compositing::{}".format(raw)
