"""Tests for plugin-side read-only graph query helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIAGNOSTICS_PATH = REPO_ROOT / "plugin" / "graph" / "graph_queries.py"
GRAPH_SCENE_INVENTORY_PATH = REPO_ROOT / "plugin" / "graph" / "graph_queries.py"


class FakeDefinition:
    """Fake node definition or property type."""

    def __init__(self, definition_id: str) -> None:
        """Store the definition identifier."""
        self.definition_id = definition_id

    def getId(self) -> str:
        """Return the definition identifier."""
        return self.definition_id


class FakePosition:
    """Fake node position."""

    def __init__(self, x_value: float, y_value: float) -> None:
        """Store coordinates."""
        self.x = x_value
        self.y = y_value


class FakeProperty:
    """Fake node property."""

    def __init__(self, property_id: str, uid: str = "") -> None:
        """Store property metadata."""
        self.property_id = property_id
        self.uid = uid

    def getId(self) -> str:
        """Return the property identifier."""
        return self.property_id

    def getUid(self) -> str:
        """Return the property UID."""
        return self.uid

    def getType(self) -> FakeDefinition:
        """Return the property type."""
        return FakeDefinition("float")


class FakeValue:
    """Fake SDValue wrapper."""

    def __init__(self, value: object) -> None:
        """Store raw value."""
        self.value = value

    def get(self) -> object:
        """Return raw value."""
        return self.value


class FakeUsage:
    """Fake SDUsage value."""

    def getName(self) -> str:
        """Return usage name."""
        return "baseColor"

    def getComponents(self) -> str:
        """Return usage components."""
        return "RGBA"

    def getColorSpace(self) -> str:
        """Return usage color space."""
        return "sRGB"


class FakeUsageArray:
    """Fake SDValueArray<SDTypeUsage> raw value."""

    def getSize(self) -> int:
        """Return array size."""
        return 1

    def getItem(self, index: int) -> FakeValue:
        """Return usage item."""
        assert index == 0
        return FakeValue(FakeUsage())


class FakeConnection:
    """Fake property connection."""

    def __init__(self, source_node: FakeNode, source_property: FakeProperty) -> None:
        """Store connection endpoints."""
        self.source_node = source_node
        self.source_property = source_property

    def __repr__(self) -> str:
        """Return diagnostic text."""
        return "connection"

    def getInputPropertyNode(self) -> FakeNode:
        """Return the source node."""
        return self.source_node

    def getInputProperty(self) -> FakeProperty:
        """Return the source property."""
        return self.source_property

    def getConnRefOutput(self) -> str:
        """Return a fake connection reference output."""
        return "ref_out"


class FakeNode:
    """Fake graph node."""

    def __init__(self, node_id: str, definition_id: str, position: FakePosition) -> None:
        """Store node metadata."""
        self.node_id = node_id
        self.definition_id = definition_id
        self.position = position
        self.input_properties = [FakeProperty("input1")]
        self.output_properties = [FakeProperty("unique_filter_output", "out_uid")]
        self.annotation_properties = [FakeProperty("identifier"), FakeProperty("label"), FakeProperty("usages")]
        self.connections: dict[str, list[FakeConnection]] = {}

    def getIdentifier(self) -> str:
        """Return the node identifier."""
        return self.node_id

    def getDefinition(self) -> FakeDefinition:
        """Return the node definition."""
        return FakeDefinition(self.definition_id)

    def getReferencedResource(self) -> None:
        """Return no referenced resource."""
        return None

    def getPackage(self) -> None:
        """Return no package."""
        return None

    def getPosition(self) -> FakePosition:
        """Return the node position."""
        return self.position

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return properties by category."""
        if category == 1:
            return self.output_properties
        if category == 2:
            return self.annotation_properties
        return self.input_properties

    def getPropertyGraph(self, prop: FakeProperty) -> None:
        """Return no nested graph."""
        return None

    def getPropertyConnections(self, prop: FakeProperty) -> list[FakeConnection]:
        """Return connections for a property."""
        return self.connections.get(prop.getId(), [])

    def getPropertyValue(self, prop: FakeProperty) -> FakeValue | None:
        """Return annotation values."""
        if prop.getId() == "identifier":
            return FakeValue("basecolor")
        if prop.getId() == "label":
            return FakeValue("Base Color")
        if prop.getId() == "usages":
            return FakeValue(FakeUsageArray())
        return None


class FakeGraph:
    """Fake graph resource."""

    def __init__(self) -> None:
        """Initialize a connected two-node graph."""
        self.source = FakeNode("source", "sbs::compositing::uniform", FakePosition(0.0, 0.0))
        self.target = FakeNode("target", "sbs::compositing::output", FakePosition(100.0, 20.0))
        self.target.connections["input1"] = [FakeConnection(self.source, self.source.output_properties[0])]
        self.nodes = [self.source, self.target]

    def getIdentifier(self) -> str:
        """Return the graph identifier."""
        return "GraphA"

    def getNodes(self) -> list[FakeNode]:
        """Return graph nodes."""
        return self.nodes

    def getUrl(self) -> str:
        """Return a fake URL."""
        return "pkg:///GraphA"


