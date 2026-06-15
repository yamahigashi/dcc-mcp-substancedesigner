"""Normalized MCP-facing schemas for Substance Designer data."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from dcc_mcp_substancedesigner.authoring_reference import tool_hint
from dcc_mcp_substancedesigner.semantic_graph import enrich_node_detail


def normalize_scene_info(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize plugin scene information into the stable MCP surface."""
    packages = normalize_packages(raw)["packages"]
    graphs = [graph for package in packages for graph in package["graphs"]]
    return {
        "application": {
            "name": "Substance 3D Designer",
            "version": raw.get("sd_version"),
            "plugin_version": raw.get("plugin_version"),
        },
        "current_graph": raw.get("current_graph"),
        "current_graph_node_count": _int(raw.get("current_graph_node_count")),
        "package_count": len(packages),
        "graph_count": len(graphs),
        "packages": packages,
    }


def normalize_packages(raw: Dict[str, Any], *, package_path: Optional[str] = None) -> Dict[str, Any]:
    """Normalize package and graph inventory for get_scene."""
    packages = []
    for index, package in enumerate(_list(raw.get("packages"))):
        file_path = package.get("file_path")
        if package_path and file_path != package_path:
            continue
        graphs = []
        for graph_index, graph in enumerate(_list(package.get("graphs"))):
            if graph.get("identifier") is None:
                continue
            graphs.append(
                {
                    "identifier": graph.get("identifier"),
                    "type": graph.get("type"),
                    "node_count": _int(graph.get("node_count")),
                    "index": graph_index,
                }
            )
        packages.append(
            {
                "index": index,
                "file_path": file_path,
                "is_saved": bool(file_path),
                "graphs": graphs,
                "graph_count": len(graphs),
                **({"error": package["error"]} if package.get("error") else {}),
            }
        )
    return {"packages": packages, "package_count": len(packages)}


def normalize_graph_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a graph summary returned by get_graph_info."""
    nodes = [_normalize_graph_node(node) for node in _list(raw.get("nodes"))]
    connections = _graph_connections(nodes)
    return {
        "identifier": raw.get("identifier"),
        "package_path": raw.get("package_path"),
        "node_count": _int(raw.get("node_count")),
        "nodes": nodes,
        "connections": connections,
        "canonical_connections": [_canonical_connection(edge) for edge in connections],
        "connection_count": len(connections),
        "returned_node_count": len(nodes),
        "truncated": _bool(raw.get("truncated")),
        "node_limit": _int(raw.get("node_limit")),
    }


def normalize_node_list(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize graph nodes into a list-only response."""
    summary = normalize_graph_summary(raw)
    return {
        "graph_identifier": summary["identifier"],
        "node_count": summary["node_count"],
        "nodes": summary["nodes"],
        "returned_node_count": summary["returned_node_count"],
        "truncated": summary["truncated"],
        "node_limit": summary["node_limit"],
    }


