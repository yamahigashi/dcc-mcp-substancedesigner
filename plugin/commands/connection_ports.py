"""Port inspection helpers."""

from __future__ import annotations

from .connection_types import ConnectableNode, DisconnectableNode, SDPropertyCategory


def node_output_ids(node: ConnectableNode) -> set[str]:
    """Return visible output property identifiers."""
    try:
        return {prop.getId() for prop in list(node.getProperties(SDPropertyCategory.Output))}
    except Exception:
        return set()


def node_input_ids(node: ConnectableNode | DisconnectableNode, system_params: frozenset[str]) -> set[str]:
    """Return visible input property identifiers excluding system params."""
    try:
        return {
            prop.getId()
            for prop in list(node.getProperties(SDPropertyCategory.Input))
            if prop.getId() not in system_params
        }
    except Exception:
        return set()
