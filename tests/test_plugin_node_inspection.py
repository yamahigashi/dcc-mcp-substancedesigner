"""Tests for plugin-side node inspection helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_DETAIL_PATH = REPO_ROOT / "plugin" / "node" / "node_queries.py"
NODE_DEFINITION_IDENTITY_PATH = REPO_ROOT / "plugin" / "node" / "node_queries.py"
NODE_POSITION_READ_PATH = REPO_ROOT / "plugin" / "node" / "node_queries.py"
NODE_PROPERTY_METADATA_PATH = REPO_ROOT / "plugin" / "node" / "node_queries.py"


class FakeDefinition:
    """Fake node definition."""

    def __init__(self, definition_id: str = "pkg://materials/package.sbs/GraphA") -> None:
        """Store a definition id."""
        self.definition_id = definition_id

    def getId(self) -> str:
        """Return a package-backed definition identifier."""
        return self.definition_id


class FakeResource:
    """Fake referenced resource."""

    def getIdentifier(self) -> str:
        """Return the resource identifier."""
        return "GraphA"

    def getUrl(self) -> str:
        """Return the resource URL."""
        return "pkg://materials/package.sbs/GraphA"


class FakePackage:
    """Fake package value."""

    def getFilePath(self) -> str:
        """Return a fake package path."""
        return "/tmp/package.sbs"


class FakePosition:
    """Fake node position."""

    x = 10.0
    y = 20.0


class FakeType:
    """Fake property type."""

    def getId(self) -> str:
        """Return a fake type identifier."""
        return "float"


class FakeProperty:
    """Fake property value."""

    def __init__(self, property_id: str = "roughness", uid: int = 42) -> None:
        """Store property metadata."""
        self.property_id = property_id
        self.uid = uid

    def getId(self) -> str:
        """Return a fake property identifier."""
        return self.property_id

    def getUid(self) -> int:
        """Return a fake property UID."""
        return self.uid

    def getLabel(self) -> str:
        """Return a fake label."""
        return "Roughness"

    def getType(self) -> FakeType:
        """Return a fake property type."""
        return FakeType()


class FakeNestedGraph:
    """Fake nested graph."""

    def __init__(self, class_name: str = "SDSBSFunctionGraph") -> None:
        """Initialize fake graph class name."""
        self.class_name = class_name

    def getClassName(self) -> str:
        """Return a fake graph class name."""
        return self.class_name


class FakeNode:
    """Fake Substance Designer node."""

    def __init__(
        self,
        definition_id: str = "pkg://materials/package.sbs/GraphA",
        expose_property_graph: bool = True,
        referenced_resource: object | None = None,
    ) -> None:
        """Initialize fake connection state."""
        self.connections: list[FakeConnection] = []
        self.definition_id = definition_id
        self.expose_property_graph = expose_property_graph
        self.referenced_resource = referenced_resource

    def getIdentifier(self) -> str:
        """Return a fake node identifier."""
        return "node_a"

    def getDefinition(self) -> FakeDefinition:
        """Return a fake definition."""
        return FakeDefinition(self.definition_id)

    def getReferencedResource(self) -> object:
        """Return a fake referenced resource."""
        if self.referenced_resource is not None:
            return self.referenced_resource
        return FakeResource()

    def getPackage(self) -> FakePackage:
        """Return a fake package."""
        return FakePackage()

    def getPosition(self) -> FakePosition:
        """Return a fake position."""
        return FakePosition()

    def getProperties(self, _category: int) -> list[FakeProperty]:
        """Return fake properties."""
        return [FakeProperty()]

    def getPropertyGraph(self, _prop: FakeProperty) -> FakeNestedGraph:
        """Return a fake nested graph."""
        if not self.expose_property_graph:
            return None
        return FakeNestedGraph()

    def getPropertyValue(self, _prop: FakeProperty) -> FakeValue:
        """Return a fake property value."""
        return FakeValue("value")

    def getPropertyConnections(self, _prop: FakeProperty) -> list[FakeConnection]:
        """Return fake property connections."""
        return self.connections


class FakeInspectionGraph:
    """Fake graph for temporary node inspection."""

    def __init__(self) -> None:
        """Initialize created/deleted state."""
        self.created = FakeNode()
        self.deleted: list[FakeNode] = []

    def newNode(self, definition_id: str) -> FakeNode:
        """Create a fake node."""
        assert definition_id == "sbs::compositing::levels"
        return self.created

    def getNodeDefinitions(self) -> list[FakeDefinition]:
        """Return allowed node definitions."""
        return [FakeDefinition("sbs::compositing::levels")]

    def newInstanceNode(self, _resource: FakeResource) -> FakeNode:
        """Create a fake instance node."""
        return self.created

    def deleteNode(self, node: FakeNode) -> None:
        """Record deleted temporary nodes."""
        self.deleted.append(node)


class FakeInspectionPackage:
    """Fake package that resolves resources."""

    def findResourceFromUrl(self, url: str) -> FakeResource | None:
        """Return a resource for the expected URL."""
        return FakeResource() if url == "pkg:///GraphA" else None


class FakeInspectionPackageManager:
    """Fake package manager for runtime inspection."""

    def getPackages(self) -> list[FakeInspectionPackage]:
        """Return fake packages."""
        return [FakeInspectionPackage()]


class FakeValue:
    """Fake SDValue-like value."""

    def __init__(self, value: str) -> None:
        """Store a value."""
        self.value = value

    def get(self) -> str:
        """Return the wrapped value."""
        return self.value


class FakeConnection:
    """Fake property connection."""

    def getInputPropertyNode(self) -> FakeSourceNode:
        """Return a fake source node."""
        return FakeSourceNode()

    def getInputProperty(self) -> FakeProperty:
        """Return a fake source property."""
        return FakeProperty("out", 99)

    def getConnRefOutput(self) -> str:
        """Return a fake ref output."""
        return "ref_out"

    def __repr__(self) -> str:
        """Return diagnostic text."""
        return "connection"


class FakeSourceNode(FakeNode):
    """Fake source node."""

    def getIdentifier(self) -> str:
        """Return a source node identifier."""
        return "source"


def test_node_queries_serializes_instance_metadata() -> None:
    """Verify instance node metadata and position helpers."""
    module = _load_node_queries_module()
    node = FakeNode()

    assert module.get_node_def_id(node) == "pkg://materials/package.sbs/GraphA"
    assert module.is_instance_node(node) is True
    assert module.get_node_pos(node) == [10.0, 20.0]
    assert module.get_instance_ref(node) == {
        "definition": "pkg://materials/package.sbs/GraphA",
        "graph": "GraphA",
        "resource_url": "pkg://materials/package.sbs/GraphA",
        "package": "/tmp/package.sbs",
    }


def test_node_queries_serializes_properties_and_nested_graph_refs() -> None:
    """Verify property metadata and nested graph reference serialization."""
    module = _load_node_queries_module()
    node = FakeNode()

    assert module.get_property_info(FakeProperty()) == {
        "id": "roughness",
        "uid": 42,
        "label": "Roughness",
        "type": "float",
    }
    assert module.get_nested_graph_refs(node) == [
        {"property": "roughness", "graph_type": "SDSBSFunctionGraph", "exists": True},
        {"property": "roughness", "graph_type": "SDSBSFunctionGraph", "exists": True},
    ]


def test_node_queries_serializes_fx_map_referenced_graph_ref() -> None:
    """FX-Map nodes expose their referenced SDSBSFxMapGraph through node introspection."""
    module = _load_node_queries_module()
    node = FakeNode(
        definition_id="sbs::compositing::fxmaps",
        expose_property_graph=False,
        referenced_resource=FakeNestedGraph("SDSBSFxMapGraph"),
    )

    assert module.get_nested_graph_refs(node) == [
        {"kind": "fx_map_graph", "graph_type": "SDSBSFxMapGraph", "exists": True}
    ]


def test_node_queries_serializes_full_node_detail() -> None:
    """Verify full node detail payload serialization."""
    module = _load_node_queries_module()
    node = FakeNode()
    node.connections = [FakeConnection()]

    detail = module.get_node_detail("node_a", node, frozenset(), _serialize_fake_value)

    assert detail["node_id"] == "node_a"
    assert detail["inputs"][0]["value"] == "value"
    assert detail["inputs"][0]["connected_from"] == ["source.out"]
    assert detail["inputs"][0]["connections"] == [
        {"node": "source", "output": "out", "output_uid": 99, "connRefOutput": "ref_out"}
    ]
    assert detail["outputs"][0]["id"] == "roughness"


def test_node_queries_inspect_node_deletes_temporary_atomic_node() -> None:
    """Runtime inspection deletes the temporary node after serializing detail."""
    module = _load_node_queries_module()
    graph = FakeInspectionGraph()

    detail = module.inspect_node(
        graph=graph,
        package_manager=FakeInspectionPackageManager(),
        definition_id="sbs::compositing::levels",
        resource_url=None,
        system_params=frozenset(),
        serialize_value=_serialize_fake_value,
    )

    assert detail["target"] == {"kind": "atomic", "definition_id": "sbs::compositing::levels"}
    assert detail["temporary_node_id"] == "node_a"
    assert detail["inputs"][0]["id"] == "roughness"
    assert graph.deleted == [graph.created]


def test_node_queries_inspect_node_reads_existing_node_without_deleting() -> None:
    """Existing-node inspection does not delete the graph node."""
    module = _load_node_queries_module()
    graph = FakeInspectionGraph()

    detail = module.inspect_node(
        graph=graph,
        package_manager=FakeInspectionPackageManager(),
        existing_node=graph.created,
        node_id="node_a",
        definition_id=None,
        resource_url=None,
        system_params=frozenset(),
        serialize_value=_serialize_fake_value,
    )

    assert detail["target"] == {"kind": "existing_node", "node_id": "node_a"}
    assert detail["node_id"] == "node_a"
    assert detail["temporary_node_id"] is None
    assert graph.deleted == []


def test_node_queries_inspect_node_reports_property_context_notice() -> None:
    """Property-specific context reports that packaged context data is unavailable."""
    module = _load_node_queries_module()
    graph = FakeInspectionGraph()

    detail = module.inspect_node(
        graph=graph,
        package_manager=FakeInspectionPackageManager(),
        existing_node=graph.created,
        node_id="node_a",
        property_id="roughness",
        system_params=frozenset(),
        serialize_value=_serialize_fake_value,
    )

    assert detail["property_context"]["property_id"] == "roughness"
    assert detail["property_context"]["available"] is False
    assert "Do not invent" in detail["property_context"]["guidance"]
    assert graph.deleted == []


def test_node_queries_inspect_node_resolves_resource_url() -> None:
    """Runtime inspection supports package resource targets."""
    module = _load_node_queries_module()
    graph = FakeInspectionGraph()

    detail = module.inspect_node(
        graph=graph,
        package_manager=FakeInspectionPackageManager(),
        existing_node=None,
        node_id=None,
        definition_id=None,
        resource_url="pkg:///GraphA",
        system_params=frozenset(),
        serialize_value=_serialize_fake_value,
    )

    assert detail["target"] == {"kind": "library", "resource_url": "pkg:///GraphA"}
    assert graph.deleted == [graph.created]


def _serialize_fake_value(value: FakeValue | None) -> str | None:
    """Serialize a fake value."""
    return value.get() if value is not None else None


def _load_node_queries_module() -> types.ModuleType:
    """Load concrete node inspection helper modules as package modules."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    previous_package = sys.modules.get("plugin")
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_types",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
        "plugin.node.node_queries",
    ]:
        sys.modules.pop(module_name, None)
    module = _load_module("plugin.node.node_queries", NODE_DETAIL_PATH)
    identity = _load_module("plugin.node.node_queries", NODE_DEFINITION_IDENTITY_PATH)
    position = _load_module("plugin.node.node_queries", NODE_POSITION_READ_PATH)
    metadata = _load_module("plugin.node.node_queries", NODE_PROPERTY_METADATA_PATH)
    module.get_instance_ref = identity.get_instance_ref
    module.get_node_def_id = identity.get_node_def_id
    module.is_instance_node = identity.is_instance_node
    module.get_node_pos = position.get_node_pos
    module.get_property_info = metadata.get_property_info
    if previous_package is None:
        sys.modules.pop("plugin", None)
    else:
        sys.modules["plugin"] = previous_package
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
