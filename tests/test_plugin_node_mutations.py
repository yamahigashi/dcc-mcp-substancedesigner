"""Tests for plugin-side node mutation helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import TypeAlias

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_CREATION_PATH = REPO_ROOT / "plugin" / "node" / "node_operations.py"
NODE_EDITING_PATH = REPO_ROOT / "plugin" / "node" / "node_operations.py"

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class FakeValue:
    """Fake SDValue handle."""

    def __init__(self, value: object | None = None) -> None:
        """Store wrapped value."""
        self.value = value

    @staticmethod
    def sNew(value: object) -> FakeValue:
        """Return a fake wrapped string."""
        return FakeValue(value)

    def getType(self) -> FakeType:
        """Return a fake value type."""
        return FakeType("unknown")

    def __eq__(self, other: object) -> bool:
        """Compare wrapped values for existing assertions."""
        return self.value == other


class FakeValueArray:
    """Fake SDValueArray handle."""

    def __init__(self, value_type: FakeType, size: int) -> None:
        """Store array type and items."""
        self.value_type = value_type
        self.items: list[object | None] = [None] * size

    @staticmethod
    def sNew(value_type: FakeType, size: int) -> FakeValueArray:
        """Create a fake array."""
        return FakeValueArray(value_type, size)

    def setItem(self, index: int, value: object) -> None:
        """Set a fake array item."""
        if self.value_type.getId() == "SDTypeUsage" and not isinstance(value, FakeValueUsage):
            raise TypeError("SDTypeUsage arrays only accept SDValueUsage items")
        self.items[index] = value


class FakeValueUsage(FakeValue):
    """Fake SDValueUsage handle."""

    @staticmethod
    def sNew(value: object) -> FakeValueUsage:
        """Create a fake usage value."""
        if not isinstance(value, FakeUsage):
            raise TypeError("SDValueUsage.sNew requires SDUsage")
        return FakeValueUsage(value)

    def getType(self) -> FakeType:
        """Return usage type."""
        return FakeType("SDTypeUsage")


class FakeUsage:
    """Fake SDUsage handle."""

    def __init__(self, name: str, components: str, color_space: str) -> None:
        """Store usage metadata."""
        self.name = name
        self.components = components
        self.color_space = color_space

    @staticmethod
    def sNew(name: str, components: str, color_space: str) -> FakeUsage:
        """Create a fake usage."""
        return FakeUsage(name, components, color_space)


class FakeType:
    """Fake SD type."""

    def __init__(self, type_id: str) -> None:
        """Store type id."""
        self.type_id = type_id

    def getId(self) -> str:
        """Return type id."""
        return self.type_id


class FakeDefinition:
    """Fake node definition."""

    def __init__(self, definition_id: str) -> None:
        """Store definition id."""
        self.definition_id = definition_id

    def getId(self) -> str:
        """Return definition id."""
        return self.definition_id


class FakePosition:
    """Fake node position."""

    def __init__(self, x_value: float, y_value: float) -> None:
        """Store coordinates."""
        self.x = x_value
        self.y = y_value


class FakeNode:
    """Fake mutable node."""

    def __init__(self, node_id: str, definition_id: str) -> None:
        """Initialize node state."""
        self.node_id = node_id
        self.definition_id = definition_id
        self.position = FakePosition(0.0, 0.0)
        self.annotations: dict[str, object] = {}

    def getIdentifier(self) -> str:
        """Return node id."""
        return self.node_id

    def getDefinition(self) -> FakeDefinition:
        """Return node definition."""
        return FakeDefinition(self.definition_id)

    def getReferencedResource(self) -> None:
        """Return no referenced resource."""
        return None

    def getPackage(self) -> None:
        """Return no package."""
        return None

    def getPosition(self) -> FakePosition:
        """Return node position."""
        return self.position

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return no properties."""
        return []

    def getPropertyGraph(self, prop: FakeProperty) -> None:
        """Return no nested graph."""
        return None

    def setPosition(self, position: tuple[float, float]) -> None:
        """Set node position."""
        self.position = FakePosition(position[0], position[1])

    def setAnnotationPropertyValueFromId(self, parameter_id: str, value: object) -> None:
        """Record an annotation value."""
        self.annotations[parameter_id] = value


class FakeProperty:
    """Fake node property."""


class FakeResource:
    """Fake package resource."""


class FakePackage:
    """Fake package with resource lookup."""

    def __init__(self) -> None:
        """Initialize resource."""
        self.resource = FakeResource()

    def findResourceFromUrl(self, url: str) -> FakeResource | None:
        """Find a fake resource."""
        return self.resource if url == "pkg://resource" else None


