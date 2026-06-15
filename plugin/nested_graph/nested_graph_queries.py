"""Nested graph inspection and serialization helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from sd.api.sdproperty import SDPropertyCategory

from ..json_types import JsonValue
from .nested_graph_operations import find_node_property
from .nested_graph_types import (
    NestedConnection,
    NestedGraph,
    NestedGraphState,
    NestedNode,
    NestedNodeState,
    NestedOwnerGraph,
    NestedProperty,
    NodeDefinitionGetter,
    NodePositionGetter,
    OutputGetter,
    OutputNodeCollection,
    PropertyGraphOwner,
    ValueSerializer,
)


def get_nested_graph_state_payload(
    graph: NestedOwnerGraph,
    owner_node: PropertyGraphOwner,
    node_id: str,
    property_id: str,
    graph_type: str,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter,
    serialize_value: ValueSerializer,
) -> NestedGraphState:
    """Return the command payload for a node property nested graph."""
    prop = find_node_property(owner_node, property_id)
    try:
        nested_graph = owner_node.getPropertyGraph(prop)
    except Exception as exc:
        raise RuntimeError("Failed to read nested graph '{}.{}': {}".format(node_id, property_id, exc)) from exc

    target: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "property": property_id,
    }
    if nested_graph is None:
        return {
            "target": target,
            "graph_type": graph_type,
            "exists": False,
            "nodes": [],
            "owner_inputs": owner_input_nodes(owner_node, property_id, serialize_value),
            "external_references": [],
            "connections": [],
            "output": None,
        }

    state = serialize_nested_graph_state(nested_graph, get_node_definition, get_node_position, serialize_value)
    return {
        "target": target,
        "graph_type": graph_type,
        "exists": True,
        "nodes": state["nodes"],
        "owner_inputs": owner_input_nodes(owner_node, property_id, serialize_value),
        "external_references": external_references(json_list(state.get("nodes"))),
        "connections": state["connections"],
        "output": state["output"],
    }


def get_fx_map_graph_state_payload(
    graph: NestedOwnerGraph,
    owner_node: PropertyGraphOwner,
    node_id: str,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter,
    serialize_value: ValueSerializer,
) -> NestedGraphState:
    """Return the command payload for an FX-Map node's referenced graph."""
    nested_graph = fx_map_referenced_graph(owner_node, node_id)
    target: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
    }
    if nested_graph is None:
        return {
            "target": target,
            "graph_type": "SDSBSFxMapGraph",
            "exists": False,
            "nodes": [],
            "connections": [],
            "output": None,
        }
    state = serialize_nested_graph_state(nested_graph, get_node_definition, get_node_position, serialize_value)
    return {
        "target": target,
        "graph_type": "SDSBSFxMapGraph",
        "exists": True,
        "nodes": state["nodes"],
        "connections": state["connections"],
        "output": state["output"],
    }


def fx_map_referenced_graph(owner_node: PropertyGraphOwner, node_id: str) -> NestedGraph | None:
    """Return the SDSBSFxMapGraph referenced by an FX-Map compositing node."""
    try:
        resource = owner_node.getReferencedResource()
    except Exception as exc:
        raise RuntimeError("Failed to read FX-Map referenced graph '{}': {}".format(node_id, exc)) from exc
    if resource is None:
        return None
    try:
        class_name = resource.getClassName()
    except Exception:
        class_name = ""
    if class_name and class_name != "SDSBSFxMapGraph":
        raise ValueError("Node '{}' references '{}', not SDSBSFxMapGraph.".format(node_id, class_name))
    return resource


def owner_input_nodes(
    owner_node: PropertyGraphOwner,
    nested_property_id: str,
    serialize_value: ValueSerializer,
) -> list[JsonValue]:
    """Return owner-node input properties."""
    input_nodes: list[JsonValue] = []
    try:
        input_props = list(owner_node.getProperties(SDPropertyCategory.Input))
    except Exception:
        input_props = []
    for prop in input_props:
        try:
            property_id = prop.getId()
        except Exception:
            continue
        if property_id == nested_property_id or property_id.startswith("$"):
            continue
        state: dict[str, JsonValue] = {"id": property_id}
        value_type = property_type_id(prop)
        if value_type is not None:
            state["value_type"] = value_type
        try:
            value = owner_node.getPropertyValue(prop)
            if value is not None:
                state["default"] = serialize_value(value)
        except Exception:
            pass
        input_nodes.append(state)
    return input_nodes


