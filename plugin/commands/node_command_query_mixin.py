"""Node query and preview bridge command mixins."""

from __future__ import annotations

from typing import cast

from ..controls import (
    GraphResolver,
    MutableValueOwner,
    NodeFinder,
    ParameterSetter,
    ValueOwner,
    list_controls,
    list_graph_inputs,
    property_value,
    set_controls,
    set_graph_input,
)
from ..host.host_resources import node_identifier
from ..host.host_runtime import QT_BINDING_USED
from ..host.host_types import HostGraph
from ..json_types import JsonMap, JsonValue
from ..library.library_nodes import load_package
from ..library.library_types import LibraryPackageManager
from ..nested_graph.nested_graph_operations import bind_parameter_input_command, find_node_property
from ..nested_graph.nested_graph_types import GraphResolver as NestedGraphResolver
from ..nested_graph.nested_graph_types import NodeDefinitionGetter, OwnerNode
from ..nested_graph.nested_graph_types import NodeFinder as NestedNodeFinder
from ..node.node_catalog import SYSTEM_PARAMS
from ..node.node_queries import InspectableGraph, InspectablePackageManager, get_node_def_id, get_node_detail
from ..node.node_queries import inspect_node as inspect_node_payload
from ..node.node_types import DetailNode
from ..parameters.parameters import value_input
from ..parameters.sd_values import infer_value_type
from ..preview.preview_outputs import export_node_output_texture, find_node_output_property
from ..preview.preview_render import RenderGraph, RenderNode, render_node_preview
from ..preview.view_capture import capture_graph_3d_view
from ..sd_serialization import serialize_sd_value
from .command_protocols import NodeCommandHost


