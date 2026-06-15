"""Node editing bridge command mixin."""

from __future__ import annotations

from typing import cast

from ..host.host_resources import node_identifier
from ..json_types import JsonMap, JsonValue
from ..node.node_operations import delete_node as delete_node_payload
from ..node.node_operations import duplicate_node as duplicate_node_payload
from ..node.node_operations import move_node as move_node_payload
from ..node.node_types import MutableGraph
from .command_protocols import NodeCommandHost


class NodeEditingCommandMixin:
    """Node deletion, movement, and duplication command implementations."""

    def delete_node(self, node_id: JsonValue, graph_identifier: str | None = None) -> JsonMap:
        """Delete a node from a graph."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = host._find_node(graph, node_id)
        return delete_node_payload(cast(MutableGraph, graph), node, node_id)

    def move_node(
        self,
        node_id: JsonValue,
        position: JsonValue,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Move a node to a graph editor position."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = host._find_node(graph, node_id)
        return move_node_payload(node, node_id, position)

    def duplicate_node(
        self,
        node_id: JsonValue,
        offset: JsonValue = None,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Duplicate a regular node with an optional offset."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = host._find_node(graph, node_id)
        return duplicate_node_payload(cast(MutableGraph, graph), node, node_id, offset)