class FakePackageManager:
    """Fake package manager."""

    def __init__(self) -> None:
        """Initialize package."""
        self.package = FakePackage()

    def getPackages(self) -> list[FakePackage]:
        """Return packages."""
        return [self.package]


class FakeGraph:
    """Fake mutable graph."""

    def __init__(self) -> None:
        """Initialize graph state."""
        self.nodes: list[FakeNode] = []
        self.deleted: list[FakeNode] = []

    def getNodeDefinitions(self) -> list[FakeDefinition]:
        """Return known definitions."""
        return [FakeDefinition("sbs::compositing::uniform"), FakeDefinition("sbs::compositing::output")]

    def newNode(self, definition_id: str) -> FakeNode:
        """Create a regular node."""
        node = FakeNode("{}_{}".format(definition_id.split("::")[-1], len(self.nodes)), definition_id)
        self.nodes.append(node)
        return node

    def newInstanceNode(self, resource: FakeResource) -> FakeNode:
        """Create an instance node."""
        node = FakeNode("instance_{}".format(len(self.nodes)), "pkg://resource")
        self.nodes.append(node)
        return node

    def deleteNode(self, node: FakeNode) -> None:
        """Record node deletion."""
        self.deleted.append(node)


def test_create_node_and_instance_node() -> None:
    """Verify regular and instance node creation payloads."""
    module = _load_node_operationss_module()
    graph = FakeGraph()

    regular = module.create_node(graph, "sbs::compositing::uniform", [10, 20])
    instance = module.create_instance_node(graph, FakePackageManager(), "pkg://resource", [30, 40])

    assert regular["node_id"] == "uniform_0"
    assert regular["definition"] == "sbs::compositing::uniform"
    assert regular["position"] == [10, 20]
    assert instance["node_id"] == "instance_1"
    assert instance["position"] == [30, 40]
    assert graph.nodes[0].position.x == 10.0
    assert graph.nodes[1].position.y == 40.0


def test_created_nodes_suggest_preview_next_tool() -> None:
    """Created nodes should push callers to inspect the rendered output."""
    module = _load_node_operationss_module()
    graph = FakeGraph()

    regular = module.create_node(graph, "sbs::compositing::uniform", None)
    instance = module.create_instance_node(graph, FakePackageManager(), "pkg://resource", None)
    output = module.create_output_node(graph, "baseColor", None)

    assert {
        "tool": "substance_designer__get_preview",
        "public_name": "get_preview",
        "params": {"node_id": "uniform_0"},
        "reason": "Preview this node output before treating creation as complete.",
    } in regular["next_tools"]
    assert instance["next_tools"][0]["params"] == {"node_id": "instance_1"}
    assert output["next_tools"][0]["params"] == {"node_id": "output_2"}


def test_create_instance_node_reports_unloaded_package_diagnostics() -> None:
    """Verify missing resource errors distinguish unloaded packages from bad URLs."""
    module = _load_node_operationss_module()

    try:
        module.create_instance_node(
            FakeGraph(),
            FakePackageManager(),
            "pkg:///spline_bridge_2_splines?dependency=1545739604",
            None,
            {"package": {"file_name": "spline_tools.sbs", "kind": "builtin_standard_library"}},
        )
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("missing resource was accepted")

    assert "dependency=1545739604" in message
    assert "spline_tools.sbs" in message
    assert "loaded_packages" in message
    assert "node-definition package metadata" in message


def test_create_output_delete_move_and_duplicate_node() -> None:
    """Verify output creation, movement, duplication, and deletion payloads."""
    module = _load_node_operationss_module()
    graph = FakeGraph()
    source = graph.newNode("sbs::compositing::uniform")
    source.setPosition((5.0, 7.0))

    output = module.create_output_node(graph, "baseColor", [100, 200])
    moved = module.move_node(source, "uniform_0", [20, 30])
    duplicated = module.duplicate_node(graph, source, "uniform_0", [3, 4])
    deleted = module.delete_node(graph, source, "uniform_0")

    assert output["annotations_set"] == {"label": True, "identifier": True, "usages": True}
    usage_array = graph.nodes[1].annotations["usages"]
    usage_value = usage_array.items[0].value
    assert usage_value.name == "baseColor"
    assert usage_value.components == "RGBA"
    assert usage_value.color_space == "sRGB"
    assert moved == {"node_id": "uniform_0", "position": [20, 30]}
    assert duplicated["position"] == [23.0, 34.0]
    assert deleted == {"deleted": "uniform_0"}
    assert graph.deleted == [source]


