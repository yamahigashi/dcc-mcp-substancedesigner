"""Scene and graph diagnostic query helpers."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from typing import cast

from sd.api.sdproperty import SDPropertyCategory

from ..json_types import JsonMap, JsonValue
from ..node.node_queries import (
    get_connection_ref_output,
    get_node_def_id,
    get_node_pos,
    get_property_info,
)
from ..node.node_types import GraphPackageSource, HostProperty
from ..node.node_types import HostPackage as NodeHostPackage
from ..sd_serialization import serialize_sd_value
from .graph_types import (
    GraphConnection,
    GraphNode,
    GraphResource,
    QueryGraph,
    ScenePackage,
    ScenePackageManager,
    SceneUiManager,
)


def scene_info(
    package_manager: ScenePackageManager,
    ui_manager: SceneUiManager,
    sd_version: str,
    plugin_version: str,
) -> JsonMap:
    """Return the host scene inventory summary."""
    current_graph = current_graph_or_none(ui_manager)
    current_graph_id = current_graph.getIdentifier() if current_graph is not None else None
    packages = [package_info(package) for package in list(package_manager.getUserPackages())]
    return {
        "packages": packages,
        "package_count": len(packages),
        "current_graph": current_graph_id,
        "current_graph_node_count": graph_node_count(current_graph),
        "sd_version": sd_version,
        "plugin_version": plugin_version,
    }


def diagnostic(
    package_manager: ScenePackageManager,
    ui_manager: SceneUiManager,
    sd_version: str | None,
    sd_version_error: str | None,
    qt_binding: str,
    pyside_path: str,
    qt_invoker_ok: bool,
    library_cache_entries: int,
    standard_library_preload: list[JsonValue] | None = None,
    command_registry: list[str] | None = None,
    preview_cache_path: str | None = None,
    preview_cache_entries: int | None = None,
) -> JsonMap:
    """Return plugin runtime diagnostic data."""
    results: JsonMap = {
        "sd_running": sd_version is not None,
        "qt_binding": qt_binding,
        "pyside_path": pyside_path,
        "qt_invoker_ok": qt_invoker_ok,
        "library_cache_entries": library_cache_entries,
        "plugin_path": plugin_root_path(),
        "command_registry": command_registry or [],
        "preview_cache_path": preview_cache_path,
        "preview_cache_entries": preview_cache_entries,
        "bridge_hash": bridge_hash(command_registry or []),
        "bridge_hash_source": "plugin_command_registry",
        "standard_library_preload": standard_library_preload or [],
    }
    if sd_version is not None:
        results["sd_version"] = sd_version
    if sd_version_error is not None:
        results["sd_version_error"] = sd_version_error
    add_package_diagnostics(results, package_manager)
    add_current_graph_diagnostics(results, ui_manager)
    return results


def plugin_root_path() -> str:
    """Return the installed plugin root path."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bridge_hash(command_registry: list[str]) -> str:
    """Return a stable diagnostic hash for the running command surface."""
    payload = "\n".join(sorted(command_registry))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def graph_info(graph: QueryGraph, node_limit: int, include_connections: bool) -> JsonMap:
    """Return detailed graph node and connection info."""
    all_nodes = list(graph.getNodes())
    limited_nodes = all_nodes[:node_limit] if node_limit > 0 else []
    return {
        "identifier": graph.getIdentifier(),
        "package_path": get_graph_package_path(graph),
        "node_count": len(all_nodes),
        "nodes": [node_info(node, include_connections) for node in limited_nodes],
        "truncated": len(all_nodes) > node_limit,
        "node_limit": node_limit,
    }


def package_info(package: ScenePackage) -> JsonMap:
    """Return serializable package inventory data."""
    try:
        graphs = [resource_info(resource) for resource in list(package.getChildrenResources(False))]
        return {"file_path": package.getFilePath(), "graphs": graphs}
    except Exception as exc:
        return {"error": str(exc)}


def resource_info(resource: GraphResource) -> JsonMap:
    """Return serializable package resource data."""
    try:
        class_name = resource.getClassName()
        node_count = graph_node_count(resource) if "CompGraph" in class_name or "SDGraph" in class_name else 0
        return {"identifier": resource.getIdentifier(), "type": class_name, "node_count": node_count}
    except Exception as exc:
        return {"error": str(exc)}


