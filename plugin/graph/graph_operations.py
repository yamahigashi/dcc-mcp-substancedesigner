"""Graph package, resource, and layout operation helpers."""

from __future__ import annotations

import os
import re

from sd.api.sdbasetypes import float2

from ..json_types import JsonMap
from .graph_types import GraphFactory, GraphResource, HostPackage, PackageManager, UiManager


def create_package(package_manager: PackageManager, file_path: str | None) -> JsonMap:
    """Create a user package and optionally save it immediately."""
    package = package_manager.newUserPackage()
    if file_path:
        ensure_parent_dir(file_path)
        package_manager.savePackageAs(package, file_path)
    user_packages = list(package_manager.getUserPackages())
    return {
        "file_path": package.getFilePath(),
        "package_index": package_index(user_packages, package),
        "message": "New package created." if file_path else "New package created. Use save_package to save it.",
    }


def save_package(package_manager: PackageManager, package: HostPackage, file_path: str | None) -> JsonMap:
    """Save a package to an explicit path or its existing path."""
    if file_path:
        ensure_parent_dir(file_path)
        package_manager.savePackageAs(package, file_path)
        return {"saved_to": file_path}
    current_path = package.getFilePath()
    if not current_path:
        raise ValueError("Package has no file path. Use file_path parameter to specify.")
    package_manager.savePackage(package)
    return {"saved_to": current_path}


def package_index(user_packages: list[HostPackage], package: HostPackage) -> int | None:
    """Return the index of a package in the user package list."""
    for index, user_package in enumerate(user_packages):
        if user_package is package:
            return index
    return len(user_packages) - 1 if user_packages else None


def ensure_parent_dir(file_path: str) -> None:
    """Create a file path parent directory when needed."""
    target_dir = os.path.dirname(os.path.abspath(file_path))
    if os.path.exists(target_dir):
        return
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as exc:
        raise ValueError("Cannot create directory '{}': {}".format(target_dir, exc)) from exc


def sanitize_identifier(name: str | None) -> str:
    """Return a Substance Designer-safe graph identifier."""
    if not name:
        return "MCP_Graph"
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if sanitized and not sanitized[0].isalpha():
        sanitized = "G_" + sanitized
    return sanitized or "MCP_Graph"


def create_graph(graph_factory: GraphFactory, package: HostPackage, graph_name: str) -> JsonMap:
    """Create a composition graph in a package."""
    safe_name = sanitize_identifier(graph_name)
    graph = graph_factory(package)
    graph.setIdentifier(safe_name)
    return {
        "identifier": graph.getIdentifier(),
        "requested_name": graph_name,
        "sanitized_name": safe_name,
        "type": graph.getClassName(),
        "package": package.getFilePath(),
    }


def delete_graph(package: HostPackage, graph_identifier: str) -> JsonMap:
    """Delete a graph resource from a package."""
    for resource in list(package.getChildrenResources(False)):
        try:
            if resource.getIdentifier() == graph_identifier:
                resource.delete()
                return {"deleted": graph_identifier}
        except Exception:
            pass
    raise ValueError("Graph '{}' not found.".format(graph_identifier))


def open_graph(ui_manager: UiManager, graph: GraphResource, graph_identifier: str) -> JsonMap:
    """Open a graph in the host editor and return the operation result."""
    try:
        ui_manager.openResourceInEditor(graph)
        return {"opened": graph_identifier, "success": True}
    except Exception as exc:
        return {"opened": graph_identifier, "warning": str(exc)}


def arrange_graph_nodes(
    graph: GraphResource,
    start_x: int | float,
    start_y: int | float,
    node_spacing_x: int | float,
    node_spacing_y: int | float,
) -> JsonMap:
    """Arrange graph nodes in a simple grid and return the command payload."""
    nodes = list(graph.getNodes())
    if not nodes:
        return {"graph": graph.getIdentifier(), "arranged_nodes": 0, "warning": "No nodes to arrange."}

    per_row = max(1, int(len(nodes) ** 0.5) + 1)
    x_value = float(start_x)
    y_value = float(start_y)
    for index, node in enumerate(nodes):
        try:
            node.setPosition(float2(x_value, y_value))
        except Exception:
            pass
        x_value += float(node_spacing_x)
        if (index + 1) % per_row == 0:
            x_value = float(start_x)
            y_value += float(node_spacing_y)

    return {
        "graph": graph.getIdentifier(),
        "arranged_nodes": len(nodes),
        "warning": "arrange_nodes can destroy all connections. Prefer move_node.",
    }