def normalize_node_detail(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize detailed node inspection data."""
    node_id = raw.get("node_id")
    graph_identifier = raw.get("graph_identifier")
    normalized = {
        "node_id": node_id,
        "graph_identifier": graph_identifier,
        "resolved_graph_identifier": raw.get("resolved_graph_identifier") or graph_identifier,
        "definition": raw.get("definition"),
        "is_library_node": bool(raw.get("is_library_node")),
        "position": _position(raw.get("position")),
        "inputs": [_normalize_port(port) for port in _list(raw.get("inputs"))],
        "outputs": [_normalize_port(port) for port in _list(raw.get("outputs"))],
        "annotations": [_normalize_port(port) for port in _list(raw.get("annotations"))],
        "nested_graph_refs": [
            _normalize_nested_graph_ref(ref, node_id=node_id, graph_identifier=graph_identifier)
            for ref in _list(raw.get("nested_graph_refs"))
        ],
        "instance": raw.get("instance") if isinstance(raw.get("instance"), dict) else None,
        "diagnostics": _list(raw.get("diagnostics")),
        "note": raw.get("note") or "",
    }
    return enrich_node_detail(normalized)


def normalize_operation_result(operation: str, raw: Any) -> Dict[str, Any]:
    """Normalize mutation/utility command responses into a common envelope."""
    result = raw if isinstance(raw, dict) else {"value": raw}
    return {
        "operation": operation,
        "ok": True,
        "result": result,
    }


def _normalize_graph_node(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "identifier": raw.get("identifier"),
        "definition": raw.get("definition"),
        "position": _position(raw.get("position")),
        "connections": [_normalize_connection(conn) for conn in _list(raw.get("connections"))],
        "annotations": [_normalize_port(port) for port in _list(raw.get("annotations"))],
    }


def _normalize_connection(raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {
        "input": raw.get("input"),
        "from_node": raw.get("from_node"),
        "from_output": raw.get("from_output"),
    }
    normalized.update(_connection_optional_fields(raw))
    return normalized


def _graph_connections(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    connections = []
    for node in nodes:
        to_node = node.get("identifier")
        for conn in node.get("connections", []):
            if not isinstance(conn, dict):
                continue
            connections.append(
                {
                    "from_node": conn.get("from_node"),
                    "from_output": conn.get("from_output"),
                    "to_node": to_node,
                    "to_input": conn.get("input"),
                    **_connection_optional_fields(conn),
                }
            )
    return connections


def _canonical_connection(edge: Dict[str, Any]) -> Dict[str, Any]:
    source = {
        "node": edge.get("from_node"),
        "output": edge.get("from_output"),
        **_compact(
            {
                "output_uid": edge.get("from_output_uid")
                or edge.get("source_output_uid")
                or edge.get("connRefOutput")
                or edge.get("conn_ref_output")
            }
        ),
    }
    target = {
        "node": edge.get("to_node"),
        "input": edge.get("to_input"),
        **_compact({"input_uid": edge.get("to_input_uid") or edge.get("destination_input_uid")}),
    }
    return {"from": source, "to": target}


def _normalize_port(raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {"id": raw.get("id")}
    for key in (
        "uid",
        "identifier",
        "label",
        "type",
        "index",
        "usage",
        "value",
        "connected_from",
        "connections",
        "exposed",
        "exposure",
        "exposed_as",
    ):
        if key in raw:
            normalized[key] = raw[key]
    return normalized


def _connection_optional_fields(conn: Dict[str, Any]) -> Dict[str, Any]:
    optional = {}
    for key in (
        "from_output_uid",
        "source_output_uid",
        "connRefOutput",
        "conn_ref_output",
        "to_input_uid",
        "destination_input_uid",
    ):
        if key in conn:
            optional[key] = conn[key]
    return optional


def _normalize_nested_graph_ref(
    raw: Dict[str, Any], *, node_id: Any = None, graph_identifier: Any = None
) -> Dict[str, Any]:
    kind = raw.get("kind")
    property_id = raw.get("property") or raw.get("property_id")
    graph_type = raw.get("graph_type")
    if kind == "fx_map_graph" or (graph_type == "SDSBSFxMapGraph" and not property_id):
        graph_ref = _compact(
            {
                "kind": "fx_map_graph",
                "owner_node_id": node_id,
                "graph_identifier": graph_identifier,
                "graph_type": graph_type or "SDSBSFxMapGraph",
            }
        )
        node_args = _compact({"node_id": node_id, "graph_identifier": graph_identifier})
        return {
            "kind": "fx_map_graph",
            "graph_type": graph_type or "SDSBSFxMapGraph",
            "exists": bool(raw.get("exists", True)),
            "read_tool": tool_hint("get_graph", {"graph_ref": graph_ref}),
            "inspect_tool": tool_hint("get_node", node_args),
            "preview_tool": tool_hint("get_preview", node_args),
        }
    graph_ref = _compact(
        {
            "kind": "node_property_graph",
            "owner_node_id": node_id,
            "property_id": property_id,
            "parent_graph": graph_identifier,
            "graph_type": graph_type or "SDSBSFunctionGraph",
        }
    )
    node_args = _compact({"node_id": node_id, "graph_identifier": graph_identifier})
    return {
        "property": property_id,
        "graph_type": graph_type,
        "exists": bool(raw.get("exists", True)),
        "read_tool": tool_hint("get_graph", {"graph_ref": graph_ref}),
        "inspect_tool": tool_hint("get_node", node_args),
        "preview_tool": tool_hint("get_preview", node_args),
    }


def _position(value: Any) -> Optional[List[float]]:
    if isinstance(value, dict):
        if "x" in value and "y" in value:
            return [_float(value.get("x")), _float(value.get("y"))]
        if "0" in value and "1" in value:
            return [_float(value.get("0")), _float(value.get("1"))]
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return [_float(value[0]), _float(value[1])]
    return None


def _list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, dict)):
        return []
    return [item for item in value if isinstance(item, dict)]


def _compact(value: Dict[str, Any]) -> Dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
