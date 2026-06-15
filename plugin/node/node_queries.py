"""Node identity, property serialization, and detail response helpers."""

from __future__ import annotations

from typing import Protocol, cast

from sd.api.sdproperty import SDPropertyCategory

from ..json_types import JsonScalar, JsonValue
from .node_types import (
    DetailConnection,
    DetailNode,
    HostConnection,
    HostDefinition,
    HostGetter,
    HostNode,
    HostProperty,
    InstanceRef,
    NestedGraphRef,
    NodeDetail,
    NodePropertyInfo,
    PropertyInfo,
    ReprFallback,
    ValueSerializer,
)


def get_node_detail(
    node_id: str,
    node: DetailNode,
    system_params: frozenset[str],
    serialize_value: ValueSerializer,
) -> NodeDetail:
    """Return the full host-side node detail payload."""
    is_library = is_instance_node(node)
    return {
        "node_id": node_id,
        "definition": get_node_def_id(node),
        "is_library_node": is_library,
        "instance": get_instance_ref(node),
        "position": get_node_pos(node),
        "inputs": input_property_details(node, system_params, serialize_value),
        "outputs": output_property_details(node),
        "annotations": annotation_property_details(node, serialize_value),
        "nested_graph_refs": get_nested_graph_refs(node),
        "note": ("Library node: use output IDs listed above, NOT 'unique_filter_output'" if is_library else ""),
    }


def inspect_node(
    *,
    graph: InspectableGraph,
    package_manager: InspectablePackageManager,
    existing_node: DetailNode | None = None,
    node_id: str | None = None,
    definition_id: str | None = None,
    resource_url: str | None = None,
    property_id: str | None = None,
    system_params: frozenset[str],
    serialize_value: ValueSerializer,
) -> NodeDetail:
    """Inspect an existing node or a temporary node created from a definition/resource."""
    target_count = sum(bool(value) for value in (node_id, definition_id, resource_url))
    if target_count != 1:
        raise ValueError("inspect_node requires exactly one of node_id, definition_id, or resource_url.")
    node = None
    temporary = False
    target: dict[str, JsonValue] = {}
    try:
        if node_id:
            if existing_node is None:
                raise ValueError("existing node '{}' was not resolved.".format(node_id))
            node = existing_node
            target = {"kind": "existing_node", "node_id": node_id}
        elif definition_id:
            validate_runtime_node_definition(graph, definition_id)
            node = graph.newNode(definition_id)
            temporary = True
            target = {"kind": "atomic", "definition_id": definition_id}
        else:
            resource = find_runtime_resource(package_manager, str(resource_url))
            if resource is None:
                raise ValueError("Resource '{}' is not loaded or could not be found.".format(resource_url))
            node = graph.newInstanceNode(resource)
            temporary = True
            target = {"kind": "library", "resource_url": str(resource_url)}
        if node is None:
            raise RuntimeError("Node resolution failed for inspect_node.")
        detail = get_node_detail(node.getIdentifier(), node, system_params, serialize_value)
        return {
            "target": target,
            "node_id": node.getIdentifier(),
            "temporary_node_id": node.getIdentifier() if temporary else None,
            "definition": detail.get("definition"),
            "is_library_node": detail.get("is_library_node", False),
            "instance": detail.get("instance"),
            "inputs": detail.get("inputs", []),
            "outputs": detail.get("outputs", []),
            "annotations": detail.get("annotations", []),
            "nested_graph_refs": detail.get("nested_graph_refs", []),
            "property_context": property_context_notice(property_id, detail.get("nested_graph_refs", [])),
        }
    finally:
        if temporary and node is not None:
            graph.deleteNode(node)


def find_runtime_resource(package_manager: InspectablePackageManager, resource_url: str) -> InspectableResource | None:
    """Find a package resource by URL for temporary instance-node inspection."""
    try:
        packages = list(package_manager.getPackages())
    except Exception:
        packages = []
    for package in packages:
        try:
            resource = package.findResourceFromUrl(resource_url)
            if resource is not None:
                return resource
        except Exception:
            pass
    return None


def property_context_notice(property_id: str | None, nested_graph_refs: JsonValue) -> JsonValue:
    """Return an explicit notice for property-backed context data."""
    if not property_id:
        return None
    exists = False
    if isinstance(nested_graph_refs, list):
        exists = any(isinstance(ref, dict) and ref.get("property") == property_id for ref in nested_graph_refs)
    return {
        "property_id": property_id,
        "nested_graph_ref_exists": exists,
        "available": False,
        "reason": "Function Graph property-context resources are not packaged yet.",
        "guidance": "Do not invent reserved variable names; verify them through existing graphs, saved XML, or live API evidence before editing.",
    }