def current_graph_or_none(ui_manager: SceneUiManager) -> QueryGraph | None:
    """Return the current graph, ignoring host failures."""
    try:
        return ui_manager.getCurrentGraph()
    except Exception:
        return None


def graph_node_count(graph: QueryGraph | GraphResource | None) -> int:
    """Return a graph node count, ignoring host failures."""
    if graph is None:
        return 0
    try:
        return len(list(graph.getNodes()))
    except Exception:
        return 0


def add_package_diagnostics(results: JsonMap, package_manager: ScenePackageManager) -> None:
    """Add package diagnostics to a result mapping."""
    try:
        packages = list(package_manager.getUserPackages())
        results["user_packages"] = len(packages)
        results["package_files"] = [package.getFilePath() for package in packages]
    except Exception as exc:
        results["packages_error"] = str(exc)


def add_current_graph_diagnostics(results: JsonMap, ui_manager: SceneUiManager) -> None:
    """Add current graph diagnostics to a result mapping."""
    try:
        graph = ui_manager.getCurrentGraph()
        if graph:
            results["current_graph"] = graph.getIdentifier()
            results["current_graph_nodes"] = graph_node_count(graph)
        else:
            results["current_graph"] = None
    except Exception as exc:
        results["current_graph_error"] = str(exc)


def get_graph_package_path(graph: GraphPackageSource) -> str | None:
    """Return a graph package path or URL when the host exposes it."""
    for method_name in ("getPackage", "getParentPackage"):
        try:
            package_getter = cast(Callable[[], NodeHostPackage | None], getattr(graph, method_name))
            package = package_getter()
            if package is not None:
                path = package.getFilePath()
                if path:
                    return path
        except Exception:
            pass
    try:
        url = graph.getUrl()
        if url:
            return url
    except Exception:
        pass
    return None


def node_info(node: GraphNode, include_connections: bool) -> JsonMap:
    """Return graph summary data for one node."""
    info: JsonMap = {
        "identifier": node.getIdentifier(),
        "definition": get_node_def_id(node),
        "position": get_node_pos(node),
        "connections": [],
    }
    if info["definition"] == "sbs::compositing::output":
        info["annotations"] = annotation_values(node)
    if include_connections:
        info["connections"] = input_connections(node)
    return info


def annotation_values(node: GraphNode) -> list[JsonValue]:
    """Return lightweight annotation values for graph output nodes."""
    values: list[JsonValue] = []
    for prop in annotation_properties(node):
        info = get_property_info(prop)
        try:
            value = node.getPropertyValue(prop)
            if value is not None:
                info["value"] = serialize_sd_value(value)
        except Exception:
            pass
        values.append(info)
    return values


def annotation_properties(node: GraphNode) -> list[HostProperty]:
    """Return annotation properties for a graph node."""
    try:
        return list(node.getProperties(SDPropertyCategory.Annotation))
    except Exception:
        return []


def input_connections(node: GraphNode) -> list[JsonValue]:
    """Return input connection metadata for a node."""
    connections: list[JsonValue] = []
    for prop in node_input_properties(node):
        property_id = prop.getId()
        for connection in property_connections(node, prop):
            source_node = connection.getInputPropertyNode()
            source_property = connection.getInputProperty()
            if source_node is None or source_property is None:
                continue
            connection_info: JsonMap = {
                "input": property_id,
                "from_node": source_node.getIdentifier(),
                "from_output": source_property.getId(),
                "from_output_uid": get_property_info(source_property).get("uid"),
            }
            ref_output = get_connection_ref_output(connection)
            if ref_output is not None:
                connection_info["connRefOutput"] = ref_output
            connections.append(connection_info)
    return connections


def node_input_properties(node: GraphNode) -> list[HostProperty]:
    """Return input properties for a graph node."""
    try:
        return list(node.getProperties(SDPropertyCategory.Input))
    except Exception:
        return []


def property_connections(node: GraphNode, prop: HostProperty) -> list[GraphConnection]:
    """Return input property connections for a node."""
    try:
        connections = node.getPropertyConnections(prop)
        return list(connections) if connections is not None else []
    except Exception:
        return []
