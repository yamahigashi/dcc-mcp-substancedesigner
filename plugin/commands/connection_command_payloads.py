"""Connection command payload builders."""

from __future__ import annotations

from ..input_normalization import optional_string_identifier
from ..json_types import JsonValue
from .connection_execution import safe_connect
from .connection_ports import node_input_ids, node_output_ids
from .connection_types import (
    ConnectableNode,
    ConnectionPayload,
    DisconnectableNode,
    SDPropertyCategory,
)


def connect_nodes_payload(
    from_node_id: str,
    to_node_id: str,
    from_node: ConnectableNode,
    to_node: ConnectableNode,
    from_output: JsonValue,
    to_input: JsonValue,
    system_params: frozenset[str],
) -> ConnectionPayload:
    """Connect two nodes and return a command payload."""
    from_output = resolve_output_port(from_node, from_output)
    to_input = resolve_input_port(to_node, to_input, system_params)
    safe_connect(from_node, from_output, to_node, to_input, system_params)
    return {
        "from_node": from_node_id,
        "from_output": from_output,
        "to_node": to_node_id,
        "to_input": to_input,
        "success": True,
    }


def disconnect_node_input(node: DisconnectableNode, node_id: str, input_id: JsonValue) -> dict[str, str]:
    """Delete all connections from a node input and return a command payload."""
    input_id = resolve_input_port(node, input_id, frozenset())
    prop = node.getPropertyFromId(input_id, SDPropertyCategory.Input)
    if not prop:
        raise ValueError("Property '{}' not found on node '{}'.".format(input_id, node_id))
    node.deletePropertyConnections(prop)
    return {"disconnected": "{}:{}".format(node_id, input_id)}


def resolve_output_port(node: ConnectableNode, value: JsonValue) -> str:
    """Resolve a source output port from an id/object/default request."""
    return resolve_port(value, node_output_ids(node), "output", node.getIdentifier())


def resolve_input_port(
    node: ConnectableNode | DisconnectableNode, value: JsonValue, system_params: frozenset[str]
) -> str:
    """Resolve a target input port from an id/object/default request."""
    return resolve_port(value, node_input_ids(node, system_params), "input", node.getIdentifier())


def resolve_port(value: JsonValue, candidates: set[str], label: str, node_id: str) -> str:
    """Resolve a port request, accepting common object shapes and unambiguous defaults."""
    port = optional_string_identifier(value, "{} port".format(label))
    if port is not None:
        return port
    if len(candidates) == 1:
        return next(iter(candidates))
    if not candidates:
        raise ValueError("No visible {} ports found on node '{}'.".format(label, node_id))
    raise ValueError(
        "{} port is ambiguous on node '{}'. Available: {}".format(label.capitalize(), node_id, sorted(candidates))
    )
