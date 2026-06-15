"""Validated connection execution helpers."""

from __future__ import annotations

from .connection_ports import node_input_ids, node_output_ids
from .connection_types import ConnectableNode


def safe_connect(
    from_node: ConnectableNode,
    from_output: str,
    to_node: ConnectableNode,
    to_input: str,
    system_params: frozenset[str],
) -> bool:
    """Connect nodes after validating visible port identifiers."""
    output_ids = node_output_ids(from_node)
    input_ids = node_input_ids(to_node, system_params)
    if output_ids and from_output not in output_ids:
        raise ValueError(
            "Output port '{}' not found on node '{}'. Available: {}".format(
                from_output,
                from_node.getIdentifier(),
                sorted(output_ids),
            )
        )
    if input_ids and to_input not in input_ids:
        raise ValueError(
            "Input port '{}' not found on node '{}'. Available: {}".format(
                to_input,
                to_node.getIdentifier(),
                sorted(input_ids),
            )
        )

    try:
        connection = from_node.newPropertyConnectionFromId(from_output, to_node, to_input)
    except Exception as exc:
        if to_input in input_ids and _looks_like_item_not_found(exc):
            raise RuntimeError(
                "not_a_wire_input: Property '{}' on node '{}' is a node parameter, not a connectable graph input "
                "socket. Use bind_parameter_input for parameter bindings.".format(
                    to_input,
                    to_node.getIdentifier(),
                )
            ) from exc
        raise
    if connection is None:
        raise RuntimeError(
            "Connection failed: {}.{} -> {}.{}".format(
                from_node.getIdentifier(),
                from_output,
                to_node.getIdentifier(),
                to_input,
            )
        )
    return True


def _looks_like_item_not_found(exc: Exception) -> bool:
    """Return whether an SD API exception indicates a missing connection socket."""
    text = "{} {}".format(type(exc).__name__, exc)
    return "ItemNotFound" in text
