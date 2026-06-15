"""Unified editable control helpers for graph, node, and property-backed values."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from typing import Protocol, cast, runtime_checkable

from sd.api.sdproperty import SDPropertyCategory

from .json_types import JsonMap, JsonValue
from .nested_graph.nested_graph_operations import (
    ensure_owner_input,
    find_node_property,
    input_property_from_id,
    normalize_global_variable_reference,
    sd_value_for,
)
from .nested_graph.nested_graph_types import PropertyGraphOwner
from .node.node_queries import get_property_info
from .node.node_types import HostProperty as NodeHostProperty
from .parameters.parameter_types import ParameterNode, ReprFallback, SettableSDValue
from .parameters.parameter_types import ValueInput as ParameterValueInput
from .parameters.parameters import set_parameter_value, value_input
from .parameters.sd_values import coerce_value_type, infer_value_type, make_sd_value

CONSTRAINT_KEYS = ("min", "max", "step", "group", "editor", "clamp")
SYSTEM_INPUT_PREFIX = "$"


class HostProperty(Protocol):
    """Property methods used by control inspection."""

    def getId(self) -> str:
        """Return property identifier."""
        ...

    def getType(self) -> ReprFallback | None:
        """Return property type."""
        ...


@runtime_checkable
class ValueGetter(Protocol):
    """Value wrapper exposing a raw host value."""

    def get(self) -> JsonValue | ReprFallback:
        """Return the wrapped value."""
        ...


class ValueOwner(Protocol):
    """Object exposing property values."""

    def getProperties(self, category: int) -> Iterable[HostProperty]:
        """Return properties for a category."""
        ...

    def getPropertyValue(self, prop: HostProperty) -> ReprFallback:
        """Return property value."""
        ...


class NodeDefinition(Protocol):
    """Node definition handle."""

    def getId(self) -> str:
        """Return definition id."""
        ...


class MutableValueOwner(ValueOwner, Protocol):
    """Object exposing mutable input values."""

    def newProperty(self, property_id: str, property_type: ReprFallback, category: int) -> HostProperty:
        """Create a new input property."""
        ...

    def setInputPropertyValueFromId(self, property_id: str, value: SettableSDValue) -> None:
        """Set an input value by id."""
        ...


class NodeLike(ValueOwner, Protocol):
    """Node methods used by control helpers."""

    def getIdentifier(self) -> str:
        """Return node identifier."""
        ...

    def getDefinition(self) -> NodeDefinition | None:
        """Return node definition."""
        ...

    def getPropertyConnections(self, prop: HostProperty) -> Iterable[ReprFallback]:
        """Return property connections."""
        ...


class NestedGraphLike(Protocol):
    """Nested graph methods used by control helpers."""

    def getNodes(self) -> Iterable[NodeLike]:
        """Return nested graph nodes."""
        ...


class GraphLike(MutableValueOwner, Protocol):
    """Graph methods used by control helpers."""

    def getIdentifier(self) -> str:
        """Return graph identifier."""
        ...


class NestedGraphOwner(MutableValueOwner, Protocol):
    """Node that owns a property graph."""

    def getIdentifier(self) -> str:
        """Return node identifier."""
        ...

    def getPropertyFromId(self, property_id: str, category: int) -> HostProperty | None:
        """Return a property by id and category."""
        ...

    def getPropertyGraph(self, prop: HostProperty) -> NestedGraphLike | None:
        """Return a property graph."""
        ...

    def deletePropertyGraph(self, prop: HostProperty) -> None:
        """Delete a property graph."""
        ...

    def newPropertyGraph(self, prop: HostProperty, graph_type: str) -> NestedGraphLike | None:
        """Create a property graph."""
        ...

    def setPropertyValue(self, prop: HostProperty, value: SettableSDValue) -> None:
        """Set a property value."""
        ...

    def setPropertyAnnotationValueFromId(self, prop: HostProperty, annotation_id: str, value: SettableSDValue) -> None:
        """Set a property annotation."""
        ...


ValueSerializer = Callable[[ReprFallback], JsonValue]
ParameterSetter = Callable[[ReprFallback, JsonMap], None]
GraphResolver = Callable[[str | None], GraphLike]
NodeFinder = Callable[[GraphLike, JsonValue], NodeLike]


def list_controls(
    target_value: JsonValue,
    *,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    serialize_value: ValueSerializer,
) -> JsonMap:
    """List editable controls for a graph, node, or node property target."""
    target = target_mapping(target_value)
    kind = required_string(target.get("kind"), "target.kind is required.")
    if kind == "graph":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        return {
            "target": {"kind": "graph", "graph_identifier": graph_identifier(graph)},
            "controls": graph_input_controls(cast(MutableValueOwner, graph), serialize_value),
        }
    if kind == "node":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        node_id = required_string(target.get("node_id"), "target.node_id is required.")
        node = find_node(graph, node_id)
        return {
            "target": {"kind": "node", "graph_identifier": graph_identifier(graph), "node_id": node_id},
            "controls": node_controls(node, node_id, serialize_value),
        }
    if kind == "node_property":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        node_id = required_string(target.get("node_id"), "target.node_id is required.")
        property_id = required_string(
            target.get("property") or target.get("property_id"), "target.property is required."
        )
        node = find_node(graph, node_id)
        controls = property_controls(cast(NestedGraphOwner, node), node_id, property_id, serialize_value)
        return {
            "target": {
                "kind": "node_property",
                "graph_identifier": graph_identifier(graph),
                "node_id": node_id,
                "property": property_id,
            },
            "controls": controls,
        }
    raise ValueError("Unknown control target kind '{}'. Valid: graph, node, node_property".format(kind))


def set_controls(
    target_value: JsonValue,
    updates_value: JsonValue,
    *,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    serialize_value: ValueSerializer,
    set_node_params: ParameterSetter,
) -> JsonMap:
    """Apply editable control updates."""
    target = target_mapping(target_value)
    updates = list_mapping(updates_value, "updates")
    kind = required_string(target.get("kind"), "target.kind is required.")
    if kind == "graph":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        results = [set_graph_input_control(graph, update, serialize_value) for update in updates]
        return {"target": {"kind": "graph", "graph_identifier": graph_identifier(graph)}, "updated": results}
    if kind == "node":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        node_id = required_string(target.get("node_id"), "target.node_id is required.")
        node = find_node(graph, node_id)
        results = [set_node_control(node, node_id, update) for update in updates]
        return {
            "target": {"kind": "node", "graph_identifier": graph_identifier(graph), "node_id": node_id},
            "updated": results,
        }
    if kind == "node_property":
        graph = resolve_graph(optional_string(target.get("graph_identifier")))
        node_id = required_string(target.get("node_id"), "target.node_id is required.")
        property_id = required_string(
            target.get("property") or target.get("property_id"), "target.property is required."
        )
        node = find_node(graph, node_id)
        results = [
            set_property_control(cast(NestedGraphOwner, node), property_id, update, serialize_value, set_node_params)
            for update in updates
        ]
        return {
            "target": {
                "kind": "node_property",
                "graph_identifier": graph_identifier(graph),
                "node_id": node_id,
                "property": property_id,
            },
            "updated": results,
            "rebuilt": False,
            "node_map": {},
        }
    raise ValueError("Unknown control target kind '{}'. Valid: graph, node, node_property".format(kind))


def list_graph_inputs(graph: MutableValueOwner, serialize_value: ValueSerializer) -> JsonMap:
    """Return graph input controls through the graph-input convenience surface."""
    return {"inputs": graph_input_controls(graph, serialize_value)}


def set_graph_input(
    graph: MutableValueOwner,
    input_id: str,
    value: JsonValue,
    value_type: str | None,
    serialize_value: ValueSerializer,
    metadata: JsonMap | None = None,
) -> JsonMap:
    """Set one graph input through the graph-input convenience surface."""
    metadata = metadata or {}
    return set_graph_input_control(
        graph,
        {"id": input_id, "value": value, **({"value_type": value_type} if value_type else {}), **metadata},
        serialize_value,
    )


def graph_input_controls(graph: MutableValueOwner, serialize_value: ValueSerializer) -> list[JsonMap]:
    """List graph input controls."""
    controls = []
    for prop in properties(graph, SDPropertyCategory.Input):
        prop_id = prop.getId()
        if prop_id.startswith(SYSTEM_INPUT_PREFIX):
            continue
        info = property_info(prop)
        value = property_value(graph, prop, serialize_value)
        metadata = property_annotations(graph, prop, serialize_value)
        constraints = property_constraints(metadata)
        controls.append(
            {
                "id": prop_id,
                "label": info.get("label") or prop_id,
                "value": value,
                "value_type": adapter_value_type(info.get("type"), value),
                "type": adapter_value_type(info.get("type"), value),
                "sd_type": info.get("type"),
                "writable": writable_by_api(graph, "setInputPropertyValueFromId"),
                "writable_source": "setInputPropertyValueFromId",
                "exposed": True,
                "exposed_source": "graph_input_property",
                "constraints": constraints,
                "description": metadata.get("description"),
                "min": metadata.get("min"),
                "max": metadata.get("max"),
                "step": metadata.get("step"),
                "group": metadata.get("group"),
                "editor": metadata.get("editor"),
                "clamp": metadata.get("clamp"),
                "role": "graph_input",
                "source": {"kind": "graph_input", "input_id": prop_id},
            }
        )
    return controls


def node_controls(node: NodeLike, node_id: str, serialize_value: ValueSerializer) -> list[JsonMap]:
    """List direct node input and annotation controls."""
    controls = []
    for category, category_name, role in (
        (SDPropertyCategory.Input, "input", "node_parameter"),
        (SDPropertyCategory.Annotation, "annotation", "node_annotation"),
    ):
        for prop in properties(cast(ValueOwner, node), category):
            prop_id = prop.getId()
            if prop_id.startswith(SYSTEM_INPUT_PREFIX):
                continue
            info = property_info(prop)
            value = property_value(cast(ValueOwner, node), prop, serialize_value)
            control_id = prop_id
            metadata = property_annotations(cast(ValueOwner, node), prop, serialize_value)
            controls.append(
                {
                    "id": control_id,
                    "label": info.get("label") or prop_id,
                    "value": value,
                    "value_type": adapter_value_type(info.get("type"), value),
                    "sd_type": info.get("type"),
                    "writable": node_property_writable(node, category_name),
                    "writable_source": writable_source(category_name),
                    "constraints": property_constraints(metadata),
                    "role": role,
                    **control_metadata(metadata),
                    "source": {
                        "kind": "node_parameter",
                        "node_id": node_id,
                        "category": category_name,
                        "parameter_id": prop_id,
                    },
                }
            )
    return controls


def property_controls(
    owner_node: NestedGraphOwner,
    node_id: str,
    property_id: str,
    serialize_value: ValueSerializer,
) -> list[JsonMap]:
    """List controls backed by a node-owned property graph and owner inputs."""
    prop = find_node_property(owner_node, property_id)
    nested_graph = owner_node.getPropertyGraph(prop)
    if nested_graph is None:
        return []
    controls: list[JsonMap] = []
    for nested_node in graph_nodes(nested_graph):
        nested_node_id = nested_node.getIdentifier()
        definition = node_definition(nested_node)
        for input_prop in properties(cast(ValueOwner, nested_node), SDPropertyCategory.Input):
            parameter_id = input_prop.getId()
            if property_has_connections(nested_node, input_prop):
                continue
            value = property_value(cast(ValueOwner, nested_node), input_prop, serialize_value)
            info = property_info(input_prop)
            reference_id = external_reference_id(value)
            if reference_id:
                controls.append(
                    owner_input_control(
                        owner_node, node_id, property_id, reference_id, nested_node_id, definition, serialize_value
                    )
                )
                continue
            role = "constant" if parameter_id in {"__constant__", "value"} else "node_parameter"
            metadata = property_annotations(cast(ValueOwner, nested_node), input_prop, serialize_value)
            controls.append(
                {
                    "id": "{}.{}".format(nested_node_id, parameter_id),
                    "label": parameter_id,
                    "value": value,
                    "value_type": adapter_value_type(info.get("type"), value),
                    "sd_type": info.get("type"),
                    "writable": node_property_writable(nested_node, "input"),
                    "writable_source": writable_source("input"),
                    "constraints": property_constraints(metadata),
                    "role": role,
                    **control_metadata(metadata),
                    "source": {
                        "kind": "property_graph_parameter",
                        "owner_node_id": node_id,
                        "property": property_id,
                        "graph_type": "SDSBSFunctionGraph",
                        "node_id": nested_node_id,
                        "definition": definition,
                        "parameter_id": parameter_id,
                    },
                }
            )
    return controls


def owner_input_control(
    owner_node: NestedGraphOwner,
    node_id: str,
    property_id: str,
    reference_id: str,
    nested_node_id: str,
    definition: str | None,
    serialize_value: ValueSerializer,
) -> JsonMap:
    """Return a control backed by an owner-node input referenced from a property graph."""
    prop = input_property_from_id(cast(PropertyGraphOwner, owner_node), reference_id)
    info: JsonMap = {"id": reference_id}
    value: JsonValue = None
    metadata: JsonMap = {}
    if prop is not None:
        info = property_info(prop)
        value = property_value(owner_node, prop, serialize_value)
        metadata = property_annotations(owner_node, prop, serialize_value)
    return {
        "id": reference_id,
        "label": info.get("label") or reference_id,
        "value": value,
        "value_type": adapter_value_type(info.get("type"), value),
        "sd_type": info.get("type"),
        "writable": prop is not None and writable_by_api(owner_node, "setInputPropertyValueFromId"),
        "writable_source": "setInputPropertyValueFromId" if prop is not None else "missing_property",
        "constraints": property_constraints(metadata),
        "role": "external_reference",
        **control_metadata(metadata),
        "source": {
            "kind": "owner_input",
            "owner_node_id": node_id,
            "property": property_id,
            "input_id": reference_id,
            "referenced_by": {"node_id": nested_node_id, "definition": definition},
        },
    }


def set_graph_input_control(graph: MutableValueOwner, update: JsonMap, serialize_value: ValueSerializer) -> JsonMap:
    """Create or set one graph input control."""
    requested_input_id = required_string(update.get("id") or update.get("input_id"), "control id is required.")
    input_id = normalize_global_variable_reference(requested_input_id)
    prop = property_from_id(graph, input_id, SDPropertyCategory.Input)
    old_value = property_value(graph, prop, serialize_value) if prop is not None else None
    value_present = "value" in update
    if prop is None:
        value_type = optional_string(update.get("value_type")) or (
            infer_value_type(parameter_value_input(update.get("value"))) if value_present else "float"
        )
        spec = graph_input_spec(input_id, requested_input_id, value_type, update, value_present)
        input_result = ensure_owner_input(cast(PropertyGraphOwner, graph), spec)
        prop = property_from_id(graph, input_id, SDPropertyCategory.Input)
        if prop is None:
            prop = input_property_from_id(cast(PropertyGraphOwner, graph), input_id)
        if prop is None:
            raise ValueError("Graph input '{}' was created but could not be read back.".format(input_id))
        status = "created"
    else:
        input_result = None
        status = "updated"
        if graph_input_has_metadata(update):
            value_type = optional_string(update.get("value_type")) or adapter_value_type(
                property_info(prop).get("type"), old_value
            )
            ensure_owner_input(
                cast(PropertyGraphOwner, graph),
                graph_input_spec(input_id, requested_input_id, value_type, update, False),
            )
    if not value_present:
        return {
            "id": input_id,
            "input_id": input_id,
            "requested_id": requested_input_id,
            "old_value": old_value,
            "value": property_value(graph, prop, serialize_value),
            "value_type": adapter_value_type(property_info(prop).get("type"), old_value),
            "sd_type": property_info(prop).get("type"),
            "status": status,
            **({"input": input_result} if input_result is not None else {}),
        }
    sd_type = property_info(prop).get("type")
    value = update.get("value")
    value_input = parameter_value_input(value)
    value_type = optional_string(update.get("value_type")) or adapter_value_type(sd_type, value)
    coerced_type = coerce_value_type(value_type, value_input, cast(str | None, sd_type))
    graph.setInputPropertyValueFromId(input_id, make_sd_value(coerced_type, value_input))
    return {
        "id": input_id,
        "input_id": input_id,
        "requested_id": requested_input_id,
        "old_value": old_value,
        "value": value,
        "value_type": coerced_type,
        "sd_type": sd_type,
        "status": status,
        **({"input": input_result} if input_result is not None else {}),
    }


def graph_input_spec(
    input_id: str,
    requested_input_id: str,
    value_type: str,
    update: JsonMap,
    include_default: bool,
) -> JsonMap:
    """Return an owner-input style spec for graph input upsert."""
    spec: JsonMap = {"id": input_id, "requested_id": requested_input_id, "value_type": value_type}
    if include_default:
        spec["default"] = update.get("value")
    for key in ("description", "group", "min", "max", "step", "clamp", "editor"):
        if key in update:
            spec[key] = update[key]
    return spec


def graph_input_has_metadata(update: JsonMap) -> bool:
    """Return whether a graph input update carries editable metadata."""
    return any(key in update for key in ("description", "group", "min", "max", "step", "clamp", "editor"))


def set_node_control(node: NodeLike, node_id: str, update: JsonMap) -> JsonMap:
    """Set one node control."""
    control_id = required_string(update.get("id") or update.get("parameter_id"), "control id is required.")
    value = update.get("value")
    value_input = parameter_value_input(value)
    value_type = optional_string(update.get("value_type")) or infer_value_type(value_input)
    result = set_parameter_value(cast(ParameterNode, node), node_id, control_id, value, value_type)
    return {"id": control_id, "status": "updated", **result}


def set_property_control(
    owner_node: NestedGraphOwner,
    property_id: str,
    update: JsonMap,
    serialize_value: ValueSerializer,
    set_node_params: ParameterSetter,
) -> JsonMap:
    """Set one property-backed control."""
    control_id = required_string(update.get("id"), "control id is required.")
    value = update.get("value")
    value_input = parameter_value_input(value)
    value_type = optional_string(update.get("value_type")) or infer_value_type(value_input)

    if "." not in control_id:
        normalized_control_id = normalize_global_variable_reference(control_id)
        prop = input_property_from_id(cast(PropertyGraphOwner, owner_node), normalized_control_id)
        if prop is None:
            raise ValueError("Owner input '{}' not found for property '{}'.".format(control_id, property_id))
        old_value = property_value(owner_node, prop, serialize_value)
        owner_node.setInputPropertyValueFromId(normalized_control_id, sd_value_for(value_type, value))
        return {
            "id": normalized_control_id,
            "requested_id": control_id,
            "status": "updated",
            "old_value": old_value,
            "value": value,
            "value_type": value_type,
            "source": {"kind": "owner_input", "input_id": normalized_control_id},
        }

    nested_node_id, parameter_id = control_id.split(".", 1)
    nested_graph = owner_node.getPropertyGraph(find_node_property(owner_node, property_id))
    nested_node = graph_node_from_id(nested_graph, nested_node_id)
    if nested_node is None:
        raise ValueError("Property graph node '{}' not found.".format(nested_node_id))
    old_prop = property_from_id(cast(ValueOwner, nested_node), parameter_id, SDPropertyCategory.Input)
    old_value = property_value(cast(ValueOwner, nested_node), old_prop, serialize_value) if old_prop else None
    set_node_params(nested_node, {parameter_id: {"value": value, "type": value_type}})
    return {
        "id": control_id,
        "status": "updated",
        "old_value": old_value,
        "value": value,
        "value_type": value_type,
        "source": {
            "kind": "property_graph_parameter",
            "node_id": nested_node_id,
            "parameter_id": parameter_id,
        },
    }


def properties(owner: ValueOwner, category: int) -> list[HostProperty]:
    """Return owner properties for a category."""
    try:
        return list(owner.getProperties(category))
    except Exception:
        return []


def property_from_id(owner: ValueOwner, property_id: str, category: int) -> HostProperty | None:
    """Return one property by id."""
    for prop in properties(owner, category):
        if prop.getId() == property_id:
            return prop
    return None


def property_ids(owner: ValueOwner, category: int) -> list[str]:
    """Return property ids for diagnostics."""
    return [prop.getId() for prop in properties(owner, category)]


def property_info(prop: HostProperty) -> JsonMap:
    """Return property metadata."""
    return cast(JsonMap, get_property_info(cast(NodeHostProperty, prop)))


def property_value(owner: ValueOwner, prop: HostProperty | None, serialize_value: ValueSerializer) -> JsonValue:
    """Return serialized property value."""
    if prop is None:
        return None
    try:
        value = owner.getPropertyValue(prop)
        return serialize_value(value) if value is not None else None
    except Exception:
        return None


def adapter_value_type(sd_type: JsonValue, value: JsonValue) -> str:
    """Return adapter value type from SD type or serialized value."""
    if isinstance(sd_type, str) and sd_type:
        lowered = sd_type.lower()
        if lowered == "colorrgba":
            return "color"
        if lowered == "sdtypearray<sdtypeusage>":
            return "usage_array"
        return lowered
    try:
        return infer_value_type(parameter_value_input(value))
    except Exception:
        return "float"


def empty_constraints() -> JsonMap:
    """Return a stable empty constraints object."""
    return dict.fromkeys(CONSTRAINT_KEYS, None)


def property_constraints(metadata: JsonMap) -> JsonMap:
    """Return control constraints from property annotations."""
    constraints = empty_constraints()
    for key in CONSTRAINT_KEYS:
        if key in metadata:
            constraints[key] = metadata[key]
    return constraints


def control_metadata(metadata: JsonMap) -> JsonMap:
    """Return top-level control metadata fields backed by property annotations."""
    return {key: metadata[key] for key in ("description", *CONSTRAINT_KEYS) if key in metadata}


def property_annotations(owner: ValueOwner, prop: HostProperty, serialize_value: ValueSerializer) -> JsonMap:
    """Return supported property annotations exposed by the host."""
    metadata: JsonMap = {}
    for annotation_id in ("description", *CONSTRAINT_KEYS):
        found, value = property_annotation_value(owner, prop, annotation_id, serialize_value)
        if found:
            metadata[annotation_id] = value
    return metadata


def property_annotation_value(
    owner: ValueOwner,
    prop: HostProperty,
    annotation_id: str,
    serialize_value: ValueSerializer,
) -> tuple[bool, JsonValue]:
    """Read one property annotation using known host API spellings."""
    getter_specs = (
        (owner, "getPropertyAnnotationValueFromId", (prop, annotation_id)),
        (owner, "getPropertyAnnotationValueFromId", (prop.getId(), annotation_id)),
        (owner, "getPropertyAnnotationValue", (prop, annotation_id)),
        (owner, "getPropertyAnnotation", (prop, annotation_id)),
        (prop, "getAnnotationValueFromId", (annotation_id,)),
        (prop, "getAnnotationValue", (annotation_id,)),
        (prop, "getAnnotation", (annotation_id,)),
    )
    for target, method_name, args in getter_specs:
        try:
            getter = getattr(target, method_name)
        except Exception:
            continue
        if not callable(getter):
            continue
        try:
            raw_value = getter(*args)
        except Exception:
            continue
        if raw_value is None:
            continue
        return True, serialize_annotation_value(raw_value, serialize_value)
    return False, None


def serialize_annotation_value(value: ReprFallback, serialize_value: ValueSerializer) -> JsonValue:
    """Serialize an annotation value without stringifying JSON-native primitives."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, ValueGetter):
        try:
            raw_value = value.get()
        except Exception:
            raw_value = None
        if raw_value is None or isinstance(raw_value, (str, int, float, bool)):
            return raw_value
    return serialize_value(value)


