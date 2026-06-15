"""Tests for plugin-side nested graph helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import TypeAlias

REPO_ROOT = Path(__file__).resolve().parents[1]
NESTED_GRAPH_APPLY_PATH = REPO_ROOT / "plugin" / "nested_graph" / "nested_graph_operations.py"
NESTED_GRAPH_APPLICATION_PATH = REPO_ROOT / "plugin" / "nested_graph" / "nested_graph_operations.py"
NESTED_GRAPH_INSPECTION_PATH = REPO_ROOT / "plugin" / "nested_graph" / "nested_graph_queries.py"
NESTED_GRAPH_STRUCTURE_PATH = REPO_ROOT / "plugin" / "nested_graph" / "nested_graph_operations.py"
NESTED_GRAPH_SERIALIZATION_PATH = REPO_ROOT / "plugin" / "nested_graph" / "nested_graph_queries.py"
FakeJsonValue: TypeAlias = None | bool | int | float | str | list["FakeJsonValue"] | dict[str, "FakeJsonValue"]


class FakeType:
    """Fake SDType value."""

    def __init__(self, type_id: str) -> None:
        """Store a fake type identifier."""
        self.type_id = type_id

    def getId(self) -> str:
        """Return the fake type identifier."""
        return self.type_id


class FakeProperty:
    """Fake nested graph property."""

    def __init__(self, property_id: str, type_id: str = "float") -> None:
        """Store a fake property identifier."""
        self.property_id = property_id
        self.type_id = type_id

    def getId(self) -> str:
        """Return the fake property identifier."""
        return self.property_id

    def getType(self) -> FakeType:
        """Return a fake type object."""
        return FakeType(self.type_id)


class FakeConnection:
    """Fake nested graph connection."""

    def __init__(self, source_node: FakeNode, source_property: FakeProperty) -> None:
        """Store fake source endpoint values."""
        self.source_node = source_node
        self.source_property = source_property

    def getInputPropertyNode(self) -> FakeNode:
        """Return the fake source node."""
        return self.source_node

    def getInputProperty(self) -> FakeProperty:
        """Return the fake source property."""
        return self.source_property


class FakeValue:
    """Fake property value."""

    def __init__(self, value: str) -> None:
        """Store a fake value."""
        self.value = value

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        return self.value


class FakeNode:
    """Fake nested graph node."""

    def __init__(
        self,
        node_id: str,
        inputs: list[FakeProperty],
        definition_id: str = "",
        referenced_resource: "FakeResource | None" = None,
    ) -> None:
        """Store fake node state."""
        self.node_id = node_id
        self.definition_id = definition_id
        self.referenced_resource = referenced_resource
        self.inputs = inputs
        self.connections: dict[str, list[FakeConnection]] = {}
        self.values: dict[str, FakeValue] = {}
        self.position: tuple[float, float] | None = None
        self.params: dict[str, FakeJsonValue] = {}
        self.deleted_connections: list[str] = []
        self.property_graphs: dict[str, FakeNestedGraph] = {}
        self.created_graph_types: list[str] = []
        self.deleted_property_graphs: list[str] = []

    def getIdentifier(self) -> str:
        """Return the fake node identifier."""
        return self.node_id

    def getReferencedResource(self) -> "FakeResource | None":
        """Return a fake referenced resource for instance nodes."""
        return self.referenced_resource

    def getProperties(self, _category: int) -> list[FakeProperty]:
        """Return fake input properties."""
        return self.inputs

    def getPropertyFromId(self, property_id: str, _category: int) -> FakeProperty | None:
        """Return a matching fake input property."""
        for prop in self.inputs:
            if prop.getId() == property_id:
                return prop
        return None

    def getPropertyConnections(self, prop: FakeProperty) -> list[FakeConnection]:
        """Return fake connections for a property."""
        return self.connections.get(prop.getId(), [])

    def deletePropertyConnections(self, prop: FakeProperty) -> None:
        """Delete fake input connections."""
        self.deleted_connections.append(prop.getId())
        self.connections[prop.getId()] = []

    def getPropertyValue(self, prop: FakeProperty) -> FakeValue | None:
        """Return a fake property value."""
        return self.values.get(prop.getId())

    def setPosition(self, position: tuple[float, float]) -> None:
        """Record a fake node position."""
        self.position = position

    def getPropertyGraph(self, prop: FakeProperty) -> "FakeNestedGraph | None":
        """Return a fake node-owned property graph."""
        return self.property_graphs.get(prop.getId())

    def deletePropertyGraph(self, prop: FakeProperty) -> None:
        """Delete a fake node-owned property graph."""
        self.deleted_property_graphs.append(prop.getId())
        self.property_graphs.pop(prop.getId(), None)

    def newPropertyGraph(self, prop: FakeProperty, graph_type: str) -> "FakeNestedGraph | None":
        """Create a fake node-owned property graph."""
        if graph_type != "SDSBSFunctionGraph":
            return None
        graph = FakeNestedGraph([], [], graph_type)
        self.property_graphs[prop.getId()] = graph
        self.created_graph_types.append(graph_type)
        return graph


class FakeOwnerNode:
    """Fake node that owns a nested graph property."""

    def __init__(self) -> None:
        """Initialize fake owner properties."""
        self.input_props = [FakeProperty("perpixel")]
        self.annotation_props = [FakeProperty("note", "string")]
        self.property_graph: FakeNestedGraph | None = None
        self.deleted_properties: list[str] = []
        self.values: dict[str, object] = {}
        self.property_annotations: dict[tuple[str, str], object] = {}
        self.created_inputs: list[tuple[str, str, int]] = []
        self.created_graph_types: list[str] = []
        self.delete_property_graph_error: Exception | None = None
        self.referenced_resource: FakeNestedGraph | None = None

    def getIdentifier(self) -> str:
        """Return the fake owner identifier."""
        return "owner"

    def getPropertyFromId(self, property_id: str, category: int) -> FakeProperty | None:
        """Return a matching fake property."""
        props = self.input_props if category == 0 else self.annotation_props
        for prop in props:
            if prop.getId() == property_id:
                return prop
        return None

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return fake owner properties."""
        return self.input_props if category == 0 else self.annotation_props

    def getPropertyValue(self, prop: FakeProperty) -> object | None:
        """Return a fake owner property value."""
        return self.values.get(prop.getId())

    def newProperty(self, property_id: str, property_type: object, category: int) -> FakeProperty:
        """Create a fake owner property."""
        type_id = property_type.getId() if hasattr(property_type, "getId") else str(property_type)
        prop = FakeProperty(property_id, type_id)
        if category == 0:
            self.input_props.append(prop)
        else:
            self.annotation_props.append(prop)
        self.created_inputs.append((property_id, type_id, category))
        return prop

    def setPropertyValue(self, prop: FakeProperty, value: object) -> None:
        """Record a property default value."""
        self.values[prop.getId()] = value

    def setInputPropertyValueFromId(self, property_id: str, value: object) -> None:
        """Record a property default value by id."""
        self.values[property_id] = value

    def setPropertyAnnotationValueFromId(self, prop: FakeProperty, annotation_id: str, value: object) -> None:
        """Record a property annotation value."""
        self.property_annotations[(prop.getId(), annotation_id)] = value

    def getPropertyGraph(self, prop: FakeProperty) -> FakeNestedGraph | None:
        """Return the fake property graph."""
        if prop.getId() in {"perpixel", "fxmap"}:
            return self.property_graph
        return None

    def getReferencedResource(self) -> FakeNestedGraph | None:
        """Return a fake node-referenced resource."""
        return self.referenced_resource

    def deletePropertyGraph(self, prop: FakeProperty) -> None:
        """Delete the fake property graph."""
        if self.delete_property_graph_error is not None:
            raise self.delete_property_graph_error
        self.deleted_properties.append(prop.getId())
        self.property_graph = None

    def newPropertyGraph(self, prop: FakeProperty, graph_type: str) -> FakeNestedGraph | None:
        """Create a fake property graph."""
        if prop.getId() == "perpixel" and graph_type != "SDSBSFunctionGraph":
            return None
        if prop.getId() == "fxmap" and graph_type != "SDSBSFxMapGraph":
            return None
        if prop.getId() not in {"perpixel", "fxmap"}:
            return None
        self.created_graph_types.append(graph_type)
        self.property_graph = FakeNestedGraph([], [], graph_type)
        return self.property_graph


