"""Nested graph bridge command mixin for node-owned property graphs."""

from __future__ import annotations

from typing import cast

from ..host.host_resources import node_identifier
from ..json_types import JsonMap, JsonValue
from ..nested_graph.nested_graph_operations import (
    apply_fx_map_graph_patch_command,
    apply_fx_map_graph_state_command,
    apply_nested_graph_patch_command,
    apply_nested_graph_state_command,
    bind_parameter_input_command,
)
from ..nested_graph.nested_graph_queries import get_fx_map_graph_state_payload, get_nested_graph_state_payload
from ..nested_graph.nested_graph_types import (
    GraphResolver,
    NestedOwnerGraph,
    NodeConnector,
    NodeDefinitionGetter,
    NodeFinder,
    NodePositionGetter,
    ParameterSetter,
    PropertyGraphOwner,
)
from ..node.node_queries import get_node_def_id, get_node_pos
from ..sd_serialization import serialize_sd_value
from .command_protocols import NodeCommandHost


class NodeNestedGraphCommandMixin:
    """Node-owned nested graph inspection and application commands."""

    def get_nested_graph_state(
        self,
        node_id: JsonValue,
        property_id: str,
        graph_identifier: str | None = None,
        graph_type: str = "SDSBSFunctionGraph",
    ) -> JsonMap:
        """Return serialized state for a node-owned nested graph."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        owner_node = host._find_node(graph, node_id)
        return get_nested_graph_state_payload(
            cast(NestedOwnerGraph, graph),
            cast(PropertyGraphOwner, owner_node),
            node_id,
            property_id,
            graph_type,
            cast(NodeDefinitionGetter, get_node_def_id),
            cast(NodePositionGetter, get_node_pos),
            serialize_sd_value,
        )

    def get_fx_map_graph_state(
        self,
        node_id: JsonValue,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Return serialized state for an FX-Map node's referenced graph."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        owner_node = host._find_node(graph, node_id)
        return get_fx_map_graph_state_payload(
            cast(NestedOwnerGraph, graph),
            cast(PropertyGraphOwner, owner_node),
            node_id,
            cast(NodeDefinitionGetter, get_node_def_id),
            cast(NodePositionGetter, get_node_pos),
            serialize_sd_value,
        )

    def apply_nested_graph_state(self, state: JsonValue, mode: str = "sync") -> JsonMap:
        """Apply serialized nested graph state."""
        host = cast(NodeCommandHost, self)
        return apply_nested_graph_state_command(
            state,
            mode,
            cast(GraphResolver, host._resolve_graph),
            cast(NodeFinder, host._find_node),
            cast(ParameterSetter, host._set_node_params),
            cast(NodeConnector, host._safe_connect),
            cast(NodeDefinitionGetter, get_node_def_id),
            package_manager=host._pkg_mgr(),
            get_node_position=cast(NodePositionGetter, get_node_pos),
            serialize_value=serialize_sd_value,
        )

    def apply_fx_map_graph_state(self, state: JsonValue, mode: str = "sync") -> JsonMap:
        """Apply serialized FX-Map graph state."""
        host = cast(NodeCommandHost, self)
        return apply_fx_map_graph_state_command(
            state,
            mode,
            cast(GraphResolver, host._resolve_graph),
            cast(NodeFinder, host._find_node),
            cast(ParameterSetter, host._set_node_params),
            cast(NodeConnector, host._safe_connect),
            cast(NodeDefinitionGetter, get_node_def_id),
            package_manager=host._pkg_mgr(),
            get_node_position=cast(NodePositionGetter, get_node_pos),
            serialize_value=serialize_sd_value,
        )

    def apply_nested_graph_patch(self, patch: JsonValue, mode: str = "patch") -> JsonMap:
        """Patch an existing node-owned nested graph without rebuilding it."""
        host = cast(NodeCommandHost, self)
        return apply_nested_graph_patch_command(
            patch,
            mode,
            cast(GraphResolver, host._resolve_graph),
            cast(NodeFinder, host._find_node),
            cast(ParameterSetter, host._set_node_params),
            cast(NodeConnector, host._safe_connect),
            cast(NodeDefinitionGetter, get_node_def_id),
            package_manager=host._pkg_mgr(),
            get_node_position=cast(NodePositionGetter, get_node_pos),
            serialize_value=serialize_sd_value,
        )

    def apply_fx_map_graph_patch(self, patch: JsonValue, mode: str = "patch") -> JsonMap:
        """Patch an existing FX-Map referenced graph without rebuilding it."""
        host = cast(NodeCommandHost, self)
        return apply_fx_map_graph_patch_command(
            patch,
            mode,
            cast(GraphResolver, host._resolve_graph),
            cast(NodeFinder, host._find_node),
            cast(ParameterSetter, host._set_node_params),
            cast(NodeConnector, host._safe_connect),
            cast(NodeDefinitionGetter, get_node_def_id),
            package_manager=host._pkg_mgr(),
            get_node_position=cast(NodePositionGetter, get_node_pos),
            serialize_value=serialize_sd_value,
        )

    def bind_parameter_input(self, target: JsonValue, input: JsonValue, mode: str = "replace") -> JsonMap:
        """Bind a node parameter property to an owner input."""
        host = cast(NodeCommandHost, self)
        return bind_parameter_input_command(
            target,
            input,
            mode,
            cast(GraphResolver, host._resolve_graph),
            cast(NodeFinder, host._find_node),
            cast(ParameterSetter, host._set_node_params),
            cast(NodeConnector, host._safe_connect),
            cast(NodeDefinitionGetter, get_node_def_id),
        )