def writable_by_api(owner: ReprFallback, method_name: str) -> bool:
    """Return whether a write method exists on the host object."""
    try:
        return callable(getattr(owner, method_name))
    except Exception:
        return False


def node_property_writable(node: ReprFallback, category_name: str) -> bool:
    """Return whether a node property category has a matching write method."""
    return writable_by_api(node, writable_source(category_name))


def writable_source(category_name: str) -> str:
    """Return the setter expected for a control category."""
    if category_name == "annotation":
        return "setAnnotationPropertyValueFromId"
    return "setInputPropertyValueFromId"


def graph_nodes(graph: NestedGraphLike) -> list[NodeLike]:
    """Return graph nodes."""
    try:
        return list(graph.getNodes())
    except Exception:
        return []


def graph_node_from_id(graph: NestedGraphLike | None, node_id: str) -> NodeLike | None:
    """Find one nested graph node by id."""
    if graph is None:
        return None
    for node in graph_nodes(graph):
        try:
            if node.getIdentifier() == node_id:
                return node
        except Exception:
            continue
    return None


def node_definition(node: NodeLike) -> str | None:
    """Return node definition id."""
    try:
        definition = node.getDefinition()
        return definition.getId() if definition is not None else None
    except Exception:
        return None


def property_has_connections(node: NodeLike, prop: HostProperty) -> bool:
    """Return whether a property has connections."""
    try:
        connections = node.getPropertyConnections(prop)
        return bool(list(connections) if connections is not None else [])
    except Exception:
        return False