class FakeOuterGraph:
    """Fake parent graph for nested graph commands."""

    def getIdentifier(self) -> str:
        """Return the parent graph identifier."""
        return "GraphA"


class FakeOutputCollection:
    """Fake host output node collection."""

    def __init__(self, nodes: list[FakeNode]) -> None:
        """Store fake nodes."""
        self.nodes = nodes

    def getSize(self) -> int:
        """Return the fake collection size."""
        return len(self.nodes)

    def getItem(self, index: int) -> FakeNode:
        """Return a fake collection item."""
        return self.nodes[index]


class FakeDefinition:
    """Fake nested graph node definition."""

    def __init__(self, definition_id: str) -> None:
        """Store a definition identifier."""
        self.definition_id = definition_id

    def getId(self) -> str:
        """Return the fake definition identifier."""
        return self.definition_id


class FakeResource:
    """Fake package resource backing a function graph instance."""

    def __init__(self, url: str) -> None:
        """Store a fake package resource URL."""
        self.url = url

    def getClassName(self) -> str:
        """Return a function graph resource class."""
        return "SDSBSFunctionGraph"

    def getIdentifier(self) -> str:
        """Return a fake resource identifier."""
        return self.url.rsplit("/", 1)[-1].split("?", 1)[0]

    def getUrl(self) -> str:
        """Return the fake resource URL."""
        return self.url


class FakePackage:
    """Fake package that can resolve resources by URL."""

    def __init__(self, file_path: str, resources: list[FakeResource]) -> None:
        """Store fake package resources."""
        self.file_path = file_path
        self.resources = resources

    def getFilePath(self) -> str:
        """Return the fake package path."""
        return self.file_path

    def getChildrenResources(self, _recursive: bool) -> list[FakeResource]:
        """Return package resources."""
        return self.resources

    def findResourceFromUrl(self, url: str) -> FakeResource | None:
        """Find a resource by exact URL."""
        return next((resource for resource in self.resources if resource.getUrl() == url), None)


class FakePackageManager:
    """Fake package manager for nested graph instance nodes."""

    def __init__(self, packages: list[FakePackage]) -> None:
        """Store fake loaded packages."""
        self.packages = packages

    def getPackages(self) -> list[FakePackage]:
        """Return loaded fake packages."""
        return self.packages

    def loadUserPackage(self, file_path: str) -> FakePackage:
        """Record an explicit package load request."""
        package = FakePackage(file_path, [])
        self.packages.append(package)
        return package


class FakeNestedGraph:
    """Fake nested graph."""

    def __init__(
        self,
        nodes: list[FakeNode],
        output_nodes: list[FakeNode],
        graph_type: str = "SDSBSFxMapGraph",
    ) -> None:
        """Store fake graph state."""
        self.nodes = nodes
        self.output_nodes = output_nodes
        self.graph_type = graph_type
        self.definitions = [
            FakeDefinition("fake::source"),
            FakeDefinition("fake::target"),
            FakeDefinition("sbs::function::get_float1"),
            FakeDefinition("sbs::function::get_float4"),
        ]
        self.created: list[FakeNode] = []
        self.instance_resources: list[str] = []
        self.connected: list[tuple[str, str, str, str]] = []
        self.output_node: FakeNode | None = None
        self.deleted: list[str] = []

    def getNodes(self) -> list[FakeNode]:
        """Return fake graph nodes."""
        return self.nodes

    def getOutputNodes(self) -> FakeOutputCollection:
        """Return fake output nodes through a host-like collection."""
        return FakeOutputCollection(self.output_nodes)

    def getNodeDefinitions(self) -> list[FakeDefinition]:
        """Return fake node definitions."""
        return self.definitions

    def newNode(self, definition_id: str) -> FakeNode | None:
        """Create a fake node for a definition."""
        if definition_id not in {definition.getId() for definition in self.definitions}:
            return None
        inputs = [FakeProperty("branchoffset")] if definition_id == "sbs::fxmap::paramset" else []
        node = FakeNode("created_{}".format(len(self.created)), inputs, definition_id)
        self.created.append(node)
        self.nodes.append(node)
        return node

    def newInstanceNode(self, resource: FakeResource) -> FakeNode:
        """Create a fake instance node for a package resource."""
        node = FakeNode("created_{}".format(len(self.created)), [], "sbs::function::instance", resource)
        self.created.append(node)
        self.nodes.append(node)
        self.instance_resources.append(resource.getUrl())
        return node

    def setOutputNode(self, node: FakeNode, enabled: bool) -> None:
        """Record a fake output node."""
        if enabled:
            self.output_node = node

    def deleteNode(self, node: FakeNode) -> None:
        """Delete a fake node."""
        self.deleted.append(node.getIdentifier())
        self.nodes = [item for item in self.nodes if item is not node]
        self.output_nodes = [item for item in self.output_nodes if item is not node]

    def getClassName(self) -> str:
        """Return a fake graph class name."""
        return self.graph_type