class NodeInspectionCommandMixin:
    """Node detail inspection commands."""

    def get_node_info(self, node_id: JsonValue, graph_identifier: str | None = None) -> JsonMap:
        """Return detailed node metadata and parameter values."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        try:
            node = host._find_node(graph, node_id)
        except ValueError as exc:
            raise NodeLookupErrorWithDetails(
                str(exc),
                {
                    "node_id": node_id,
                    "requested_graph_identifier": graph_identifier,
                    "resolved_graph_identifier": _safe_graph_identifier(graph),
                    "current_graph": _safe_current_graph_identifier(host),
                    "candidate_graphs": _safe_candidate_graph_identifiers(host),
                    "hint": (
                        "Graph identifier was omitted or did not resolve to a graph containing this node. "
                        "Retry with graph_identifier or call get_scene to inspect current_graph."
                    ),
                },
            ) from exc
        detail = get_node_detail(node_id, cast(DetailNode, node), SYSTEM_PARAMS, serialize_sd_value)
        resolved_graph_identifier = _safe_graph_identifier(graph)
        detail["graph_identifier"] = resolved_graph_identifier
        detail["resolved_graph_identifier"] = resolved_graph_identifier
        return detail

    def inspect_node(
        self,
        node_id: JsonValue = None,
        definition_id: str | None = None,
        resource_url: str | None = None,
        property_id: str | None = None,
        graph_identifier: str | None = None,
    ) -> JsonMap:
        """Inspect an existing node or a temporary node by definition/resource."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        resolved_node_id = node_identifier(node_id) if node_id is not None else None
        existing_node = host._find_node(graph, resolved_node_id) if resolved_node_id is not None else None
        return inspect_node_payload(
            graph=cast(InspectableGraph, graph),
            package_manager=cast(InspectablePackageManager, host._pkg_mgr()),
            existing_node=cast(DetailNode, existing_node) if existing_node is not None else None,
            node_id=resolved_node_id,
            definition_id=definition_id,
            resource_url=resource_url,
            property_id=property_id,
            system_params=SYSTEM_PARAMS,
            serialize_value=serialize_sd_value,
        )

    def list_controls(self, target: JsonValue) -> JsonMap:
        """Return editable controls for a graph, node, or node property target."""
        host = cast(NodeCommandHost, self)
        return list_controls(
            target,
            resolve_graph=cast(GraphResolver, host._resolve_graph),
            find_node=cast(NodeFinder, host._find_node),
            serialize_value=serialize_sd_value,
        )

    def set_controls(self, target: JsonValue, updates: JsonValue) -> JsonMap:
        """Set editable controls for a graph, node, or node property target."""
        host = cast(NodeCommandHost, self)
        return set_controls(
            target,
            updates,
            resolve_graph=cast(GraphResolver, host._resolve_graph),
            find_node=cast(NodeFinder, host._find_node),
            serialize_value=serialize_sd_value,
            set_node_params=cast(ParameterSetter, host._set_node_params),
        )

    def list_graph_inputs(self, graph_identifier: str | None = None) -> JsonMap:
        """Return graph input controls using the focused graph-input surface."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        result = list_graph_inputs(cast(MutableValueOwner, graph), serialize_sd_value)
        result["graph_identifier"] = graph.getIdentifier()
        return result

    def set_graph_input(
        self,
        input_id: str | None = None,
        value: JsonValue = None,
        value_type: str | None = None,
        graph_identifier: str | None = None,
        target: JsonValue = None,
        mode: str = "replace",
        description: str | None = None,
        group: str | None = None,
        min: JsonValue = None,
        max: JsonValue = None,
        step: JsonValue = None,
        clamp: JsonValue = None,
        editor: str | None = None,
    ) -> JsonMap:
        """Create or set one graph input value, optionally binding a node parameter."""
        host = cast(NodeCommandHost, self)
        if target is not None:
            result = self._bind_graph_input_target(
                target,
                input_id,
                value,
                value_type,
                graph_identifier,
                mode,
                {
                    "description": description,
                    "group": group,
                    "min": min,
                    "max": max,
                    "step": step,
                    "clamp": clamp,
                    "editor": editor,
                },
            )
            result["operation"] = "set_graph_input"
            result["status"] = "bound"
            return result
        if input_id is None:
            raise ValueError("input_id is required when target is omitted.")
        graph = host._resolve_graph(graph_identifier)
        metadata: JsonMap = {}
        for key, item in {
            "description": description,
            "group": group,
            "min": min,
            "max": max,
            "step": step,
            "clamp": clamp,
            "editor": editor,
        }.items():
            if item is not None:
                metadata[key] = item
        result = set_graph_input(
            cast(MutableValueOwner, graph),
            input_id,
            value,
            value_type,
            serialize_sd_value,
            metadata,
        )
        result["graph_identifier"] = graph.getIdentifier()
        return result

    def _bind_graph_input_target(
        self,
        target: JsonValue,
        input_id: str | None,
        value: JsonValue,
        value_type: str | None,
        graph_identifier: str | None,
        mode: str,
        metadata: JsonMap,
    ) -> JsonMap:
        """Bind a target node property through the graph-input convenience surface."""
        host = cast(NodeCommandHost, self)
        if not isinstance(target, dict):
            raise ValueError("target must be an object.")
        target_payload = dict(target)
        if graph_identifier is not None and "graph_identifier" not in target_payload:
            target_payload["graph_identifier"] = graph_identifier
        property_id = target_payload.get("property") or target_payload.get("property_id")
        if not isinstance(property_id, str) or not property_id:
            raise ValueError("target.property is required for graph input binding.")
        resolved_input_id = input_id or property_id
        input_payload: JsonMap = {"id": resolved_input_id}
        if value_type is not None:
            input_payload["value_type"] = value_type
        if value is None:
            current_value = self._target_property_value(target_payload)
            if current_value is None:
                raise ValueError(
                    "value was omitted and target property '{}' did not expose a readable current value. "
                    "Call get_node_detail or list_controls, then retry set_graph_input with value.".format(property_id)
                )
            input_payload["default"] = current_value
            if value_type is None:
                input_payload["value_type"] = infer_value_type(value_input(current_value))
        else:
            input_payload["default"] = value
            if value_type is None:
                input_payload["value_type"] = infer_value_type(value_input(value))
        for key, item in metadata.items():
            if item is not None:
                input_payload[key] = item
        return bind_parameter_input_command(
            target_payload,
            input_payload,
            mode,
            cast(NestedGraphResolver, host._resolve_graph),
            cast(NestedNodeFinder, host._find_node),
            host._set_node_params,
            host._safe_connect,
            cast(NodeDefinitionGetter, get_node_def_id),
        )

    def _target_property_value(self, target: JsonMap) -> JsonValue:
        """Return the current value for a target node property when readable."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(
            cast(
                str | None, target.get("graph_identifier") if isinstance(target.get("graph_identifier"), str) else None
            )
        )
        node_id = target.get("node_id")
        if node_id is None:
            return None
        node = host._find_node(graph, node_identifier(node_id))
        property_id = target.get("property") or target.get("property_id")
        if not isinstance(property_id, str):
            return None
        prop = find_node_property(cast(OwnerNode, node), property_id)
        return property_value(cast(ValueOwner, node), prop, serialize_sd_value)


