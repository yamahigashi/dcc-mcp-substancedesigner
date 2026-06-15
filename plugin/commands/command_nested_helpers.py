"""Nested graph helper callbacks for command handlers."""

from __future__ import annotations

from typing import cast

from ..json_types import JsonMap
from ..nested_graph.nested_graph_types import MutableNestedGraph, MutableNestedNode
from ..node.node_catalog import SYSTEM_PARAMS
from ..parameters.parameter_types import ParameterNode
from ..parameters.parameters import apply_node_params
from .connection_execution import safe_connect
from .connection_types import ConnectableNode


def set_nested_node_params(node: MutableNestedNode, params: JsonMap) -> JsonMap:
    """Apply parameter values to a nested graph node."""
    return cast(JsonMap, apply_node_params(cast(ParameterNode, node), params))


def safe_nested_connect(
    graph: MutableNestedGraph,
    from_node: MutableNestedNode,
    from_out: str,
    to_node: MutableNestedNode,
    to_in: str,
) -> None:
    """Connect nested graph nodes with port validation."""
    del graph
    safe_connect(cast(ConnectableNode, from_node), from_out, cast(ConnectableNode, to_node), to_in, SYSTEM_PARAMS)
