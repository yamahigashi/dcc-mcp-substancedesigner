"""Tests for plugin-side preview hash helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PREVIEW_HASH_PATH = REPO_ROOT / "plugin" / "preview" / "preview_render.py"


class FakeProperty:
    """Fake node property."""

    def __init__(self, property_id: str) -> None:
        """Store a fake property identifier."""
        self.property_id = property_id

    def getId(self) -> str:
        """Return the fake property identifier."""
        return self.property_id


class FakeConnection:
    """Fake node connection."""

    def __init__(self, source_node: FakeNode, source_property: FakeProperty) -> None:
        """Store fake source endpoint data."""
        self.source_node = source_node
        self.source_property = source_property

    def getInputPropertyNode(self) -> FakeNode:
        """Return the source node."""
        return self.source_node

    def getInputProperty(self) -> FakeProperty:
        """Return the source property."""
        return self.source_property


class FakeValue:
    """Fake property value."""

    def __init__(self, value: str) -> None:
        """Store a fake string value."""
        self.value = value

    def __repr__(self) -> str:
        """Return the fake value representation."""
        return self.value


class FakeNode:
    """Fake preview node."""

    def __init__(
        self,
        node_id: str,
        definition: str,
        values: dict[str, FakeValue],
        property_graphs: dict[str, "FakeNestedGraph"] | None = None,
        referenced_graph: "FakeNestedGraph | None" = None,
    ) -> None:
        """Store fake node metadata and values."""
        self.node_id = node_id
        self.definition = definition
        self.values = values
        self.property_graphs = property_graphs or {}
        self.referenced_graph = referenced_graph
        self.connections: dict[str, list[FakeConnection]] = {}

    def getIdentifier(self) -> str:
        """Return the fake node identifier."""
        return self.node_id

    def getProperties(self, _category: int) -> list[FakeProperty]:
        """Return fake input properties."""
        return [FakeProperty(property_id) for property_id in self.values]

    def getPropertyConnections(self, prop: FakeProperty) -> list[FakeConnection]:
        """Return fake connections for a property."""
        return self.connections.get(prop.getId(), [])

    def getPropertyValue(self, prop: FakeProperty) -> FakeValue | None:
        """Return a fake value for a property."""
        return self.values.get(prop.getId())

    def getPropertyGraph(self, prop: FakeProperty) -> "FakeNestedGraph | None":
        """Return a fake nested property graph."""
        return self.property_graphs.get(prop.getId())

    def getReferencedResource(self) -> "FakeNestedGraph | None":
        """Return a fake node-referenced resource graph."""
        return self.referenced_graph


class FakeNestedGraph:
    """Fake property-backed nested graph."""

    def __init__(self, nodes: list[FakeNode], outputs: list[FakeNode] | None = None) -> None:
        """Store fake nested graph nodes and outputs."""
        self.nodes = nodes
        self.outputs = outputs or []

    def getNodes(self) -> list[FakeNode]:
        """Return nested graph nodes."""
        return self.nodes

    def getOutputNodes(self) -> list[FakeNode]:
        """Return nested graph output nodes."""
        return self.outputs


class FakeGraph:
    """Fake preview graph."""

    def getIdentifier(self) -> str:
        """Return the fake graph identifier."""
        return "graph_a"


def test_make_preview_cache_key_is_deterministic() -> None:
    """Preview cache key generation is stable across dictionary order."""
    module = _load_preview_render_module()

    first = module.make_preview_cache_key({"b": 2, "a": 1})
    second = module.make_preview_cache_key({"a": 1, "b": 2})

    assert first == second


def test_hash_node_preview_changes_when_upstream_values_change() -> None:
    """Preview hashes include upstream node value changes."""
    module = _load_preview_render_module()
    node_a = FakeNode("node_a", "uniform", {"value": FakeValue("one")})
    node_b = FakeNode("node_b", "blend", {"input1": FakeValue("ignored")})
    node_b.connections["input1"] = [FakeConnection(node_a, FakeProperty("value"))]

    first = module.hash_node_preview(FakeGraph(), node_b, "out", _definition, _serialize, frozenset())
    node_a.values["value"] = FakeValue("two")
    second = module.hash_node_preview(FakeGraph(), node_b, "out", _definition, _serialize, frozenset())

    assert first != second


def test_hash_node_preview_changes_when_nested_graph_changes() -> None:
    """Preview hashes include property-backed nested Function Graph state."""
    module = _load_preview_render_module()
    read_thickness = FakeNode(
        "read_thickness",
        "sbs::function::get_float1",
        {"__constant__": FakeValue("#v_line_thickness")},
    )
    nested_graph = FakeNestedGraph([read_thickness], [read_thickness])
    owner = FakeNode(
        "spline_render",
        "pkg:///spline_render",
        {"thickness_image": FakeValue("ignored")},
        {"thickness_image": nested_graph},
    )

    first = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())
    read_thickness.values["__constant__"] = FakeValue("#v_line_width")
    second = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())

    assert first != second


def test_hash_node_preview_changes_when_referenced_fx_map_graph_changes() -> None:
    """Preview hashes include node-referenced FX-Map graph state."""
    module = _load_preview_render_module()
    quadrant = FakeNode("quadrant", "sbs::fxmap::paramset", {"patterntype": FakeValue("0")})
    fx_graph = FakeNestedGraph([quadrant], [quadrant])
    owner = FakeNode("fxmap", "sbs::compositing::fxmaps", {"background": FakeValue("black")}, referenced_graph=fx_graph)

    first = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())
    quadrant.values["patterntype"] = FakeValue("6")
    second = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())

    assert first != second


def test_hash_node_preview_changes_when_system_parameter_changes() -> None:
    """Preview hashes include render-affecting system parameters such as FX-Map random seeds."""
    module = _load_preview_render_module()
    owner = FakeNode("fxmap", "sbs::compositing::fxmaps", {"$randomseed": FakeValue("1")})

    system_params = frozenset({"$randomseed"})
    first = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, system_params)
    owner.values["$randomseed"] = FakeValue("2")
    second = module.hash_node_preview(
        FakeGraph(), owner, "unique_filter_output", _definition, _serialize, system_params
    )

    assert first != second


def test_hash_node_preview_changes_when_fx_map_node_property_graph_changes() -> None:
    """Preview hashes include two-level nested FX-Map property function graph state."""
    module = _load_preview_render_module()
    offset_const = FakeNode("offset_const", "sbs::function::const_float2", {"__constant__": FakeValue("[0,0]")})
    offset_graph = FakeNestedGraph([offset_const], [offset_const])
    quadrant = FakeNode(
        "quadrant",
        "sbs::fxmap::paramset",
        {"branchoffset": FakeValue("ignored")},
        {"branchoffset": offset_graph},
    )
    fx_graph = FakeNestedGraph([quadrant], [quadrant])
    owner = FakeNode("fxmap", "sbs::compositing::fxmaps", {"background": FakeValue("black")}, referenced_graph=fx_graph)

    first = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())
    offset_const.values["__constant__"] = FakeValue("[0.25,0.5]")
    second = module.hash_node_preview(FakeGraph(), owner, "unique_filter_output", _definition, _serialize, frozenset())

    assert first != second


def _definition(node: FakeNode) -> str:
    """Return a fake node definition."""
    return node.definition


def _serialize(value: FakeValue) -> str:
    """Serialize a fake value."""
    return repr(value)


def _load_preview_render_module() -> types.ModuleType:
    """Load preview hash modules as a package to exercise relative imports."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.preview.preview_render", PREVIEW_HASH_PATH)
    for module_name in [
        "plugin",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_render",
        "plugin.preview.preview_types",
    ]:
        sys.modules.pop(module_name, None)
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from disk without writing bytecode."""
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