class FakeResource(FakeGraph):
    """Fake package resource."""

    def getClassName(self) -> str:
        """Return a graph-like class name."""
        return "SDSBSCompGraph"


class FakePackage:
    """Fake user package."""

    def __init__(self) -> None:
        """Initialize child resources."""
        self.resource = FakeResource()

    def getFilePath(self) -> str:
        """Return a fake package path."""
        return "material.sbs"

    def getChildrenResources(self, recursive: bool) -> list[FakeResource]:
        """Return child resources."""
        return [] if recursive else [self.resource]


class FakePackageManager:
    """Fake package manager."""

    def __init__(self) -> None:
        """Initialize fake packages."""
        self.package = FakePackage()

    def getUserPackages(self) -> list[FakePackage]:
        """Return user packages."""
        return [self.package]


class FakeUiManager:
    """Fake UI manager."""

    def __init__(self) -> None:
        """Initialize current graph."""
        self.graph = FakeGraph()

    def getCurrentGraph(self) -> FakeGraph:
        """Return the current graph."""
        return self.graph


def test_scene_info_summarizes_packages_and_current_graph() -> None:
    """Verify scene info summarizes package and current graph inventory."""
    module = _load_graph_queries_module()

    result = module.scene_info(FakePackageManager(), FakeUiManager(), "16.0.0", "3.3.0")

    assert result["package_count"] == 1
    assert result["current_graph"] == "GraphA"
    assert result["current_graph_node_count"] == 2
    assert result["packages"][0]["graphs"][0]["node_count"] == 2


def test_graph_info_includes_connections() -> None:
    """Verify graph summaries include connection metadata."""
    module = _load_graph_queries_module()
    graph = FakeGraph()

    info = module.graph_info(graph, 10, True)

    assert info["nodes"][1]["connections"] == [
        {
            "input": "input1",
            "from_node": "source",
            "from_output": "unique_filter_output",
            "from_output_uid": "out_uid",
            "connRefOutput": "ref_out",
        }
    ]
    assert info["nodes"][1]["annotations"] == [
        {"id": "identifier", "uid": "", "type": "float", "value": "basecolor"},
        {"id": "label", "uid": "", "type": "float", "value": "Base Color"},
        {
            "id": "usages",
            "uid": "",
            "type": "float",
            "value": [{"name": "baseColor", "components": "RGBA", "color_space": "sRGB"}],
        },
    ]


def test_diagnostic_collects_runtime_inventory() -> None:
    """Verify diagnostics collect package, graph, runtime, and cache data."""
    module = _load_graph_queries_module()

    preload = [{"package_name": "spline_tools.sbs", "loaded": True}]
    result = module.diagnostic(
        FakePackageManager(), FakeUiManager(), "16.0.0", None, "PySide6", "path", True, 4, preload
    )

    assert result["sd_running"] is True
    assert result["sd_version"] == "16.0.0"
    assert result["user_packages"] == 1
    assert result["library_cache_entries"] == 4
    assert result["standard_library_preload"] == preload
    assert result["current_graph_nodes"] == 2


def _load_graph_queries_module() -> types.ModuleType:
    """Load concrete graph query helper modules as package modules."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.graph.graph_queries", GRAPH_SCENE_INVENTORY_PATH)
    diagnostics = _load_module("plugin.graph.graph_queries", GRAPH_DIAGNOSTICS_PATH)
    module.graph_info = diagnostics.graph_info
    module.diagnostic = diagnostics.diagnostic
    _remove_fake_modules()
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path under an explicit module name."""
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


def _install_fake_sd_modules() -> None:
    sd_module = types.ModuleType("sd")
    api_module = types.ModuleType("sd.api")
    sys.modules["sd"] = sd_module
    sys.modules["sd.api"] = api_module

    property_module = types.ModuleType("sd.api.sdproperty")

    class FakeCategory:
        """Fake SD property categories."""

        Input = 0
        Output = 1
        Annotation = 2

    property_module.SDPropertyCategory = FakeCategory
    sys.modules["sd.api.sdproperty"] = property_module


def _remove_fake_modules() -> None:
    """Remove fake modules installed for graph query helper loading."""
    for module_name in [
        "plugin",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_types",
        "plugin.graph.graph_queries",
        "plugin.graph.graph_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_types",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "sd",
        "sd.api",
        "sd.api.sdproperty",
    ]:
        sys.modules.pop(module_name, None)