def test_find_node_property_returns_input_or_annotation_property() -> None:
    """Property lookup searches input and annotation categories."""
    module = _load_nested_graphs_module()

    assert module.find_node_property(FakeOwnerNode(), "perpixel").getId() == "perpixel"


def test_serialize_nested_graph_state_collects_values_connections_and_output() -> None:
    """State serialization collects node parameters, connections, and output."""
    module = _load_nested_graphs_module()
    source = FakeNode("source", [FakeProperty("amount")])
    target = FakeNode("target", [FakeProperty("input1"), FakeProperty("gain")])
    target.connections["input1"] = [FakeConnection(source, FakeProperty("unique_filter_output"))]
    target.values["gain"] = FakeValue("0.5")
    graph = FakeNestedGraph([source, target], [target])

    state = module.serialize_nested_graph_state(
        graph,
        lambda node: "fake::{}".format(node.getIdentifier()),
        lambda _node: [1.0, 2.0],
        lambda value: repr(value),
    )

    assert state == {
        "nodes": [
            {"id": "source", "definition": "fake::source", "position": [1.0, 2.0]},
            {
                "id": "target",
                "definition": "fake::target",
                "position": [1.0, 2.0],
                "parameters": {"gain": "0.5"},
            },
        ],
        "connections": [
            {
                "from": "source",
                "from_output": "unique_filter_output",
                "to": "target",
                "to_input": "input1",
            }
        ],
        "output": {"node": "target"},
    }


def test_serialize_nested_graph_state_keeps_get_nodes_as_nested_nodes() -> None:
    """State serialization keeps Designer get nodes in the nested graph node list."""
    module = _load_nested_graphs_module()
    input_getter = FakeNode("get_1", [FakeProperty("__constant__")])
    input_getter.values["__constant__"] = FakeValue("feather_length")
    target = FakeNode("target", [FakeProperty("input1")])
    target.connections["input1"] = [FakeConnection(input_getter, FakeProperty("unique_filter_output"))]
    graph = FakeNestedGraph([input_getter, target], [target])

    state = module.serialize_nested_graph_state(
        graph,
        lambda node: "sbs::function::get_float1" if node.getIdentifier() == "get_1" else "fake::target",
        lambda node: [0.0, 0.0] if node.getIdentifier() == "get_1" else [160.0, 0.0],
        lambda value: value.value,
    )

    assert state == {
        "nodes": [
            {
                "id": "get_1",
                "definition": "sbs::function::get_float1",
                "position": [0.0, 0.0],
                "parameters": {"__constant__": "feather_length"},
            },
            {"id": "target", "definition": "fake::target", "position": [160.0, 0.0]},
        ],
        "connections": [
            {
                "from": "get_1",
                "from_output": "unique_filter_output",
                "to": "target",
                "to_input": "input1",
            }
        ],
        "output": {"node": "target"},
    }


