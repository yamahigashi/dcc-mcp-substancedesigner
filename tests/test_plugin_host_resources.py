"""Tests for plugin-side host resource resolution helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_PACKAGE_RESOLVER_PATH = REPO_ROOT / "plugin" / "host" / "host_resources.py"
HOST_GRAPH_RESOLVER_PATH = REPO_ROOT / "plugin" / "host" / "host_resources.py"
HOST_NODE_RESOLVER_PATH = REPO_ROOT / "plugin" / "host" / "host_resources.py"


class FakeNode:
    """Fake host node."""

    def __init__(self, node_id: str) -> None:
        """Store node identifier."""
        self.node_id = node_id

    def getIdentifier(self) -> str:
        """Return node identifier."""
        return self.node_id


class FakeGraph:
    """Fake host graph."""

    def __init__(self, graph_id: str, class_name: str = "SDSBSCompGraph") -> None:
        """Store graph state."""
        self.graph_id = graph_id
        self.class_name = class_name
        self.nodes = [FakeNode("direct"), FakeNode("fallback")]

    def getIdentifier(self) -> str:
        """Return graph identifier."""
        return self.graph_id

    def getClassName(self) -> str:
        """Return graph class name."""
        return self.class_name

    def getNodeFromId(self, node_id: str) -> FakeNode | None:
        """Return only the direct node through direct lookup."""
        return self.nodes[0] if node_id == "direct" else None

    def getNodes(self) -> list[FakeNode]:
        """Return graph nodes."""
        return self.nodes


class FakePackage:
    """Fake host package."""

    def __init__(self, file_path: str, graphs: list[FakeGraph]) -> None:
        """Store package path and resources."""
        self.file_path = file_path
        self.graphs = graphs

    def getFilePath(self) -> str:
        """Return package path."""
        return self.file_path

    def getChildrenResources(self, recursive: bool) -> list[FakeGraph]:
        """Return child graph resources."""
        return [] if recursive else self.graphs


class FakePackageManager:
    """Fake package manager."""

    def __init__(self, packages: list[FakePackage]) -> None:
        """Store packages."""
        self.packages = packages

    def getUserPackages(self) -> list[FakePackage]:
        """Return user packages."""
        return self.packages


class FakeUiManager:
    """Fake UI manager."""

    def __init__(self, current_graph: FakeGraph | None = None) -> None:
        """Store current graph."""
        self.current_graph = current_graph

    def getCurrentGraph(self) -> FakeGraph | None:
        """Return current graph."""
        return self.current_graph


def test_resolve_package_by_path_and_index() -> None:
    """Package resolver supports path and index lookup."""
    module = _load_host_resources_module()
    packages = [FakePackage("a.sbs", []), FakePackage("b.sbs", [])]
    package_manager = FakePackageManager(packages)

    assert module.resolve_package(package_manager, 1).getFilePath() == "b.sbs"
    assert module.resolve_package(package_manager, 0, "a.sbs").getFilePath() == "a.sbs"


def test_resolve_graph_by_identifier_current_and_first_graph() -> None:
    """Graph resolver supports explicit, current, and first graph lookup."""
    module = _load_host_resources_module()
    graph_a = FakeGraph("GraphA")
    graph_b = FakeGraph("GraphB")
    package_manager = FakePackageManager([FakePackage("a.sbs", [graph_a]), FakePackage("b.sbs", [graph_b])])

    assert module.resolve_graph(package_manager, FakeUiManager(), "GraphB") is graph_b
    assert module.resolve_graph(package_manager, FakeUiManager(), "") is graph_a
    assert module.resolve_graph(package_manager, FakeUiManager(graph_a)) is graph_a
    assert module.resolve_graph(package_manager, FakeUiManager()) is graph_a
    assert module.resolve_graph(package_manager, FakeUiManager(FakeGraph(""))) is graph_a
    assert module.resolve_graph(package_manager, FakeUiManager(FakeGraph("Nested", "SDSBSFunctionGraph"))) is graph_a


def test_resolve_graph_and_package_accept_reference_objects() -> None:
    """Resource resolvers accept list_graphs-style reference objects."""
    module = _load_host_resources_module()
    graph = FakeGraph("GraphA")
    package = FakePackage("E:/materials/test.sbs", [graph])
    package_manager = FakePackageManager([package])

    assert module.resolve_graph(package_manager, FakeUiManager(), {"identifier": "GraphA"}) is graph
    assert module.resolve_package(package_manager, 0, {"package_path": "E:/materials/test.sbs"}) is package


def test_find_node_uses_direct_lookup_then_fallback_scan() -> None:
    """Node resolver uses direct lookup then graph node scanning."""
    module = _load_host_resources_module()
    graph = FakeGraph("GraphA")

    assert module.find_node(graph, "direct").getIdentifier() == "direct"
    assert module.find_node(graph, "fallback").getIdentifier() == "fallback"


def test_find_node_accepts_integer_identifiers() -> None:
    """Node resolver normalizes integer bridge identifiers before host lookup."""
    module = _load_host_resources_module()
    graph = FakeGraph("GraphA")
    graph.nodes = [FakeNode("1572341796"), FakeNode("42")]

    assert module.find_node(graph, 1572341796).getIdentifier() == "1572341796"
    assert module.find_node(graph, 42).getIdentifier() == "42"


def test_resolvers_raise_clear_errors() -> None:
    """Resource resolvers raise stable not-found errors."""
    module = _load_host_resources_module()
    graph = FakeGraph("GraphA")
    package_manager = FakePackageManager([FakePackage("a.sbs", [graph])])

    try:
        module.resolve_package(package_manager, 5)
    except ValueError as exc:
        assert "out of range" in str(exc)
    else:
        raise AssertionError("resolve_package should fail for out-of-range indexes")

    try:
        module.resolve_graph(package_manager, FakeUiManager(), "Missing")
    except ValueError as exc:
        assert "Graph 'Missing' not found" in str(exc)
    else:
        raise AssertionError("resolve_graph should fail for unknown identifiers")

    try:
        module.find_node(graph, "missing")
    except ValueError as exc:
        assert "Node 'missing' not found" in str(exc)
    else:
        raise AssertionError("find_node should fail for unknown nodes")


def _load_host_resources_module() -> types.ModuleType:
    """Load host resource helpers without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    previous_package = sys.modules.get("plugin")
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.host.host_resources",
        "plugin.host.host_resources",
        "plugin.host.host_resources",
        "plugin.host.host_types",
    ]:
        sys.modules.pop(module_name, None)
    try:
        module = _load_module("plugin.host.host_resources", HOST_PACKAGE_RESOLVER_PATH)
        graph = _load_module("plugin.host.host_resources", HOST_GRAPH_RESOLVER_PATH)
        node = _load_module("plugin.host.host_resources", HOST_NODE_RESOLVER_PATH)
        module.resolve_graph = graph.resolve_graph
        module.find_node = node.find_node
        return module
    finally:
        for module_name in [
            "plugin.host.host_resources",
            "plugin.host.host_resources",
            "plugin.host.host_resources",
            "plugin.host.host_types",
        ]:
            sys.modules.pop(module_name, None)
        if previous_package is None:
            sys.modules.pop("plugin", None)
        else:
            sys.modules["plugin"] = previous_package


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path without writing bytecode."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module