def validate_runtime_node_definition(graph: InspectableGraph, definition_id: str) -> None:
    """Reject unknown node definitions before temporary host creation when possible."""
    try:
        known = {definition.getId() for definition in list(graph.getNodeDefinitions())}
        if definition_id not in known:
            raise ValueError("Unknown definition '{}'.".format(definition_id))
    except ValueError:
        raise
    except Exception:
        pass


class InspectableResource(Protocol):
    """Protocol for resources that can be used to create instance nodes."""


class InspectablePackage(Protocol):
    """Protocol for package resource lookup."""

    def findResourceFromUrl(self, url: str) -> InspectableResource | None:
        """Find a resource by URL."""
        ...


class InspectablePackageManager(Protocol):
    """Protocol for package managers used by runtime inspection."""

    def getPackages(self) -> list[InspectablePackage]:
        """Return loaded packages."""
        ...


class InspectableGraph(Protocol):
    """Protocol for temporary node inspection."""

    def getNodeDefinitions(self) -> list[HostDefinition]:
        """Return available built-in definitions."""
        ...

    def newNode(self, definition_id: str) -> DetailNode | None:
        """Create a built-in node."""
        ...

    def newInstanceNode(self, resource: InspectableResource) -> DetailNode | None:
        """Create an instance node."""
        ...

    def deleteNode(self, node: DetailNode) -> None:
        """Delete a node."""
        ...


def get_node_pos(node: HostNode) -> list[float]:
    """Return a node position as ``[x, y]``."""
    try:
        position = node.getPosition()
        return [position.x, position.y]
    except Exception:
        return [0.0, 0.0]


def get_node_def_id(node: HostNode) -> str:
    """Return the node definition identifier or ``unknown``."""
    try:
        definition = node.getDefinition()
        if definition is not None:
            return definition.getId()
    except Exception:
        pass
    return "unknown"


def is_instance_node(node: HostNode) -> bool:
    """Return whether a node appears to be a package-backed instance."""
    definition_id = get_node_def_id(node)
    return definition_id == "unknown" or definition_id.startswith("pkg://") or "?dependency=" in definition_id


def get_instance_ref(node: HostNode) -> InstanceRef | None:
    """Return package-instance reference details for a node."""
    definition_id = get_node_def_id(node)
    if not is_instance_node(node):
        return None
    ref: InstanceRef = {"definition": definition_id}
    try:
        resource = node.getReferencedResource()
        if resource is not None:
            try:
                ref["graph"] = resource.getIdentifier()
            except Exception:
                pass
            try:
                ref["resource_url"] = resource.getUrl()
            except Exception:
                pass
    except Exception:
        pass
    try:
        package = node.getPackage()
        if package is not None:
            try:
                ref["package"] = package.getFilePath()
            except Exception:
                pass
    except Exception:
        pass
    if "resource_url" not in ref and definition_id.startswith("pkg://"):
        ref["resource_url"] = definition_id
    if "graph" not in ref and definition_id.startswith("pkg://"):
        ref["graph"] = definition_id.rsplit("/", 1)[-1].split("?", 1)[0]
    return ref


def input_property_details(
    node: DetailNode,
    system_params: frozenset[str],
    serialize_value: ValueSerializer,
) -> list[JsonValue]:
    """Return serialized input property details for a node."""
    details: list[JsonValue] = []
    for prop in node_properties(node, SDPropertyCategory.Input):
        property_id = prop.getId()
        if property_id in system_params:
            continue
        info = property_detail(node, prop, serialize_value)
        add_connection_details(info, node, prop)
        details.append(info)
    return details


def output_property_details(node: DetailNode) -> list[JsonValue]:
    """Return serialized output property details for a node."""
    return [property_info_json(prop) for prop in node_properties(node, SDPropertyCategory.Output)]


def annotation_property_details(node: DetailNode, serialize_value: ValueSerializer) -> list[JsonValue]:
    """Return serialized annotation property details for a node."""
    return [
        property_detail(node, prop, serialize_value) for prop in node_properties(node, SDPropertyCategory.Annotation)
    ]


def node_properties(node: DetailNode, category: int) -> list[HostProperty]:
    """Return node properties for a category."""
    try:
        return list(node.getProperties(category))
    except Exception:
        return []