def json_list(value: JsonValue) -> list[JsonValue]:
    """Return a JSON list value or an empty list for missing state."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise ValueError("nested graph state nodes must be a list.")


def external_references(nodes: list[JsonValue]) -> list[JsonValue]:
    """Return #owner-input references used by serialized get_* nodes."""
    references: list[JsonValue] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        params = node.get("parameters")
        if not isinstance(params, dict):
            continue
        value = params.get("__constant__") or params.get("value")
        if isinstance(value, str) and value.startswith("#") and len(value) > 1:
            reference_id = value[1:]
        elif isinstance(value, dict) and isinstance(value.get("value"), str) and value["value"].startswith("#"):
            reference_id = value["value"][1:]
        else:
            continue
        if reference_id not in seen:
            references.append({"id": reference_id})
            seen.add(reference_id)
    return references


def property_type_id(prop: NestedProperty) -> str | None:
    """Return a property type identifier when the host exposes one."""
    try:
        property_type = prop.getType()
        get_id = getattr(property_type, "getId", None)
        if callable(get_id):
            value = get_id()
            return str(value) if value else None
        return str(property_type) if property_type is not None else None
    except Exception:
        return None


def serialize_nested_graph_state(
    nested_graph: NestedGraph,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter,
    serialize_value: ValueSerializer,
) -> NestedGraphState:
    """Serialize nodes, connections, and output state from a nested graph."""
    nodes: list[JsonValue] = []
    connections: list[JsonValue] = []
    try:
        nested_nodes = list(nested_graph.getNodes())
    except Exception:
        nested_nodes = []

    for nested_node in nested_nodes:
        node_state: NestedNodeState = {
            "id": nested_node.getIdentifier(),
            "definition": get_node_definition(nested_node),
            "position": get_node_position(nested_node),
        }
        params = node_parameters_and_connections(nested_node, serialize_value, connections)
        if params:
            node_state["parameters"] = params
        nodes.append(node_state)

    output = nested_graph_output_state(nested_graph)
    return {
        "nodes": nodes,
        "connections": connections,
        "output": output,
    }


def node_parameters_and_connections(
    nested_node: NestedNode,
    serialize_value: ValueSerializer,
    connections: list[JsonValue],
) -> dict[str, JsonValue]:
    """Return unconnected parameter values and append connection records."""
    params: dict[str, JsonValue] = {}
    try:
        input_props = list(nested_node.getProperties(SDPropertyCategory.Input))
    except Exception:
        input_props = []
    for input_prop in input_props:
        property_id = input_prop.getId()
        connection_list = property_connections(nested_node, input_prop)
        if connection_list:
            append_connection_states(nested_node, property_id, connection_list, connections)
            continue
        try:
            value = nested_node.getPropertyValue(input_prop)
            if value is not None:
                params[property_id] = serialize_value(value)
        except Exception:
            pass
    return params


def property_connections(nested_node: NestedNode, input_prop: NestedProperty) -> list[NestedConnection]:
    """Return property connections for a nested node input."""
    try:
        connections = nested_node.getPropertyConnections(input_prop)
        return list(connections) if connections is not None else []
    except Exception:
        return []


def append_connection_states(
    nested_node: NestedNode,
    property_id: str,
    connections: list[NestedConnection],
    connection_states: list[JsonValue],
) -> None:
    """Append serializable connection state entries."""
    for conn in connections:
        try:
            source_node = conn.getInputPropertyNode()
            source_property = conn.getInputProperty()
            if source_node and source_property:
                connection_states.append(
                    {
                        "from": source_node.getIdentifier(),
                        "from_output": source_property.getId(),
                        "to": nested_node.getIdentifier(),
                        "to_input": property_id,
                    }
                )
        except Exception:
            pass


def nested_graph_output_state(nested_graph: NestedGraph) -> JsonValue:
    """Return the first nested graph output node state."""
    output_nodes = get_nested_graph_output_nodes(nested_graph)
    if output_nodes:
        try:
            return {"node": output_nodes[0].getIdentifier()}
        except Exception:
            return None
    return None


def get_nested_graph_output_nodes(nested_graph: NestedGraph) -> list[NestedNode]:
    """Return output nodes from a nested graph using host API fallbacks."""
    for method_name in ("getOutputNodes", "getOutputNode"):
        try:
            method = cast(OutputGetter, getattr(nested_graph, method_name))
        except Exception:
            continue
        try:
            result = method()
            if result is None:
                continue
            if isinstance(result, (list, tuple)):
                return sequence_nodes(cast(Sequence[NestedNode], result))
            if hasattr(result, "getSize") and hasattr(result, "getItem"):
                return collection_nodes(cast(OutputNodeCollection, result))
            return [cast(NestedNode, result)]
        except Exception:
            pass
    return []


def collection_nodes(collection: OutputNodeCollection) -> list[NestedNode]:
    """Return non-empty nodes from a host collection."""
    nodes: list[NestedNode] = []
    for index in range(collection.getSize()):
        item = collection.getItem(index)
        if item is not None:
            nodes.append(item)
    return nodes


def sequence_nodes(nodes: Sequence[NestedNode]) -> list[NestedNode]:
    """Return non-empty nodes from a sequence."""
    return [node for node in nodes if node is not None]
