"""Connection command mixins."""

from __future__ import annotations

from typing import cast

from ..host.host_resources import node_identifier
from ..json_types import JsonValue
from ..node.node_catalog import SYSTEM_PARAMS
from .command_host_context import CommandHostMixin
from .connection_command_payloads import connect_nodes_payload, disconnect_node_input
from .connection_types import ConnectableNode, DisconnectableNode


class DirectConnectCommandMixin(CommandHostMixin):
    """Bridge command method for direct graph connections."""

    def connect_nodes(
        self,
        from_node_id: JsonValue,
        to_node_id: JsonValue,
        from_output: JsonValue = None,
        to_input: JsonValue = None,
        output: JsonValue = None,
        input: JsonValue = None,
        graph_identifier: str | None = None,
    ) -> JsonValue:
        """Connect one node output to another node input."""
        graph = self._resolve_graph(graph_identifier)
        from_node_id = node_identifier(from_node_id, "from_node_id")
        to_node_id = node_identifier(to_node_id, "to_node_id")
        from_node = self._find_node(graph, from_node_id)
        to_node = self._find_node(graph, to_node_id)
        return connect_nodes_payload(
            from_node_id,
            to_node_id,
            cast(ConnectableNode, from_node),
            cast(ConnectableNode, to_node),
            from_output if from_output is not None else output,
            to_input if to_input is not None else input,
            SYSTEM_PARAMS,
        )


class DisconnectCommandMixin(CommandHostMixin):
    """Bridge command method for disconnecting graph inputs."""

    def disconnect_nodes(
        self,
        node_id: JsonValue,
        input_id: JsonValue = None,
        input: JsonValue = None,
        graph_identifier: str | None = None,
    ) -> JsonValue:
        """Disconnect a node input."""
        graph = self._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = self._find_node(graph, node_id)
        return disconnect_node_input(
            cast(DisconnectableNode, node), node_id, input_id if input_id is not None else input
        )
