"""Tests for plugin-side package and graph lifecycle helpers."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_LAYOUT_PATH = REPO_ROOT / "plugin" / "graph" / "graph_operations.py"
GRAPH_PACKAGE_OPERATIONS_PATH = REPO_ROOT / "plugin" / "graph" / "graph_operations.py"
GRAPH_RESOURCE_OPERATIONS_PATH = REPO_ROOT / "plugin" / "graph" / "graph_operations.py"


class FakeDefinition:
    """Fake node definition."""

    def __init__(self, definition_id: str) -> None:
        """Store a definition identifier."""
        self.definition_id = definition_id

    def getId(self) -> str:
        """Return the definition identifier."""
        return self.definition_id


class FakeGraph:
    """Fake graph resource."""

    def __init__(self, graph_id: str = "Graph") -> None:
        """Initialize fake graph state."""
        self.graph_id = graph_id
        self.deleted = False
        self.nodes: list[FakeNode] = []

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        return self.graph_id

    def setIdentifier(self, identifier: str) -> None:
        """Set the graph identifier."""
        self.graph_id = identifier

    def getClassName(self) -> str:
        """Return the graph class name."""
        return "SDSBSCompGraph"

    def getNodeDefinitions(self) -> list[FakeDefinition]:
        """Return available definitions."""
        return [FakeDefinition("sbs::compositing::uniform"), FakeDefinition("sbs::compositing::levels")]

    def getNodes(self) -> list["FakeNode"]:
        """Return graph nodes."""
        return self.nodes

    def delete(self) -> None:
        """Mark the graph as deleted."""
        self.deleted = True


class FakeNode:
    """Fake graph node with a mutable position."""

    def __init__(self) -> None:
        """Initialize without a position."""
        self.position: tuple[float, float] | None = None

    def setPosition(self, position: tuple[float, float]) -> None:
        """Record the node position."""
        self.position = position


class FakePackage:
    """Fake user package."""

    def __init__(self, file_path: str = "") -> None:
        """Initialize package data."""
        self.file_path = file_path
        self.resources = [FakeGraph("GraphA")]

    def getFilePath(self) -> str:
        """Return the package file path."""
        return self.file_path

    def getChildrenResources(self, recursive: bool) -> list[FakeGraph]:
        """Return child graph resources."""
        return [] if recursive else self.resources


class FakePackageManager:
    """Fake package manager."""

    def __init__(self) -> None:
        """Initialize package manager state."""
        self.packages = [FakePackage("existing.sbs")]
        self.saved_as: list[tuple[FakePackage, str]] = []
        self.saved: list[FakePackage] = []
        self.unloaded: list[FakePackage] = []

    def newUserPackage(self) -> FakePackage:
        """Create and register a fake package."""
        package = FakePackage()
        self.packages.append(package)
        return package

    def getUserPackages(self) -> list[FakePackage]:
        """Return user packages."""
        return self.packages

    def savePackageAs(self, package: FakePackage, file_path: str) -> None:
        """Record save-as operation."""
        package.file_path = file_path
        self.saved_as.append((package, file_path))

    def savePackage(self, package: FakePackage) -> None:
        """Record save operation."""
        self.saved.append(package)

    def unloadUserPackage(self, package: FakePackage) -> None:
        """Record unload operation."""
        self.unloaded.append(package)


class FakeUiManager:
    """Fake UI manager."""

    def __init__(self) -> None:
        """Initialize UI state."""
        self.current_graph: FakeGraph | None = None
        self.opened: list[FakeGraph] = []

    def getCurrentGraph(self) -> FakeGraph | None:
        """Return the current graph."""
        return self.current_graph

    def openResourceInEditor(self, graph: FakeGraph) -> None:
        """Record an opened graph."""
        self.opened.append(graph)


def test_create_package_saves_and_reports_index() -> None:
    """Create package helper saves paths and reports the package index."""
    module = _load_graph_lifecycle_module()
    package_manager = FakePackageManager()
    file_path = str(Path(tempfile.gettempdir()) / "dcc_mcp_test_package.sbs")

    result = module.create_package(package_manager, file_path)

    assert result["file_path"] == file_path
    assert result["package_index"] == 1
    assert result["message"] == "New package created."
    assert package_manager.saved_as[0][1] == file_path


def test_create_delete_open_and_save_graph() -> None:
    """Lifecycle helpers return stable payloads for graph operations."""
    module = _load_graph_lifecycle_module()
    package_manager = FakePackageManager()
    package = package_manager.getUserPackages()[0]
    ui_manager = FakeUiManager()

    created = module.create_graph(lambda host_package: FakeGraph(), package, "123 Bad Name")
    deleted = module.delete_graph(package, "GraphA")
    opened = module.open_graph(ui_manager, package.resources[0], "GraphA")
    saved = module.save_package(package_manager, package, None)

    assert created["sanitized_name"] == "G_123_Bad_Name"
    assert deleted == {"deleted": "GraphA"}
    assert package.resources[0].deleted is True
    assert opened == {"opened": "GraphA", "success": True}
    assert saved == {"saved_to": "existing.sbs"}
    assert package_manager.saved == [package]


def test_arrange_graph_nodes_returns_payload_and_positions() -> None:
    """Arrange helper positions nodes and returns the command payload."""
    module = _load_graph_lifecycle_module()
    graph = FakeGraph("Layout")
    graph.nodes = [FakeNode(), FakeNode(), FakeNode()]

    result = module.arrange_graph_nodes(graph, -100, 25, 10, 20)

    assert result == {
        "graph": "Layout",
        "arranged_nodes": 3,
        "warning": "arrange_nodes can destroy all connections. Prefer move_node.",
    }
    assert graph.nodes[0].position == (-100.0, 25.0)
    assert graph.nodes[1].position == (-90.0, 25.0)
    assert graph.nodes[2].position == (-100.0, 45.0)


def test_arrange_graph_nodes_reports_empty_graph() -> None:
    """Arrange helper reports a warning for empty graphs."""
    module = _load_graph_lifecycle_module()
    graph = FakeGraph("Empty")

    result = module.arrange_graph_nodes(graph, 0, 0, 10, 10)

    assert result == {"graph": "Empty", "arranged_nodes": 0, "warning": "No nodes to arrange."}


def _load_graph_lifecycle_module() -> types.ModuleType:
    """Load concrete graph lifecycle helper modules without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.graph.graph_operations", GRAPH_PACKAGE_OPERATIONS_PATH)
    resources = _load_module("plugin.graph.graph_operations", GRAPH_RESOURCE_OPERATIONS_PATH)
    layout = _load_module("plugin.graph.graph_operations", GRAPH_LAYOUT_PATH)
    module.create_graph = resources.create_graph
    module.delete_graph = resources.delete_graph
    module.open_graph = resources.open_graph
    module.arrange_graph_nodes = layout.arrange_graph_nodes
    for module_name in [
        "plugin",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_operations",
        "plugin.graph.graph_types",
        "plugin.graph.graph_operations",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_operations",
        "plugin.graph.graph_operations",
    ]:
        sys.modules.pop(module_name, None)
    return module


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