class NodePreviewCommandMixin:
    """Unified preview rendering commands."""

    def get_preview(
        self,
        node_id: JsonValue = None,
        graph_identifier: str | None = None,
        node_output_id: str | None = None,
        channel: str = "rgba",
        resolution: str = "small",
        timeout_ms: int = 10000,
        width: int | None = None,
        height: int | None = None,
    ) -> JsonMap:
        """Compute a unified preview for a node output or graph 3D view."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        try:
            if node_id is None:
                return capture_graph_3d_view(
                    graph,
                    host._ui_mgr(),
                    graph_identifier,
                    resolution,
                    int(timeout_ms),
                    QT_BINDING_USED,
                    width,
                    height,
                )
            node_id = node_identifier(node_id)
            node = host._find_node(graph, node_id)
            return render_node_preview(
                cast(RenderGraph, graph),
                cast(RenderNode, node),
                node_id,
                node_output_id,
                channel,
                resolution,
                int(timeout_ms),
                host._preview_cache,
                QT_BINDING_USED,
            )
        except Exception as exc:
            return preview_error_payload(exc, node_id, graph_identifier, node_output_id)

    def export_output(
        self,
        node_id: JsonValue,
        file_path: str,
        graph_identifier: str | None = None,
        node_output_id: str | None = None,
    ) -> JsonMap:
        """Compute a node output and save it to a caller-provided file path."""
        host = cast(NodeCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        node_id = node_identifier(node_id)
        node = host._find_node(graph, node_id)
        output_prop = find_node_output_property(cast(RenderNode, node), node_output_id)
        exported = export_node_output_texture(cast(RenderGraph, graph), cast(RenderNode, node), output_prop, file_path)
        return {
            "status": "exported",
            "node_id": exported["node_id"],
            "node_output_id": exported["node_output_id"],
            "graph_identifier": graph.getIdentifier(),
            "file_path": exported["file_path"],
            "format": exported["format"],
        }


def preview_error_payload(
    exc: Exception,
    node_id: JsonValue,
    graph_identifier: str | None,
    node_output_id: str | None,
) -> JsonMap:
    """Return structured preview diagnostics for render/capture failures."""
    message = str(exc)
    return {
        "status": "error",
        "message": message,
        "node_id": node_id,
        "graph_identifier": graph_identifier,
        "node_output_id": node_output_id,
        "diagnostics": [
            {
                "severity": "error",
                "stage": "render",
                "message": message,
                "exception_type": type(exc).__name__,
            }
        ],
    }


class NodeLibraryCommandMixin:
    """Library package commands for instance nodes."""

    def load_package(self, path: str | None = None, package_name: str | None = None) -> JsonValue:
        """Load a Substance Designer package by path or package file name."""
        package_name_or_path = path or package_name
        if not package_name_or_path:
            raise ValueError("path or package_name is required.")
        host = cast(NodeCommandHost, self)
        return load_package(cast(LibraryPackageManager, host._pkg_mgr()), package_name_or_path)


class NodeLookupErrorWithDetails(ValueError):
    """Node lookup failure with MCP-facing graph diagnostics."""

    def __init__(self, message: str, details: JsonMap) -> None:
        """Store a message and JSON-safe diagnostic details."""
        super().__init__(message)
        self.details = details


def _safe_graph_identifier(graph: HostGraph) -> str | None:
    getter = getattr(graph, "getIdentifier", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return str(value) if value is not None else None


def _safe_current_graph_identifier(host: NodeCommandHost) -> str | None:
    try:
        graph = host._ui_mgr().getCurrentGraph()
    except Exception:
        return None
    if graph is None:
        return None
    return _safe_graph_identifier(graph)


def _safe_candidate_graph_identifiers(host: NodeCommandHost) -> list[str]:
    result: list[str] = []
    try:
        packages = list(host._pkg_mgr().getUserPackages())
    except Exception:
        return result
    for package in packages:
        try:
            resources = list(package.getChildrenResources(False))
        except Exception:
            continue
        for resource in resources:
            try:
                if "SDSBSCompGraph" not in resource.getClassName():
                    continue
            except Exception:
                continue
            identifier = _safe_graph_identifier(resource)
            if identifier:
                result.append(identifier)
    return result