def get_property_info(prop: HostProperty) -> PropertyInfo:
    """Return serializable metadata for a host property."""
    info: PropertyInfo = {"id": prop.getId()}
    for key, method_name in (
        ("uid", "getUid"),
        ("uid", "getUID"),
        ("label", "getLabel"),
        ("identifier", "getIdentifier"),
    ):
        try:
            value_getter = cast(HostGetter, getattr(prop, method_name))
            value = value_getter()
            if value is not None and key not in info:
                info[key] = value
        except Exception:
            pass
    try:
        prop_type = prop.getType()
        if prop_type is not None:
            try:
                info["type"] = prop_type.getId()
            except Exception:
                info["type"] = str(prop_type)
    except Exception:
        pass
    return info


def property_detail(node: "DetailValueNode", prop: HostProperty, serialize_value: ValueSerializer) -> NodePropertyInfo:
    """Return property metadata with best-effort value serialization."""
    info = property_info_json(prop)
    try:
        value = node.getPropertyValue(prop)
        if value is not None:
            info["value"] = serialize_value(value)
    except Exception:
        pass
    return info


def property_info_json(prop: HostProperty) -> NodePropertyInfo:
    """Return property metadata widened to JSON value types."""
    return dict(get_property_info(prop))


def get_connection_ref_output(conn: HostConnection) -> JsonScalar:
    """Return a connection reference output identifier when available."""
    for method_name in (
        "getConnRefOutput",
        "getConnectionRefOutput",
        "getRefOutput",
        "getOutputPropertyId",
    ):
        try:
            value_getter = cast(HostGetter, getattr(conn, method_name))
            value = value_getter()
            if value is not None:
                return value
        except Exception:
            pass
    return None


def add_connection_details(info: NodePropertyInfo, node: DetailNode, prop: HostProperty) -> None:
    """Add connection details to an input property mapping."""
    connections = property_connections(node, prop)
    if not connections:
        return
    connected_from: list[JsonValue] = []
    connection_details: list[JsonValue] = []
    for conn in connections:
        try:
            source_node = conn.getInputPropertyNode()
            source_property = conn.getInputProperty()
            if source_node is None or source_property is None:
                continue
            connected_from.append("{}.{}".format(source_node.getIdentifier(), source_property.getId()))
            connected: NodePropertyInfo = {
                "node": source_node.getIdentifier(),
                "output": source_property.getId(),
                "output_uid": get_property_info(source_property).get("uid"),
            }
            conn_ref_output = get_connection_ref_output(conn)
            if conn_ref_output is not None:
                connected["connRefOutput"] = conn_ref_output
            connection_details.append(connected)
        except Exception:
            pass
    if connected_from:
        info["connected_from"] = connected_from
        info["connections"] = connection_details


def property_connections(node: DetailNode, prop: HostProperty) -> list[DetailConnection]:
    """Return property connections for a node property."""
    try:
        connections = node.getPropertyConnections(prop)
        return list(connections) if connections is not None else []
    except Exception:
        return []


def get_nested_graph_refs(node: HostNode) -> list[NestedGraphRef]:
    """Return nested graph references exposed by a node."""
    refs: list[NestedGraphRef] = []
    for category in (SDPropertyCategory.Input, SDPropertyCategory.Annotation):
        try:
            props = list(node.getProperties(category))
        except Exception:
            props = []
        for prop in props:
            try:
                nested = node.getPropertyGraph(prop)
            except Exception:
                continue
            if nested is None:
                continue
            graph_type: str | None = None
            try:
                graph_type = nested.getClassName()
            except Exception:
                pass
            refs.append(
                {
                    "property": prop.getId(),
                    "graph_type": graph_type,
                    "exists": True,
                }
            )
    fx_ref = fx_map_graph_ref(node)
    if fx_ref is not None:
        refs.append(fx_ref)
    return refs


def fx_map_graph_ref(node: HostNode) -> NestedGraphRef | None:
    """Return an FX-Map referenced graph ref when the host exposes one."""
    try:
        resource = node.getReferencedResource()
    except Exception:
        return None
    if resource is None:
        return None
    try:
        class_name = resource.getClassName()
    except Exception:
        return None
    if class_name != "SDSBSFxMapGraph":
        return None
    return {
        "kind": "fx_map_graph",
        "graph_type": "SDSBSFxMapGraph",
        "exists": True,
    }


class DetailValueNode(Protocol):
    """Protocol for nodes that can expose property values."""

    def getPropertyValue(self, prop: HostProperty) -> ReprFallback | None:
        """Return a property value."""
        ...