def test_node_mutations_accept_position_objects() -> None:
    """Node mutation helpers accept common position object shapes."""
    module = _load_node_operationss_module()
    graph = FakeGraph()
    source = graph.newNode("sbs::compositing::uniform")

    created = module.create_node(graph, "sbs::compositing::uniform", {"x": 10, "y": 20})
    moved = module.move_node(source, "uniform_0", {"left": 30, "top": 40})
    duplicated = module.duplicate_node(graph, source, "uniform_0", {"x": 5, "y": 6})

    assert created["position"] == [10.0, 20.0]
    assert moved["position"] == [30.0, 40.0]
    assert duplicated["position"] == [35.0, 46.0]


def test_create_node_rejects_unknown_definition() -> None:
    """Verify regular node creation rejects unknown definitions."""
    module = _load_node_operationss_module()

    try:
        module.create_node(FakeGraph(), "sbs::compositing::missing", None)
    except ValueError as exc:
        assert "Unknown definition" in str(exc)
    else:
        raise AssertionError("unknown definition was accepted")


def _load_node_operationss_module() -> types.ModuleType:
    """Load concrete node mutation helper modules as package modules."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.node.node_operations", NODE_CREATION_PATH)
    editing = _load_module("plugin.node.node_operations", NODE_EDITING_PATH)
    module.delete_node = editing.delete_node
    module.duplicate_node = editing.duplicate_node
    module.move_node = editing.move_node
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

    base_types = types.ModuleType("sd.api.sdbasetypes")
    for name in ("ColorRGBA", "float2", "float3", "float4", "int2", "int3", "int4"):
        setattr(base_types, name, lambda *values: values)
    sys.modules["sd.api.sdbasetypes"] = base_types

    property_module = types.ModuleType("sd.api.sdproperty")

    class FakeCategory:
        """Fake SD property categories."""

        Input = 0
        Annotation = 1

    property_module.SDPropertyCategory = FakeCategory
    sys.modules["sd.api.sdproperty"] = property_module

    value_module = types.ModuleType("sd.api.sdvaluestring")
    value_module.SDValueString = FakeValue
    sys.modules["sd.api.sdvaluestring"] = value_module
    for module_name, class_name in {
        "sd.api.sdvaluebool": "SDValueBool",
        "sd.api.sdvaluecolorrgba": "SDValueColorRGBA",
        "sd.api.sdvaluefloat": "SDValueFloat",
        "sd.api.sdvaluefloat2": "SDValueFloat2",
        "sd.api.sdvaluefloat3": "SDValueFloat3",
        "sd.api.sdvaluefloat4": "SDValueFloat4",
        "sd.api.sdvalueenum": "SDValueEnum",
        "sd.api.sdvalueint": "SDValueInt",
        "sd.api.sdvalueint2": "SDValueInt2",
        "sd.api.sdvalueint3": "SDValueInt3",
        "sd.api.sdvalueint4": "SDValueInt4",
    }.items():
        item = types.ModuleType(module_name)
        setattr(item, class_name, FakeValue)
        sys.modules[module_name] = item
    array_module = types.ModuleType("sd.api.sdvaluearray")
    array_module.SDValueArray = FakeValueArray
    sys.modules["sd.api.sdvaluearray"] = array_module
    usage_module = types.ModuleType("sd.api.sdusage")
    usage_module.SDUsage = FakeUsage
    sys.modules["sd.api.sdusage"] = usage_module
    value_usage_module = types.ModuleType("sd.api.sdvalueusage")
    value_usage_module.SDValueUsage = FakeValueUsage
    sys.modules["sd.api.sdvalueusage"] = value_usage_module


def _remove_fake_modules() -> None:
    """Remove fake modules installed for node mutation helper loading."""
    for module_name in [
        "plugin",
        "plugin.library.library_nodes",
        "plugin.library.library_types",
        "plugin.node.node_operations",
        "plugin.node.node_queries",
        "plugin.node.node_operations",
        "plugin.node.node_operations",
        "plugin.node.node_queries",
        "plugin.node.node_types",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_operations",
        "plugin.node.node_types",
        "sd",
        "sd.api",
        "sd.api.sdbasetypes",
        "sd.api.sdproperty",
        "sd.api.sdvaluestring",
        "sd.api.sdvaluebool",
        "sd.api.sdvaluecolorrgba",
        "sd.api.sdvaluefloat",
        "sd.api.sdvaluefloat2",
        "sd.api.sdvaluefloat3",
        "sd.api.sdvaluefloat4",
        "sd.api.sdvalueenum",
        "sd.api.sdvalueint",
        "sd.api.sdvalueint2",
        "sd.api.sdvalueint3",
        "sd.api.sdvalueint4",
        "sd.api.sdvaluearray",
        "sd.api.sdusage",
        "sd.api.sdvalueusage",
    ]:
        sys.modules.pop(module_name, None)