def test_apply_nested_graph_state_to_graph_creates_nodes_connections_and_output() -> None:
    """Low-level apply helper creates nodes, connections, and output state."""
    module = _load_nested_graphs_module()
    graph = FakeNestedGraph([], [])
    state = {
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "source", "definition": "fake::source", "position": [10, 20]},
            {
                "id": "target",
                "definition": "fake::target",
                "parameters": {"gain": 0.5},
            },
        ],
        "connections": [
            {
                "from": "source",
                "from_output": "unique_filter_output",
                "to": "target",
                "to_input": "input1",
            }
        ],
        "output": {"node": "target"},
    }

    result = module.apply_nested_graph_state_to_graph(
        graph,
        state,
        "replace",
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["nodes_created"] == 2
    assert result["connections_created"] == 1
    assert result["output"] == "target"
    assert result["node_map"] == {"source": "created_0", "target": "created_1"}


def test_apply_nested_graph_state_reports_parameter_status() -> None:
    """Low-level apply helper exposes per-parameter apply status."""
    module = _load_nested_graphs_module()
    graph = FakeNestedGraph([], [])

    result = module.apply_nested_graph_state_to_graph(
        graph,
        {
            "graph_type": "SDSBSFunctionGraph",
            "nodes": [{"id": "target", "definition": "fake::target", "parameters": {"gain": 0.5}}],
        },
        "replace",
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        _set_fake_params_with_status,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["nodes"][0]["parameter_status"] == {"gain": "ok"}


def test_apply_nested_graph_patch_reports_parameter_status() -> None:
    """Patch helper exposes per-parameter apply status."""
    module = _load_nested_graphs_module()
    graph = FakeNestedGraph([FakeNode("target", "fake::target")], [])

    result = module.apply_nested_graph_patch_to_graph(
        graph,
        {"operations": [{"op": "ensure_node", "id": "target", "parameters": {"gain": 0.5}}]},
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        _set_fake_params_with_status,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["operations"] == [
        {
            "op": "ensure_node",
            "id": "target",
            "node_id": "target",
            "parameters": ["gain"],
            "parameter_status": {"gain": "ok"},
        }
    ]


def test_apply_nested_graph_patch_sets_node_property_graph() -> None:
    """Patch helper can create a function graph on a nested FX-Map node property."""
    module = _load_nested_graphs_module()
    quadrant = FakeNode("quadrant", [FakeProperty("branchoffset", "float2")], "sbs::fxmap::paramset")
    graph = FakeNestedGraph([quadrant], [quadrant])

    result = module.apply_nested_graph_patch_to_graph(
        graph,
        {
            "operations": [
                {
                    "op": "set_property_graph",
                    "node": "quadrant",
                    "property": "branchoffset",
                    "graph_type": "SDSBSFunctionGraph",
                    "nodes": [{"id": "offset", "definition": "fake::target"}],
                    "connections": [],
                    "output": "offset",
                }
            ]
        },
        {"graph_identifier": "GraphA", "node_id": "fxmaps", "property": "fxmap"},
        _set_fake_params_with_status,
        _connect_fake_nodes,
        lambda node: node.definition_id,
    )

    assert quadrant.created_graph_types == ["SDSBSFunctionGraph"]
    assert "branchoffset" in quadrant.property_graphs
    assert result["operations"] == [
        {
            "op": "set_property_graph",
            "node": "quadrant",
            "property": "branchoffset",
            "graph_type": "SDSBSFunctionGraph",
            "nodes_created": 1,
            "connections_created": 0,
            "output": "offset",
        }
    ]


def test_apply_nested_graph_state_accepts_builtin_connections_as_implicit_bindings() -> None:
    """Builtin endpoints are accepted without requiring a created source node."""
    module = _load_nested_graphs_module()
    graph = FakeNestedGraph([], [])
    state = {
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [{"id": "sample", "definition": "fake::target"}],
        "connections": [
            {
                "from_builtin": "$pos",
                "to": "sample",
                "to_input": "pos",
            }
        ],
        "output": {"node": "sample"},
    }

    result = module.apply_nested_graph_state_to_graph(
        graph,
        state,
        "replace",
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["connections_created"] == 0
    assert result["connections"] == [
        {
            "from_builtin": "$pos",
            "to": "sample",
            "to_input": "pos",
            "success": True,
            "binding": "host_implicit_builtin",
        }
    ]
    assert graph.connected == []


def test_apply_nested_graph_state_to_graph_creates_resource_instance_nodes() -> None:
    """Low-level apply helper creates package-backed function graph instance nodes."""
    module = _load_nested_graphs_module()
    resource_url = "pkg:///3d_sdf_primitives/3d_sdf_sphere?dependency=1566899378"
    graph = FakeNestedGraph([], [])
    package_manager = FakePackageManager([FakePackage("3d_functions.sbs", [FakeResource(resource_url)])])
    state = {
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {
                "id": "sphere",
                "definition": "sbs::function-library::3d_sdf_sphere",
                "host_creation": {
                    "kind": "function_graph_resource_instance",
                    "resource_url": resource_url,
                    "package_hint": {"file_name": "3d_functions.sbs"},
                },
            }
        ],
        "connections": [],
        "output": {"node": "sphere"},
    }

    result = module.apply_nested_graph_state_to_graph(
        graph,
        state,
        "replace",
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "sdf_scene"},
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: node.definition_id,
        package_manager,
    )

    assert graph.instance_resources == [resource_url]
    assert result["nodes_created"] == 1
    assert result["nodes"][0]["definition"] == "sbs::function::instance"
    assert result["nodes"][0]["host_creation"]["resource_url"] == resource_url
    assert graph.output_node is graph.created[0]


def test_apply_nested_graph_state_to_graph_normalizes_get_node_constant_references() -> None:
    """Low-level apply normalizes #foo get node references before setting params."""
    module = _load_nested_graphs_module()
    graph = FakeNestedGraph([], [])
    state = {
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {
                "id": "source",
                "definition": "sbs::function::get_float1",
                "parameters": {"__constant__": {"value": "#feather_length", "type": "string"}},
            },
        ],
        "connections": [],
        "output": {"node": "source"},
    }

    module.apply_nested_graph_state_to_graph(
        graph,
        state,
        "replace",
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert graph.created[0].params == {"__constant__": {"value": "feather_length", "type": "string"}}


def test_get_nested_graph_state_payload_reports_existing_graph() -> None:
    """Command payload helper serializes an existing property graph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    owner.input_props.append(FakeProperty("feather_length", "float"))
    owner.values["feather_length"] = FakeValue("0.25")
    nested_node = FakeNode("target", [FakeProperty("gain")])
    nested_node.values["gain"] = FakeValue("0.5")
    owner.property_graph = FakeNestedGraph([nested_node], [nested_node])

    result = module.get_nested_graph_state_payload(
        FakeOuterGraph(),
        owner,
        "owner",
        "perpixel",
        "SDSBSFunctionGraph",
        lambda node: "fake::{}".format(node.getIdentifier()),
        lambda _node: [3.0, 4.0],
        lambda value: repr(value),
    )

    assert result["target"] == {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"}
    assert result["exists"] is True
    assert result["nodes"] == [
        {
            "id": "target",
            "definition": "fake::target",
            "position": [3.0, 4.0],
            "parameters": {"gain": "0.5"},
        },
    ]
    assert result["owner_inputs"] == [{"id": "feather_length", "value_type": "float", "default": "0.25"}]
    assert result["output"] == {"node": "target"}


def test_get_nested_graph_state_payload_reports_missing_graph() -> None:
    """Command payload helper reports absent property graphs."""
    module = _load_nested_graphs_module()

    result = module.get_nested_graph_state_payload(
        FakeOuterGraph(),
        FakeOwnerNode(),
        "owner",
        "perpixel",
        "SDSBSFunctionGraph",
        lambda node: "fake::{}".format(node.getIdentifier()),
        lambda _node: [0.0, 0.0],
        lambda value: repr(value),
    )

    assert result == {
        "target": {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "exists": False,
        "nodes": [],
        "owner_inputs": [],
        "external_references": [],
        "connections": [],
        "output": None,
    }


def test_get_fx_map_graph_state_payload_reads_referenced_resource_graph() -> None:
    """FX-Map graph state is read from the owner node's referenced resource."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    fx_node = FakeNode("quadrant", [FakeProperty("patterntype")], "sbs::fxmap::paramset")
    fx_node.values["patterntype"] = FakeValue("2")
    owner.referenced_resource = FakeNestedGraph([fx_node], [fx_node])

    result = module.get_fx_map_graph_state_payload(
        FakeOuterGraph(),
        owner,
        "fxmap_node",
        lambda node: node.definition_id,
        lambda _node: [12.0, 24.0],
        lambda value: repr(value),
    )

    assert result["target"] == {"graph_identifier": "GraphA", "node_id": "fxmap_node"}
    assert result["graph_type"] == "SDSBSFxMapGraph"
    assert result["exists"] is True
    assert result["nodes"] == [
        {
            "id": "quadrant",
            "definition": "sbs::fxmap::paramset",
            "position": [12.0, 24.0],
            "parameters": {"patterntype": "2"},
        }
    ]
    assert result["output"] == {"node": "quadrant"}


def test_apply_nested_graph_state_command_rebuilds_property_graph() -> None:
    """Command helper validates state and rebuilds the property graph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    owner.property_graph = FakeNestedGraph([], [])
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "source", "definition": "fake::source"},
            {"id": "target", "definition": "fake::target", "parameters": {"gain": 0.5}},
        ],
        "connections": [
            {"from": "source", "from_output": "unique_filter_output", "to": "target", "to_input": "input1"}
        ],
        "output": {"node": "target"},
    }

    result = module.apply_nested_graph_state_command(
        state,
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert owner.deleted_properties == ["perpixel"]
    assert owner.property_graph is not None
    assert result["status"] == "applied"
    assert result["target"] == {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"}
    assert result["nodes_created"] == 2
    assert result["connections_created"] == 1
    assert owner.property_graph.output_node is owner.property_graph.created[1]


def test_apply_nested_graph_state_command_accepts_integer_target_node_id() -> None:
    """Command helper normalizes integer target node ids before host lookup."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    seen_node_ids: list[str] = []
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": 1572341796, "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [{"id": "source", "definition": "fake::source"}],
        "connections": [],
        "output": {"node": "source"},
    }

    result = module.apply_nested_graph_state_command(
        state,
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, node_id: seen_node_ids.append(node_id) or owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert seen_node_ids == ["1572341796"]
    assert result["target"] == {"graph_identifier": "GraphA", "node_id": "1572341796", "property": "perpixel"}


def test_apply_fx_map_graph_state_command_rebuilds_referenced_fx_map_graph() -> None:
    """FX-Map command helper rebuilds the referenced SDSBSFxMapGraph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    old_node = FakeNode("old", [], "sbs::fxmap::passthrough")
    owner.referenced_resource = FakeNestedGraph([old_node], [old_node])
    owner.referenced_resource.definitions = [
        FakeDefinition("sbs::fxmap::paramset"),
        FakeDefinition("sbs::fxmap::passthrough"),
    ]
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "fxmap_node"},
        "graph_type": "SDSBSFxMapGraph",
        "nodes": [
            {
                "id": "pattern",
                "definition": "sbs::fxmap::paramset",
                "parameters": {"patterntype": 2},
            }
        ],
        "connections": [],
        "output": {"node": "pattern"},
    }

    result = module.apply_fx_map_graph_state_command(
        state,
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["status"] == "applied"
    assert result["operation"] == "apply_fx_map_graph_state"
    assert result["target"] == {
        "graph_identifier": "GraphA",
        "node_id": "fxmap_node",
        "graph_type": "SDSBSFxMapGraph",
    }
    assert owner.referenced_resource.deleted == ["old"]
    assert owner.referenced_resource.created[0].definition_id == "sbs::fxmap::paramset"
    assert owner.referenced_resource.created[0].params == {"patterntype": 2}
    assert owner.referenced_resource.output_node is owner.referenced_resource.created[0]


def test_apply_fx_map_graph_patch_updates_existing_node_without_rebuild() -> None:
    """FX-Map patch updates an existing node without deleting or recreating it."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    existing = FakeNode("existing", [], "sbs::fxmap::paramset")
    owner.referenced_resource = FakeNestedGraph([existing], [existing])
    owner.referenced_resource.definitions = [
        FakeDefinition("sbs::fxmap::paramset"),
        FakeDefinition("sbs::fxmap::passthrough"),
    ]
    patch = {
        "target": {"graph_identifier": "GraphA", "node_id": "fxmap_node"},
        "graph_type": "SDSBSFxMapGraph",
        "operations": [
            {
                "op": "set_parameter",
                "node": "existing",
                "parameter": "patternsize",
                "value": [0.2, 0.2],
            }
        ],
    }

    result = module.apply_fx_map_graph_patch_command(
        patch,
        "patch",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: node.definition_id,
    )

    assert result["status"] == "patched"
    assert result["operation"] == "apply_fx_map_graph_patch"
    assert owner.referenced_resource.deleted == []
    assert owner.referenced_resource.created == []
    assert owner.referenced_resource.nodes == [existing]
    assert existing.params == {"patternsize": [0.2, 0.2]}


def test_apply_fx_map_graph_patch_removes_existing_input_connection() -> None:
    """FX-Map patch can remove one existing input connection without rebuilding the graph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    source = FakeNode("source", [FakeProperty("unique_filter_output")], "sbs::fxmap::paramset")
    target = FakeNode("target", [FakeProperty("input1")], "sbs::fxmap::passthrough")
    target.connections["input1"] = [FakeConnection(source, FakeProperty("unique_filter_output"))]
    owner.referenced_resource = FakeNestedGraph([source, target], [target])
    patch = {
        "target": {"graph_identifier": "GraphA", "node_id": "fxmap_node"},
        "graph_type": "SDSBSFxMapGraph",
        "operations": [{"op": "remove_connection", "to": "target", "to_input": "input1"}],
    }

    result = module.apply_fx_map_graph_patch_command(
        patch,
        "patch",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: node.definition_id,
    )

    assert result["status"] == "patched"
    assert result["operations"] == [{"op": "remove_connection", "to": "target", "to_input": "input1", "success": True}]
    assert target.deleted_connections == ["input1"]
    assert target.connections["input1"] == []
    assert owner.referenced_resource.deleted == []


def test_apply_fx_map_graph_patch_restores_child_property_graph_after_later_failure() -> None:
    """FX-Map patch rollback restores property graphs owned by nested nodes."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    quadrant = FakeNode("quadrant", [FakeProperty("branchoffset")], "sbs::fxmap::paramset")
    old_offset = FakeNode("old_offset", [], "fake::target")
    quadrant.property_graphs["branchoffset"] = FakeNestedGraph([old_offset], [old_offset], "SDSBSFunctionGraph")
    owner.referenced_resource = FakeNestedGraph([quadrant], [quadrant])
    owner.referenced_resource.definitions.append(FakeDefinition("sbs::fxmap::paramset"))
    patch = {
        "target": {"graph_identifier": "GraphA", "node_id": "fxmap_node"},
        "graph_type": "SDSBSFxMapGraph",
        "operations": [
            {
                "op": "set_property_graph",
                "node": "quadrant",
                "property": "branchoffset",
                "graph_type": "SDSBSFunctionGraph",
                "nodes": [{"id": "new_offset", "definition": "fake::source"}],
                "connections": [],
                "output": "new_offset",
            },
            {
                "op": "ensure_connection",
                "from": "quadrant",
                "from_output": "unique_filter_output",
                "to": "missing",
                "to_input": "input1",
            },
        ],
    }

    try:
        module.apply_fx_map_graph_patch_command(
            patch,
            "patch",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            _connect_fake_nodes,
            lambda node: node.definition_id,
        )
    except RuntimeError as exc:
        assert exc.details["rolled_back"] is True
    else:
        raise AssertionError("invalid FX-Map patch unexpectedly succeeded")

    restored = owner.referenced_resource.nodes[0]
    restored_graph = restored.property_graphs["branchoffset"]
    assert [node.definition_id for node in restored_graph.nodes] == ["fake::target"]
    assert restored_graph.output_node is restored_graph.nodes[0]


def test_apply_nested_graph_patch_accepts_builtin_connection_without_rebuild() -> None:
    """Function graph patch records builtin bindings without treating the builtin as a node."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    target = FakeNode("sample", [FakeProperty("pos")], "sbs::function::samplecol")
    owner.property_graph = FakeNestedGraph([target], [target])
    patch = {
        "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "operations": [{"op": "ensure_connection", "from": {"builtin": "$pos"}, "to": "sample", "to_input": "pos"}],
    }

    result = module.apply_nested_graph_patch_command(
        patch,
        "patch",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: node.definition_id,
    )

    assert result["operation"] == "apply_nested_graph_patch"
    assert result["operations"] == [
        {
            "op": "ensure_connection",
            "from_builtin": "$pos",
            "to": "sample",
            "to_input": "pos",
            "success": True,
            "binding": "host_implicit_builtin",
        }
    ]
    assert owner.property_graph.deleted == []


def test_apply_nested_graph_patch_creates_missing_property_graph() -> None:
    """Patch apply creates an editable property graph when the owner property exists but has no graph yet."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    patch = {
        "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "operations": [{"op": "ensure_node", "id": "value", "definition": "fake::target"}],
    }

    result = module.apply_nested_graph_patch_command(
        patch,
        "patch",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: node.definition_id,
    )

    assert result["operation"] == "apply_nested_graph_patch"
    assert result["created_property_graph"] is True
    assert owner.created_graph_types == ["SDSBSFunctionGraph"]
    assert owner.property_graph is not None
    assert result["operations"][0]["op"] == "ensure_node"


def test_apply_fx_map_graph_state_command_restores_referenced_graph_after_apply_failure() -> None:
    """Failed FX-Map replace restores the previous referenced graph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    old_node = FakeNode("old", [], "sbs::fxmap::passthrough")
    owner.referenced_resource = FakeNestedGraph([old_node], [old_node])
    owner.referenced_resource.definitions = [
        FakeDefinition("sbs::fxmap::paramset"),
        FakeDefinition("sbs::fxmap::passthrough"),
    ]
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "fxmap_node"},
        "graph_type": "SDSBSFxMapGraph",
        "nodes": [
            {"id": "source", "definition": "sbs::fxmap::paramset"},
            {"id": "target", "definition": "sbs::fxmap::passthrough"},
        ],
        "connections": [
            {"from": "source", "from_output": "unique_filter_output", "to": "target", "to_input": "missing"}
        ],
        "output": {"node": "target"},
    }

    def fail_connect(
        _graph: FakeNestedGraph,
        _from_node: FakeNode,
        _from_output: str,
        _to_node: FakeNode,
        _to_input: str,
    ) -> None:
        raise ValueError("available ports are pattern, switch")

    try:
        module.apply_fx_map_graph_state_command(
            state,
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            fail_connect,
            lambda node: node.definition_id,
            get_node_position=lambda _node: [10.0, 20.0],
            serialize_value=lambda value: repr(value),
        )
    except RuntimeError as exc:
        assert hasattr(exc, "details")
        assert exc.details["operation"] == "apply_fx_map_graph_state"
        assert exc.details["phase"] == "apply_nested_graph_state"
        assert exc.details["rolled_back"] is True
        assert exc.details["partial_changes"] is False
        assert "available ports are pattern, switch" in exc.details["error"]
    else:
        raise AssertionError("invalid FX-Map graph apply unexpectedly succeeded")

    assert owner.referenced_resource is not None
    assert [node.definition_id for node in owner.referenced_resource.nodes] == ["sbs::fxmap::passthrough"]
    assert owner.referenced_resource.output_node is owner.referenced_resource.nodes[0]


def test_apply_nested_graph_state_command_restores_existing_graph_after_apply_failure() -> None:
    """Failed destructive replace restores the previous property graph state."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    old_node = FakeNode("old", [], "fake::target")
    owner.property_graph = FakeNestedGraph([old_node], [old_node])
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "source", "definition": "fake::source"},
            {"id": "target", "definition": "fake::target"},
        ],
        "connections": [
            {"from": "source", "from_output": "unique_filter_output", "to": "target", "to_input": "missing"}
        ],
        "output": {"node": "target"},
    }

    def fail_connect(
        _graph: FakeNestedGraph,
        _from_node: FakeNode,
        _from_output: str,
        _to_node: FakeNode,
        _to_input: str,
    ) -> None:
        raise ValueError("available ports are scene, basecolor")

    try:
        module.apply_nested_graph_state_command(
            state,
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            fail_connect,
            lambda node: node.definition_id,
            get_node_position=lambda _node: [11.0, 22.0],
            serialize_value=lambda value: repr(value),
        )
    except RuntimeError as exc:
        assert hasattr(exc, "details")
        assert exc.details["phase"] == "apply_nested_graph_state"
        assert exc.details["rolled_back"] is True
        assert exc.details["partial_changes"] is False
        assert "available ports are scene, basecolor" in exc.details["error"]
    else:
        raise AssertionError("invalid nested graph apply unexpectedly succeeded")

    assert owner.property_graph is not None
    assert owner.property_graph.created[0].definition_id == "fake::target"
    assert owner.property_graph.output_node is owner.property_graph.created[0]


