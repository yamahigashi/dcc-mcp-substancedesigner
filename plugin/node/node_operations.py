"""Node mutation helpers for create, delete, move, and duplicate operations."""

from __future__ import annotations

from typing import cast

from sd.api.sdbasetypes import float2
from sd.api.sdvaluestring import SDValueString

from ..input_normalization import normalize_float2
from ..json_types import JsonMap, JsonValue
from ..library.library_nodes import ensure_standard_package_for_resource, resource_not_found_message
from ..library.library_types import LibraryPackageManager, LibraryResource
from ..parameters.sd_values import make_sd_value_usage_array
from .node_queries import get_node_def_id, get_node_pos, is_instance_node
from .node_types import MutableGraph, MutableNode, PositionInput, ResourcePackageManager


def host_string_value(value: str) -> SDValueString:
    """Create a host string value while hiding non-host fallback typing."""
    return cast(SDValueString, SDValueString.sNew(value))


def create_node(graph: MutableGraph, definition_id: str, position: PositionInput | None) -> JsonMap:
    """Create a regular node by definition id."""
    validate_node_definition(graph, definition_id)
    node = graph.newNode(definition_id)
    if not node:
        raise RuntimeError("newNode('{}') returned None.".format(definition_id))
    set_node_position(node, position)
    return {
        "node_id": node.getIdentifier(),
        "definition": get_node_def_id(node),
        "position": normalize_float2(position, "position") if position else [0.0, 0.0],
        "next_tools": preview_next_tools(node.getIdentifier()),
    }


def create_instance_node(
    graph: MutableGraph,
    package_manager: ResourcePackageManager,
    resource_url: str,
    position: PositionInput | None,
    package_hint: JsonValue = None,
) -> JsonMap:
    """Create a library instance node from a resource URL."""
    resource = find_resource(package_manager, resource_url)
    load_attempt: JsonValue = {}
    if resource is None:
        load_attempt = ensure_standard_package_for_resource(
            cast(LibraryPackageManager, package_manager),
            resource_url,
            package_hint,
        )
        resource = find_resource(package_manager, resource_url)
    if resource is None:
        raise ValueError(
            resource_not_found_message(cast(LibraryPackageManager, package_manager), resource_url, load_attempt)
        )
    node = graph.newInstanceNode(resource)
    if not node:
        raise RuntimeError("newInstanceNode failed for '{}'.".format(resource_url))
    set_node_position(node, position)
    return {
        "node_id": node.getIdentifier(),
        "resource_url": resource_url,
        "position": normalize_float2(position, "position") if position else [0.0, 0.0],
        "package_load": load_attempt,
        "note": "Call get_node_info to find exact port IDs before connecting.",
        "next_tools": preview_next_tools(node.getIdentifier()),
    }


def create_output_node(
    graph: MutableGraph,
    usage: str,
    position: PositionInput | None,
) -> JsonMap:
    """Create an output node and set common output annotations."""
    node = graph.newNode("sbs::compositing::output")
    if not node:
        raise RuntimeError("Failed to create output node.")
    set_node_position(node, position)
    annotation_results = set_output_annotations(node, usage)
    return {
        "node_id": node.getIdentifier(),
        "definition": "sbs::compositing::output",
        "usage": usage,
        "annotations_set": annotation_results,
        "next_tools": preview_next_tools(node.getIdentifier()),
    }


def delete_node(graph: MutableGraph, node: MutableNode, node_id: str) -> JsonMap:
    """Delete a node from a graph."""
    graph.deleteNode(node)
    return {"deleted": node_id}


def move_node(node: MutableNode, node_id: str, position: PositionInput) -> JsonMap:
    """Move a node to a position."""
    set_node_position(node, position)
    return {"node_id": node_id, "position": normalize_float2(position, "position")}


def set_node_position(node: MutableNode, position: PositionInput | None) -> None:
    """Set a node position when a two-value position is provided."""
    resolved = normalize_float2(position, "position") if position is not None else None
    if resolved is not None:
        node.setPosition(float2(resolved[0], resolved[1]))


def preview_next_tools(node_id: str) -> list[JsonMap]:
    """Return the follow-up preview action for newly created nodes."""
    return [
        {
            "tool": "substance_designer__get_preview",
            "public_name": "get_preview",
            "params": {"node_id": node_id},
            "reason": "Preview this node output before treating creation as complete.",
        }
    ]


def coordinate(value: JsonValue) -> float:
    """Return a JSON scalar coordinate."""
    if isinstance(value, (bool, int, float, str)):
        return float(value)
    raise ValueError("Position values must be scalar.")


def duplicate_node(graph: MutableGraph, node: MutableNode, node_id: str, offset: PositionInput | None) -> JsonMap:
    """Duplicate a regular node at an offset position."""
    if is_instance_node(node):
        raise ValueError(
            "Cannot duplicate library node '{}' via duplicate_node. "
            "Use create_instance_node with the same resource_url.".format(node_id)
        )
    definition_id = get_node_def_id(node)
    position = get_node_pos(node)
    resolved_offset = normalize_float2(offset, "offset") if offset is not None else [100.0, 0.0]
    if resolved_offset is None:
        resolved_offset = [100.0, 0.0]
    new_node = graph.newNode(definition_id)
    if not new_node:
        raise RuntimeError("Failed to duplicate node '{}'.".format(node_id))
    new_position = [position[0] + coordinate(resolved_offset[0]), position[1] + coordinate(resolved_offset[1])]
    set_node_position(new_node, new_position)
    return {
        "original_node_id": node_id,
        "new_node_id": new_node.getIdentifier(),
        "definition": definition_id,
        "position": new_position,
    }


def validate_node_definition(graph: MutableGraph, definition_id: str) -> None:
    """Reject unknown atomic node definitions before host creation."""
    try:
        known = {definition.getId() for definition in list(graph.getNodeDefinitions())}
        if definition_id not in known:
            raise ValueError(
                "Unknown definition '{}'. Library nodes require create_instance_node with pkg:// URL.".format(
                    definition_id
                )
            )
    except ValueError:
        raise
    except Exception:
        pass


def find_resource(package_manager: ResourcePackageManager, resource_url: str) -> LibraryResource | None:
    """Find a resource URL across host packages."""
    for package in list(package_manager.getPackages()):
        try:
            resource = package.findResourceFromUrl(resource_url)
            if resource is not None:
                return resource
        except Exception:
            pass
    return None


def set_output_annotations(node: MutableNode, usage: str) -> JsonMap:
    """Set output usage annotations on an output node."""
    annotation_results: JsonMap = {"label": set_annotation(node, "label", usage)}
    for annotation_id, annotation_value in (
        ("identifier", usage),
        ("usages", usage),
    ):
        annotation_results[annotation_id] = set_annotation(node, annotation_id, annotation_value)
    return annotation_results


def set_annotation(node: MutableNode, annotation_id: str, annotation_value: str) -> bool:
    """Set a single annotation value and return whether it succeeded."""
    try:
        value = (
            make_sd_value_usage_array(annotation_value)
            if annotation_id == "usages"
            else host_string_value(annotation_value)
        )
        node.setAnnotationPropertyValueFromId(annotation_id, value)
        return True
    except Exception:
        return False