def external_reference_id(value: JsonValue) -> str | None:
    """Return owner-input reference id for serialized # references."""
    if isinstance(value, str) and value.startswith("#") and len(value) > 1:
        return value[1:]
    if isinstance(value, dict) and isinstance(value.get("value"), str):
        raw = value["value"]
        if raw.startswith("#") and len(raw) > 1:
            return raw[1:]
    return None


def graph_identifier(graph: GraphLike) -> str | None:
    """Return graph identifier."""
    try:
        return graph.getIdentifier()
    except Exception:
        return None


def target_mapping(value: JsonValue) -> JsonMap:
    """Return a target mapping."""
    if not isinstance(value, dict):
        raise ValueError("target must be an object.")
    target = cast(JsonMap, dict(value))
    if not target.get("kind"):
        if target.get("property") or target.get("property_id"):
            target["kind"] = "node_property"
        elif target.get("node_id"):
            target["kind"] = "node"
        else:
            target["kind"] = "graph"
    return target


def list_mapping(value: JsonValue, label: str) -> list[JsonMap]:
    """Return a list of mappings."""
    if isinstance(value, dict):
        return [cast(JsonMap, value)]
    if not isinstance(value, list):
        raise ValueError("{} must be a list.".format(label))
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError("{}[{}] must be an object.".format(label, index))
        result.append(cast(JsonMap, item))
    return result


def required_string(value: JsonValue, message: str) -> str:
    """Return a non-empty string."""
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value


def optional_string(value: JsonValue) -> str | None:
    """Return optional text."""
    if value is None:
        return None
    if isinstance(value, int):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("value must be a string.")
    return value if value else None


def parameter_value_input(value: JsonValue) -> ParameterValueInput:
    """Return a narrowed parameter value input."""
    return value_input(value)


def preview_cache_path() -> str:
    """Return the preview cache directory."""
    import tempfile

    return os.path.join(tempfile.gettempdir(), "dcc_mcp_substancedesigner", "previews")