def test_apply_nested_graph_state_command_restores_existing_resource_instance_graph() -> None:
    """Rollback snapshots package-backed Function Graph instances with resource URLs."""
    module = _load_nested_graphs_module()
    resource_url = "pkg:///3d_sdf_primitives/3d_sdf_sphere?dependency=1566899378"
    package_manager = FakePackageManager([FakePackage("3d_functions.sbs", [FakeResource(resource_url)])])
    owner = FakeOwnerNode()
    old_node = FakeNode("old_sphere", [], "sbs::function::instance", FakeResource(resource_url))
    owner.property_graph = FakeNestedGraph([old_node], [old_node])
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [{"id": "bad", "definition": "unknown::node"}],
        "connections": [],
        "output": {"node": "bad"},
    }

    try:
        module.apply_nested_graph_state_command(
            state,
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            _connect_fake_nodes,
            lambda node: node.definition_id,
            package_manager=package_manager,
            get_node_position=lambda _node: [0.0, 0.0],
            serialize_value=lambda value: repr(value),
        )
    except RuntimeError as exc:
        assert hasattr(exc, "details")
        assert exc.details["rolled_back"] is True
        assert exc.details["partial_changes"] is False
    else:
        raise AssertionError("invalid nested graph apply unexpectedly succeeded")

    assert owner.property_graph is not None
    assert owner.property_graph.instance_resources == [resource_url]
    assert owner.property_graph.output_node is owner.property_graph.created[0]


