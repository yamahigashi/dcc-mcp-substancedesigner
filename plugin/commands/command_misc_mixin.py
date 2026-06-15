"""Parameter and utility command methods."""

from __future__ import annotations

from typing import cast

from ..graph.graph_operations import arrange_graph_nodes
from ..graph.graph_output_size import GraphOutputSizeHost, set_graph_output_size_log2, set_graph_output_size_pixels
from ..host.host_resources import node_identifier
from ..input_normalization import string_identifier
from ..json_types import JsonMap, JsonValue
from ..node.node_queries import get_node_def_id
from ..parameters.parameter_types import ParameterNode
from ..parameters.parameters import set_parameter_value
from ..plugin_refresh import refresh_plugin_runtime
from .command_host_context import CommandHostMixin


class CommandParameterMixin(CommandHostMixin):
    """Bridge command methods for parameters and graph output size."""

    def set_parameter(
        self,
        node_id: JsonValue,
        parameter_id: JsonValue = None,
        value: JsonValue = None,
        value_type: str = "float",
        property: JsonValue = None,
        property_id: JsonValue = None,
        id: JsonValue = None,
        control: JsonValue = None,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Set a node parameter value."""
        graph = self._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        parameter_id = parameter_identifier(parameter_id, property, property_id, id, control)
        if value is None:
            raise ValueError("value is required.")
        node = self._find_node(graph, node_id)
        if parameter_id == "usage" and get_node_def_id(node) == "sbs::compositing::output":
            parameter_id = "usages"
        return set_parameter_value(cast(ParameterNode, node), node_id, parameter_id, value, value_type)

    def set_node_comment(self, node_id: JsonValue, comment: str, graph_identifier: str | None = None) -> JsonMap:
        """Set the node comment annotation."""
        return self._set_node_text_annotation(node_id, "comment", comment, graph_identifier)

    def _set_node_text_annotation(
        self,
        node_id: JsonValue,
        annotation_id: str,
        value: str,
        graph_identifier: str | None,
    ) -> JsonMap:
        graph = self._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = self._find_node(graph, node_id)
        try:
            result = set_parameter_value(cast(ParameterNode, node), node_id, annotation_id, value, "string")
        except Exception as exc:
            return {
                "node_id": node_id,
                "annotation_id": annotation_id,
                "status": "unsupported",
                "reason": str(exc),
            }
        return {"status": "updated", **result}

    def set_graph_output_size(
        self,
        width_log2: int = 11,
        height_log2: int = 11,
        width: JsonValue = None,
        height: JsonValue = None,
        size: JsonValue = None,
        resolution: JsonValue = None,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Set the graph output size using log2 dimensions."""
        graph = self._resolve_graph(graph_identifier)
        if resolution is not None:
            return set_graph_output_size_pixels(cast(GraphOutputSizeHost, graph), resolution)
        if size is not None:
            return set_graph_output_size_pixels(cast(GraphOutputSizeHost, graph), size)
        if width is not None or height is not None:
            return set_graph_output_size_pixels(
                cast(GraphOutputSizeHost, graph), {"width": width, "height": height or width}
            )
        return set_graph_output_size_log2(cast(GraphOutputSizeHost, graph), width_log2, height_log2)


class CommandUtilityMixin(CommandHostMixin):
    """Bridge command methods for utility actions."""

    def arrange_nodes(
        self,
        graph_identifier: str | None = None,
        start_x: int = -1000,
        start_y: int = 0,
        node_spacing_x: int = 200,
        node_spacing_y: int = 150,
    ) -> JsonMap:
        """Arrange graph nodes with the host layout helper."""
        graph = self._resolve_graph(graph_identifier)
        return arrange_graph_nodes(graph, start_x, start_y, node_spacing_x, node_spacing_y)

    def refresh_plugin(self) -> JsonMap:
        """Reload host plugin implementation modules and swap the bridge handler."""
        import importlib

        root_package = __name__.split(".", 1)[0]
        plugin_module = importlib.import_module(root_package)
        return refresh_plugin_runtime(plugin_module=plugin_module, root_package=root_package)


def parameter_identifier(*values: JsonValue) -> str:
    """Resolve common parameter/property aliases to a property id."""
    for value in values:
        if value is None:
            continue
        try:
            return string_identifier(value, "parameter_id")
        except ValueError:
            continue
    raise ValueError("parameter_id, property, property_id, id, or control is required.")
