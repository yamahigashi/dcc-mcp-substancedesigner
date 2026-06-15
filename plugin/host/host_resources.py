"""Host package, graph, and node resolution helpers."""

from __future__ import annotations

import os

from ..json_types import JsonValue
from .host_types import HostGraph, HostNode, HostPackage, HostPackageManager, HostUiManager


def resolve_package(
    package_manager: HostPackageManager,
    package_index: int = 0,
    package_path: JsonValue = None,
) -> HostPackage:
    """Return a host package by path or index."""
    packages = list(package_manager.getUserPackages())
    package_path = package_path_ref(package_path)
    if package_path:
        requested = comparable_path(package_path)
        for package in packages:
            if package.getFilePath() == package_path or comparable_path(package.getFilePath()) == requested:
                return package
        raise ValueError("Package '{}' not found.".format(package_path))
    if not packages:
        raise ValueError("No user packages loaded. Open a .sbs file first.")
    if package_index < 0:
        raise ValueError("package_index must be >= 0 (got {}).".format(package_index))
    if package_index >= len(packages):
        raise ValueError("Package index {} out of range (have {}).".format(package_index, len(packages)))
    return packages[package_index]


def resolve_graph(
    package_manager: HostPackageManager,
    ui_manager: HostUiManager,
    graph_identifier: JsonValue = None,
) -> HostGraph:
    """Return a graph by identifier, current editor selection, or first package graph."""
    graph_identifier = graph_identifier_ref(graph_identifier)
    if graph_identifier:
        for package in list(package_manager.getUserPackages()):
            for resource in list(package.getChildrenResources(False)):
                try:
                    if resource.getIdentifier() == graph_identifier:
                        return resource
                except Exception:
                    continue
        raise ValueError("Graph '{}' not found.".format(graph_identifier))

    try:
        graph = ui_manager.getCurrentGraph()
        if graph is not None and is_resolvable_package_graph(graph):
            return graph
    except Exception:
        pass

    for package in list(package_manager.getUserPackages()):
        for resource in list(package.getChildrenResources(False)):
            try:
                if "SDSBSCompGraph" in resource.getClassName():
                    return resource
            except Exception:
                continue
    raise ValueError("No graph available. Open a package/graph in SD, or pass graph_identifier.")


def is_resolvable_package_graph(graph: HostGraph) -> bool:
    """Return whether a current graph is a concrete package compositing graph."""
    try:
        if not graph.getIdentifier():
            return False
    except Exception:
        return False
    try:
        return "SDSBSCompGraph" in graph.getClassName()
    except Exception:
        return True


def node_identifier(value: JsonValue, name: str = "node_id") -> str:
    """Return a non-empty string node identifier from bridge JSON input."""
    if isinstance(value, bool):
        raise ValueError("{} must be a non-empty string or integer.".format(name))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    raise ValueError("{} must be a non-empty string or integer.".format(name))


def graph_identifier_ref(value: JsonValue) -> str | None:
    """Return a graph identifier from a string or graph object."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, dict):
        for key in ("graph_identifier", "identifier", "id", "graph_id"):
            item = value.get(key)
            if isinstance(item, (str, int)) and not isinstance(item, bool) and str(item):
                return str(item)
    raise ValueError("graph_identifier must be a string or graph object with identifier.")


def package_path_ref(value: JsonValue) -> str | None:
    """Return a package path from a string or package/graph object."""
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        for key in ("package_path", "file_path", "path"):
            item = value.get(key)
            if isinstance(item, str) and item:
                return item
    raise ValueError("package_path must be a string or object with package_path/file_path.")


def comparable_path(value: str) -> str:
    """Return a normalized path token for Windows/WSL slash differences."""
    return os.path.normcase(os.path.abspath(value).replace("\\", "/"))


def find_node(graph: HostGraph, node_id: JsonValue) -> HostNode:
    """Return a node by identifier from a graph."""
    normalized_node_id = node_identifier(node_id)
    try:
        node = graph.getNodeFromId(normalized_node_id)
        if node is not None:
            return node
    except Exception:
        pass
    for node in list(graph.getNodes()):
        if node.getIdentifier() == normalized_node_id:
            return node
    raise ValueError("Node '{}' not found in graph '{}'.".format(normalized_node_id, graph.getIdentifier()))