def test_apply_nested_graph_state_command_requires_existing_external_references() -> None:
    """Nested apply validates owner input dependencies without creating them."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    state = {
        "target": {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        "graph_type": "SDSBSFunctionGraph",
        "external_references": [{"id": "feather_length", "value_type": "float"}],
        "nodes": [{"id": "source", "definition": "fake::source"}],
        "connections": [],
        "output": {"node": "source"},
    }

    try:
        module.apply_nested_graph_state_command(
            state,
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            _connect_fake_nodes,
            lambda node: "definition::{}".format(node.getIdentifier()),
        )
    except ValueError as exc:
        assert "Missing owner input properties" in str(exc)
    else:
        raise AssertionError("missing external reference was accepted")

    assert owner.created_inputs == []
    assert owner.property_graph is None


def test_bind_parameter_input_command_creates_input_and_parameter_graph() -> None:
    """Binding command creates the owner input and parameter function graph."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()

    result = module.bind_parameter_input_command(
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        {
            "id": "feather_length",
            "value_type": "float",
            "default": 0.25,
            "min": 0,
            "max": 1,
            "step": 0.01,
            "clamp": True,
        },
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert owner.created_inputs == [("feather_length", "float", 0)]
    assert _value_payload(owner.values["feather_length"]) == 0.25
    assert _value_payload(owner.property_annotations[("feather_length", "clamp")]) is True
    assert result["input"] == {
        "id": "feather_length",
        "requested_id": "feather_length",
        "actual_property_id": "feather_length",
        "function_reference": "feather_length",
        "value_type": "float",
        "status": "created",
    }
    assert result["next_tools"][0]["tool"] == "get_nested_graph_state"
    assert owner.property_graph is not None
    assert owner.property_graph.created[0].params == {"__constant__": {"value": "feather_length", "type": "string"}}
    assert owner.property_graph.output_node is owner.property_graph.created[0]


def test_bind_parameter_input_normalizes_existing_owner_input_reference() -> None:
    """Binding uses a bare variable id in the generated get node."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    owner.input_props.append(FakeProperty("#color_root", "ColorRGBA"))

    result = module.bind_parameter_input_command(
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        {"id": "color_root", "value_type": "color"},
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["input"] == {
        "id": "#color_root",
        "requested_id": "color_root",
        "actual_property_id": "#color_root",
        "function_reference": "color_root",
        "value_type": "color",
        "status": "existing",
    }
    assert owner.created_inputs == []
    assert owner.property_graph is not None
    assert owner.property_graph.created[0].params == {"__constant__": {"value": "color_root", "type": "string"}}


def test_bind_parameter_input_normalizes_hash_prefixed_requested_id() -> None:
    """Binding accepts #foo input ids but creates and references the bare id."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()

    result = module.bind_parameter_input_command(
        {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
        {"id": "#color_root", "value_type": "color"},
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert owner.created_inputs == [("color_root", "colorrgba", 0)]
    assert result["input"] == {
        "id": "color_root",
        "requested_id": "#color_root",
        "actual_property_id": "color_root",
        "function_reference": "color_root",
        "value_type": "color",
        "status": "created",
    }
    assert owner.property_graph is not None
    assert owner.property_graph.created[0].params == {"__constant__": {"value": "color_root", "type": "string"}}


def test_bind_parameter_input_accepts_input_aliases_and_infers_default_type() -> None:
    """Binding accepts input_id aliases and infers value_type from defaults."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()

    result = module.bind_parameter_input_command(
        {"graph_identifier": "GraphA", "node_id": "owner", "property_id": "perpixel"},
        {"input_id": "#tint", "default": [1, 0, 0, 1]},
        "replace",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: owner,
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert owner.created_inputs == [("tint", "float4", 0)]
    assert result["input"]["value_type"] == "float4"
    assert owner.property_graph is not None
    assert owner.property_graph.created[0].definition_id == "sbs::function::get_float4"


def test_bind_parameter_input_does_not_create_input_when_graph_creation_fails() -> None:
    """Binding creates the function graph before mutating owner inputs."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    owner.input_props.append(FakeProperty("opacitymult"))

    try:
        module.bind_parameter_input_command(
            {"graph_identifier": "GraphA", "node_id": "owner", "property": "opacitymult"},
            {"id": "feather_length", "value_type": "float", "default": 0.25},
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            _connect_fake_nodes,
            lambda node: "definition::{}".format(node.getIdentifier()),
        )
    except module.NestedGraphMutationError as exc:
        assert exc.details["phase"] == "rebuild_property_graph"
        assert "newPropertyGraph returned None" in exc.details["error"]
        assert exc.details["rolled_back"] is False
        assert exc.details["partial_changes"] is False
    else:
        raise AssertionError("binding succeeded without writable property graph")

    assert owner.created_inputs == []
    assert owner.getPropertyFromId("feather_length", 0) is None


def test_bind_parameter_input_reports_read_only_property_graph_scope() -> None:
    """Read-only property graph replacement failures return classified diagnostics."""
    module = _load_nested_graphs_module()
    owner = FakeOwnerNode()
    owner.property_graph = FakeNestedGraph([], [])
    owner.delete_property_graph_error = RuntimeError("SDApiError.DataIsReadOnly")

    try:
        module.bind_parameter_input_command(
            {"graph_identifier": "GraphA", "node_id": "owner", "property": "perpixel"},
            {"id": "color_root", "value_type": "color", "default": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0}},
            "replace",
            lambda _graph_identifier: FakeOuterGraph(),
            lambda _graph, _node_id: owner,
            _set_fake_params,
            _connect_fake_nodes,
            lambda node: "definition::{}".format(node.getIdentifier()),
        )
    except module.NestedGraphMutationError as exc:
        assert exc.details["phase"] == "rebuild_property_graph"
        assert exc.details["rolled_back"] is False
        assert exc.details["partial_changes"] is False
        assert exc.details["created_owner_inputs"] == []
        assert exc.details["error_classification"]["kind"] == "read_only"
        assert exc.details["error_classification"]["scope"] == "property_graph"
    else:
        raise AssertionError("read-only property graph was not reported")

    assert owner.created_inputs == []
    assert owner.property_graph is not None


def test_apply_nested_graph_state_command_returns_param_update_conflict() -> None:
    """Command helper preserves the param_update conflict contract."""
    module = _load_nested_graphs_module()

    result = module.apply_nested_graph_state_command(
        {},
        "param_update",
        lambda _graph_identifier: FakeOuterGraph(),
        lambda _graph, _node_id: FakeOwnerNode(),
        _set_fake_params,
        _connect_fake_nodes,
        lambda node: "definition::{}".format(node.getIdentifier()),
    )

    assert result["status"] == "conflict"
    assert result["operation"] == "param_update"


def _set_fake_params(node: FakeNode, params: dict[str, FakeJsonValue]) -> None:
    """Record fake node parameters."""
    node.params = params


def _set_fake_params_with_status(node: FakeNode, params: dict[str, FakeJsonValue]) -> dict[str, FakeJsonValue]:
    """Record fake node parameters and return ok statuses."""
    node.params = params
    return dict.fromkeys(params, "ok")


def _connect_fake_nodes(
    graph: FakeNestedGraph,
    from_node: FakeNode,
    from_output: str,
    to_node: FakeNode,
    to_input: str,
) -> None:
    """Record a fake nested graph connection."""
    graph.connected.append((from_node.getIdentifier(), from_output, to_node.getIdentifier(), to_input))


def _value_payload(value: object) -> FakeJsonValue:
    """Return the payload carried by fallback SDValue fakes."""
    if hasattr(value, "value"):
        return value.value
    raise AssertionError("value does not carry a fake SDValue payload")


def _load_nested_graphs_module() -> types.ModuleType:
    """Load concrete nested graph helper modules without writing bytecode."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    previous_package = sys.modules.get("plugin")
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.nested_graph.nested_graph_operations",
        "plugin.nested_graph.nested_graph_operations",
        "plugin.nested_graph.nested_graph_operations",
        "plugin.nested_graph.nested_graph_queries",
        "plugin.nested_graph.nested_graph_queries",
        "plugin.nested_graph.nested_graph_state",
        "plugin.nested_graph.nested_graph_operations",
        "plugin.nested_graph.nested_graph_types",
    ]:
        sys.modules.pop(module_name, None)
    module = _load_module("plugin.nested_graph.nested_graph_operations", NESTED_GRAPH_STRUCTURE_PATH)
    serialization = _load_module("plugin.nested_graph.nested_graph_queries", NESTED_GRAPH_SERIALIZATION_PATH)
    application = _load_module("plugin.nested_graph.nested_graph_operations", NESTED_GRAPH_APPLICATION_PATH)
    inspection = _load_module("plugin.nested_graph.nested_graph_queries", NESTED_GRAPH_INSPECTION_PATH)
    apply_module = _load_module("plugin.nested_graph.nested_graph_operations", NESTED_GRAPH_APPLY_PATH)
    module.serialize_nested_graph_state = serialization.serialize_nested_graph_state
    module.apply_nested_graph_state_to_graph = application.apply_nested_graph_state_to_graph
    module.get_nested_graph_state_payload = inspection.get_nested_graph_state_payload
    module.get_fx_map_graph_state_payload = inspection.get_fx_map_graph_state_payload
    module.apply_nested_graph_state_command = apply_module.apply_nested_graph_state_command
    module.apply_fx_map_graph_state_command = apply_module.apply_fx_map_graph_state_command
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
