"""Node preview rendering orchestration for the host plugin."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Protocol, cast

from ..graph.graph_queries import get_graph_package_path
from ..json_types import JsonMap, JsonValue
from ..node.node_catalog import SYSTEM_PARAMS
from ..sd_serialization import serialize_sd_value
from .preview_outputs import (
    find_node_output_property,
    import_image_modules,
    normalize_preview_image_size,
    require_texture_output_property,
    save_node_preview_texture,
    save_node_preview_via_temporary_output,
)
from .preview_types import (
    HashPreviewNode,
    NodeDefinitionReader,
    NodeWithDefinition,
    OutputProperty,
    PreviewCache,
    PreviewGraph,
    PreviewHashEntry,
    PreviewInputEntry,
    PreviewPropertyGraph,
    PropertyGraphPreviewNode,
    RenderGraph,
    RenderNode,
    ReprFallback,
    SDPropertyCategory,
    ValueSerializer,
)

RESOLUTION_SIZES: dict[str, int] = {
    "small": 256,
    "medium": 512,
    "large": 1024,
}


class OutputNodeCollection(Protocol):
    """Host collection of preview output nodes."""

    def getSize(self) -> int:
        """Return collection size."""
        ...

    def getItem(self, index: int) -> ReprFallback | None:
        """Return collection item."""
        ...


def render_node_preview(
    graph: RenderGraph,
    node: RenderNode,
    node_id: str,
    node_output_id: str | None,
    channel: str,
    resolution: str,
    timeout_ms: int,
    preview_cache: PreviewCache,
    qt_binding: str | None,
) -> JsonMap:
    """Render or return a cached PNG preview payload for a node output."""
    size = preview_size(resolution)
    if int(timeout_ms) <= 0:
        raise ValueError("timeout_ms must be > 0")

    started = time.time()
    output_prop = find_node_output_property(node, node_output_id)
    require_texture_output_property(node, output_prop)
    output_id = output_prop.getId()
    graph_id = graph.getIdentifier()
    package_path = get_graph_package_path(graph)

    parameters_hash = hash_node_preview(
        graph,
        node,
        output_id,
        node_definition_id,
        serialize_sd_value,
        SYSTEM_PARAMS,
    )
    cache_key = make_preview_cache_key(
        {
            "graph_id": graph_id,
            "package_path": package_path,
            "node_id": node_id,
            "node_output_id": output_id,
            "channel": channel,
            "resolution": resolution,
            "parameters_hash": parameters_hash,
        }
    )

    cached = preview_cache.get(cache_key)
    if cached and cached_preview_exists(cached):
        image_path = string_field(cached, "image_path")
        normalize_preview_image_size(image_path, size, size, qt_binding)
        payload = dict(cached)
        payload["cached"] = True
        payload["render_ms"] = 0
        return payload

    image_path = preview_image_path(cache_key)
    render_preview_image(graph, node, output_prop, output_id, image_path, node_id, size, qt_binding)
    preview_stats = preview_image_stats(image_path, qt_binding)
    diagnostics = preview_diagnostics(preview_stats)

    render_ms = int((time.time() - started) * 1000)
    if render_ms > int(timeout_ms):
        raise RuntimeError("Node preview render exceeded timeout_ms: {}ms > {}ms".format(render_ms, int(timeout_ms)))

    payload: JsonMap = {
        "preview_type": "node_output",
        "image_path": image_path,
        "width": size,
        "height": size,
        "graph_id": graph_id,
        "graph_identifier": graph_id,
        "package_path": package_path,
        "node_id": node_id,
        "node_output_id": output_id,
        "channel": channel,
        "resolution": resolution,
        "render_ms": render_ms,
        "cached": False,
        "parameters_hash": parameters_hash,
        "preview_stats": preview_stats,
        "diagnostics": diagnostics,
    }
    preview_cache[cache_key] = dict(payload)
    return payload


def preview_size(resolution: str) -> int:
    """Return the pixel size for a named preview resolution."""
    if resolution not in RESOLUTION_SIZES:
        raise ValueError("resolution must be one of: {}".format(", ".join(sorted(RESOLUTION_SIZES.keys()))))
    return RESOLUTION_SIZES[resolution]


def cached_preview_exists(payload: JsonMap) -> bool:
    """Return whether a cached preview payload points to an existing image."""
    image_path = payload.get("image_path")
    return isinstance(image_path, str) and os.path.exists(image_path)


def preview_image_path(cache_key: str) -> str:
    """Return the target image path for a preview cache key."""
    output_dir = os.path.join(tempfile.gettempdir(), "dcc_mcp_substancedesigner", "previews")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return os.path.join(output_dir, "{}.png".format(cache_key))


def preview_image_stats(image_path: str, qt_binding: str | None) -> JsonMap:
    """Return simple brightness stats for a saved preview image."""
    modules = import_image_modules(qt_binding)
    if modules is None:
        return {}
    qtgui, _qtcore = modules
    image = qtgui.QImage(image_path)
    if image.isNull() or not hasattr(image, "pixelColor"):
        return {}

    width = int(image.width())
    height = int(image.height())
    if width <= 0 or height <= 0:
        return {}

    total = 0.0
    minimum = 255
    maximum = 0
    nonzero = 0
    count = width * height
    for y in range(height):
        for x in range(width):
            color = image.pixelColor(x, y)
            value = int((color.red() + color.green() + color.blue()) / 3)
            total += value
            minimum = min(minimum, value)
            maximum = max(maximum, value)
            if value > 0:
                nonzero += 1

    return {
        "mean": total / count,
        "min": minimum,
        "max": maximum,
        "range": maximum - minimum,
        "nonzero_ratio": nonzero / count,
    }


def preview_diagnostics(stats: JsonMap) -> list[JsonMap]:
    """Warn for previews that are effectively black and flat."""
    mean = stats.get("mean")
    value_range = stats.get("range")
    if isinstance(mean, (int, float)) and isinstance(value_range, (int, float)) and mean <= 5 and value_range <= 5:
        return [
            {
                "severity": "warning",
                "stage": "preview_analysis",
                "code": "near_black_solid_preview",
                "message": "Preview is nearly black and low-contrast; verify the node/output before continuing.",
            }
        ]
    return []


def string_field(payload: JsonMap, key: str) -> str:
    """Return a string field from a payload."""
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise ValueError("Preview payload field '{}' must be a string.".format(key))


def make_preview_cache_key(parts: dict[str, JsonValue]) -> str:
    """Return a deterministic cache key for preview request metadata."""
    serialized = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_node_preview(
    graph: PreviewGraph,
    node: HashPreviewNode,
    output_id: str,
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
    system_params: frozenset[str],
) -> str:
    """Return a deterministic hash for a node preview's upstream state."""
    visited: set[str] = set()
    stack: list[tuple[HashPreviewNode, str]] = [(node, output_id)]
    upstream: list[PreviewHashEntry] = []
    while stack:
        current, current_output = stack.pop()
        try:
            current_id = current.getIdentifier()
        except Exception:
            continue
        if current_id in visited:
            continue
        visited.add(current_id)
        entry: PreviewHashEntry = {
            "node_id": current_id,
            "definition": read_node_definition(current),
            "output": current_output,
            "inputs": [],
        }
        referenced_graph = referenced_graph_entry(current, read_node_definition, serialize_value)
        if referenced_graph is not None:
            entry["referenced_graph"] = referenced_graph
        for input_entry in preview_input_entries(
            current,
            stack,
            read_node_definition,
            serialize_value,
            system_params,
        ):
            entry_inputs = entry["inputs"]
            if isinstance(entry_inputs, list):
                entry_inputs.append(input_entry)
        upstream.append(entry)

    serialized = json.dumps(
        {
            "graph": graph.getIdentifier(),
            "graph_inputs": graph_input_entries(graph, serialize_value),
            "target": node.getIdentifier(),
            "target_output": output_id,
            "upstream": sorted(upstream, key=lambda item: str(item["node_id"])),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def graph_input_entries(graph: PreviewGraph, serialize_value: ValueSerializer) -> list[PreviewInputEntry]:
    """Return serialized hash entries for graph input properties."""
    try:
        input_props = list(graph.getProperties(SDPropertyCategory.Input))
    except BaseException:
        input_props = []
    entries: list[PreviewInputEntry] = []
    for prop in input_props:
        try:
            prop_id = prop.getId()
        except BaseException:
            continue
        try:
            value = graph.getPropertyValue(prop)
            serialized_value: JsonValue = serialize_value(value) if value is not None else None
        except BaseException:
            serialized_value = None
        entries.append({"id": prop_id, "value": serialized_value})
    return sorted(entries, key=lambda item: str(item["id"]))


def preview_input_entries(
    node: HashPreviewNode,
    stack: list[tuple[HashPreviewNode, str]],
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
    system_params: frozenset[str],
) -> list[PreviewInputEntry]:
    """Return serialized hash entries for a node's input properties."""
    try:
        input_props = list(node.getProperties(SDPropertyCategory.Input))
    except BaseException:
        input_props = []
    entries: list[PreviewInputEntry] = []
    for prop in input_props:
        try:
            prop_id = prop.getId()
        except BaseException:
            continue
        property_graph = property_graph_entry(node, prop, prop_id, read_node_definition, serialize_value)
        conn_entries = connection_entries(node, prop, prop_id, stack)
        if conn_entries:
            entry: PreviewInputEntry = {"id": prop_id, "connections": conn_entries}
            if property_graph is not None:
                entry["property_graph"] = property_graph
            entries.append(entry)
            continue
        try:
            value = node.getPropertyValue(prop)
            serialized_value: JsonValue = serialize_value(value) if value is not None else None
        except BaseException:
            serialized_value = None
        entry = {"id": prop_id, "value": serialized_value}
        if property_graph is not None:
            entry["property_graph"] = property_graph
        entries.append(entry)
    return entries


def connection_entries(
    node: HashPreviewNode,
    prop: OutputProperty,
    prop_id: str,
    stack: list[tuple[HashPreviewNode, str]],
) -> list[PreviewInputEntry]:
    """Return serialized connection entries for a property and extend traversal stack."""
    try:
        conns = node.getPropertyConnections(prop)
    except BaseException:
        conns = None
    conn_list = list(conns) if conns is not None else []
    entries: list[PreviewInputEntry] = []
    for conn in conn_list:
        try:
            source_node = conn.getInputPropertyNode()
            source_prop = conn.getInputProperty()
            if source_node and source_prop:
                source_output = source_prop.getId()
                entries.append(
                    {
                        "from_node": source_node.getIdentifier(),
                        "from_output": source_output,
                        "to_input": prop_id,
                    }
                )
                stack.append((source_node, source_output))
        except BaseException:
            pass
    return entries


def property_graph_entry(
    node: HashPreviewNode,
    prop: OutputProperty,
    prop_id: str,
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
) -> PreviewInputEntry | None:
    """Return one property graph hash entry when a node property owns a nested graph."""
    try:
        nested_graph = cast(PropertyGraphPreviewNode, node).getPropertyGraph(prop)
    except BaseException:
        return None
    if nested_graph is None:
        return None
    return {
        "id": prop_id,
        "graph": serialize_property_graph(nested_graph, read_node_definition, serialize_value),
    }


def referenced_graph_entry(
    node: HashPreviewNode,
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
) -> JsonValue | None:
    """Return a node-referenced resource graph hash entry, such as FX-Map graphs."""
    try:
        getter = getattr(node, "getReferencedResource", None)
    except BaseException:
        return None
    if not callable(getter):
        return None
    try:
        referenced = getter()
    except BaseException:
        return None
    if referenced is None or not hasattr(referenced, "getNodes"):
        return None
    return serialize_property_graph(cast(PreviewPropertyGraph, referenced), read_node_definition, serialize_value)


def serialize_property_graph(
    nested_graph: PreviewPropertyGraph,
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
) -> JsonValue:
    """Serialize property graph structure for preview cache hashing."""
    nested_nodes = property_graph_nodes(nested_graph)
    connections: list[JsonValue] = []
    nodes: list[JsonValue] = []
    for nested_node in nested_nodes:
        try:
            nested_node_id = nested_node.getIdentifier()
        except BaseException:
            continue
        nodes.append(
            {
                "id": nested_node_id,
                "definition": read_node_definition(nested_node),
                "inputs": property_graph_node_inputs(nested_node, read_node_definition, serialize_value, connections),
            }
        )
    return {
        "nodes": sorted(nodes, key=lambda item: str(item["id"]) if isinstance(item, dict) else ""),
        "connections": sorted(
            connections,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
        ),
        "output": property_graph_output(nested_graph),
    }


def property_graph_nodes(nested_graph: PreviewPropertyGraph) -> list[HashPreviewNode]:
    """Return nested graph nodes, tolerating host API failures."""
    try:
        return list(nested_graph.getNodes())
    except BaseException:
        return []


def property_graph_node_inputs(
    nested_node: HashPreviewNode,
    read_node_definition: NodeDefinitionReader,
    serialize_value: ValueSerializer,
    connections: list[JsonValue],
) -> list[PreviewInputEntry]:
    """Return nested graph node input values and append nested connections."""
    try:
        input_props = list(nested_node.getProperties(SDPropertyCategory.Input))
    except BaseException:
        input_props = []
    entries: list[PreviewInputEntry] = []
    for input_prop in input_props:
        try:
            input_id = input_prop.getId()
        except BaseException:
            continue
        conn_entries = nested_connection_entries(nested_node, input_prop, input_id)
        property_graph = property_graph_entry(nested_node, input_prop, input_id, read_node_definition, serialize_value)
        if conn_entries:
            connection_entry: PreviewInputEntry = {"id": input_id, "connections": conn_entries}
            if property_graph is not None:
                connection_entry["property_graph"] = property_graph
            connections.extend(conn_entries)
            entries.append(connection_entry)
            continue
        try:
            value = nested_node.getPropertyValue(input_prop)
            serialized_value: JsonValue = serialize_value(value) if value is not None else None
        except BaseException:
            serialized_value = None
        entry: PreviewInputEntry = {"id": input_id, "value": serialized_value}
        if property_graph is not None:
            entry["property_graph"] = property_graph
        entries.append(entry)
    return sorted(entries, key=lambda item: str(item["id"]))


def nested_connection_entries(
    nested_node: HashPreviewNode,
    input_prop: OutputProperty,
    input_id: str,
) -> list[PreviewInputEntry]:
    """Return nested graph connection entries for one nested node input."""
    try:
        conns = nested_node.getPropertyConnections(input_prop)
    except BaseException:
        conns = None
    entries: list[PreviewInputEntry] = []
    for conn in list(conns) if conns is not None else []:
        try:
            source_node = conn.getInputPropertyNode()
            source_prop = conn.getInputProperty()
            if source_node and source_prop:
                entries.append(
                    {
                        "from": source_node.getIdentifier(),
                        "from_output": source_prop.getId(),
                        "to": nested_node.getIdentifier(),
                        "to_input": input_id,
                    }
                )
        except BaseException:
            pass
    return entries


def property_graph_output(nested_graph: PreviewPropertyGraph) -> JsonValue:
    """Return property graph output node ids using host API fallbacks."""
    for method_name in ("getOutputNodes", "getOutputNode"):
        try:
            method = getattr(nested_graph, method_name)
            output_value = method()
        except BaseException:
            continue
        output_nodes = output_node_list(output_value)
        if output_nodes:
            return [{"node": node.getIdentifier()} for node in output_nodes]
    return None


def output_node_list(value: ReprFallback | list[ReprFallback] | None) -> list[HashPreviewNode]:
    """Return output nodes from common SD API collection shapes."""
    if value is None:
        return []
    if isinstance(value, list):
        return [cast(HashPreviewNode, node) for node in value if has_identifier(node)]
    if has_identifier(value):
        return [cast(HashPreviewNode, value)]
    try:
        collection = cast(OutputNodeCollection, value)
        size = collection.getSize()
        return [
            cast(HashPreviewNode, item) for index in range(size) if has_identifier(item := collection.getItem(index))
        ]
    except BaseException:
        return []


def has_identifier(value: ReprFallback | None) -> bool:
    """Return whether a value looks like a node with an identifier."""
    return callable(getattr(value, "getIdentifier", None))


def node_definition_id(node: HashPreviewNode) -> str:
    """Return a node definition identifier for preview hashing."""
    try:
        definition = cast(NodeWithDefinition, node).getDefinition()
        if definition is not None:
            return definition.getId()
    except Exception:
        pass
    return "unknown"


def render_preview_image(
    graph: RenderGraph,
    node: RenderNode,
    output_prop: OutputProperty,
    output_id: str,
    image_path: str,
    node_id: str,
    size: int,
    qt_binding: str | None,
) -> None:
    """Compute and save a preview image to disk."""
    graph.compute()
    value = node.getPropertyValue(output_prop)
    if value is None:
        save_node_preview_via_temporary_output(graph, node, output_id, image_path)
    else:
        save_node_preview_texture(value, image_path, node_id, output_id)
    if not os.path.exists(image_path):
        raise RuntimeError("Node preview PNG was not created: {}".format(image_path))
    normalize_preview_image_size(image_path, size, size, qt_binding)
