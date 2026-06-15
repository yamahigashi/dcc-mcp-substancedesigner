"""Canonical graph read model construction for Substance Designer inspection."""

from __future__ import annotations

from dcc_mcp_substancedesigner.json_types import JsonMap, JsonValue
from dcc_mcp_substancedesigner.semantic_graph import enrich_node_detail, node_kind, resolve_usage


def build_canonical_graph(summary: JsonMap, details_by_node_id: dict[str, JsonMap] | None = None) -> JsonMap:
    """Build a loss-aware adapter-owned graph model from normalized host data."""
    details_by_node_id = details_by_node_id or {}
    nodes = []
    connections = []
    diagnostics = []
    consumers: dict[str, list[JsonMap]] = {}
    producers: dict[str, list[JsonMap]] = {}

    for raw_node in _list(summary.get("nodes")):
        node_id = _text(raw_node.get("identifier"))
        if not node_id:
            continue
        detail = details_by_node_id.get(node_id) or {}
        semantic_detail = enrich_node_detail(
            {
                "node_id": node_id,
                "definition": raw_node.get("definition"),
                "position": raw_node.get("position"),
                "annotations": raw_node.get("annotations", []),
                **detail,
            }
        )
        node: JsonMap = {
            "node_id": node_id,
            "identifier": node_id,
            "definition": raw_node.get("definition"),
            "kind": semantic_detail.get("kind") or node_kind(_text(raw_node.get("definition"))),
            "filter_type": semantic_detail.get("filter_type"),
            "label": semantic_detail.get("label"),
            "display_identifier": semantic_detail.get("identifier"),
            "comment": semantic_detail.get("comment"),
            "position": raw_node.get("position"),
            "inputs": semantic_detail.get("inputs", []),
            "outputs": semantic_detail.get("outputs", []),
            "parameters": semantic_detail.get("parameters", []),
            "annotations": semantic_detail.get("annotations", []),
            "exposed_inputs": semantic_detail.get("exposed_inputs", []),
            "instance": semantic_detail.get("instance"),
            "output_binding": semantic_detail.get("output_binding"),
            "graph_surfaces": semantic_detail.get("graph_surfaces", []),
            "nested_graph_refs": semantic_detail.get("nested_graph_refs", []),
            "diagnostics": semantic_detail.get("diagnostics", []),
            "connections": [],
        }
        for conn in _list(raw_node.get("connections")):
            edge = _canonical_connection(conn, node_id)
            if not edge.get("from_node"):
                continue
            diagnostics.extend(_connection_diagnostics(edge))
            connections.append(edge)
            node["connections"].append(
                {
                    "input": edge.get("to_input"),
                    "from_node": edge.get("from_node"),
                    "from_output": edge.get("from_output"),
                    "from_output_uid": edge.get("from_output_uid"),
                    "conn_ref_output": edge.get("conn_ref_output"),
                }
            )
            consumers.setdefault(str(edge["from_node"]), []).append(
                {
                    "node": node_id,
                    "input": edge.get("to_input"),
                    "from_output": edge.get("from_output"),
                    "from_output_uid": edge.get("from_output_uid"),
                }
            )
            producers.setdefault(node_id, []).append(
                {
                    "node": edge.get("from_node"),
                    "output": edge.get("from_output"),
                    "output_uid": edge.get("from_output_uid"),
                    "to_input": edge.get("to_input"),
                }
            )
        nodes.append(node)

    graph_outputs = [
        _graph_output_from_node(node, producers.get(str(node.get("node_id")), []))
        for node in nodes
        if node.get("kind") == "graph_output"
    ]
    for output in graph_outputs:
        diagnostics.extend(_list(output.get("diagnostics")))
    return {
        "identifier": summary.get("identifier") or summary.get("graph_identifier"),
        "package_path": summary.get("package_path"),
        "node_count": summary.get("node_count", len(nodes)),
        "nodes": nodes,
        "connections": connections,
        "canonical_connections": [_endpoint_connection(edge) for edge in connections],
        "connection_count": len(connections),
        "consumers": consumers,
        "producers": producers,
        "graph_outputs": graph_outputs,
        "output_bindings": graph_outputs,
        "returned_node_count": summary.get("returned_node_count", len(nodes)),
        "truncated": bool(summary.get("truncated", False)),
        "node_limit": summary.get("node_limit", len(nodes)),
        "diagnostics": _dedupe_diagnostics(diagnostics),
    }


def _canonical_connection(raw: JsonMap, to_node: str) -> JsonMap:
    from_output = _text(raw.get("from_output") or raw.get("from_output_identifier"))
    from_output_uid = _text(
        raw.get("from_output_uid")
        or raw.get("source_output_uid")
        or raw.get("connRefOutput")
        or raw.get("conn_ref_output")
    )
    conn_ref_output = _text(raw.get("connRefOutput") or raw.get("conn_ref_output"))
    return {
        "from_node": _text(raw.get("from_node") or raw.get("source_node")),
        "from_output": from_output,
        "from_output_uid": from_output_uid,
        "from_output_identifier": from_output,
        "to_node": to_node,
        "to_input": _text(raw.get("input") or raw.get("to_input") or raw.get("destination_input")),
        "to_input_uid": _text(raw.get("to_input_uid") or raw.get("destination_input_uid")),
        "to_input_identifier": _text(raw.get("input") or raw.get("to_input") or raw.get("destination_input")),
        "conn_ref_output": conn_ref_output,
        "raw": raw,
    }


def _graph_output_from_node(node: JsonMap, producers: list[JsonMap]) -> JsonMap:
    raw_output_binding = node.get("output_binding")
    output_binding: JsonMap = raw_output_binding if isinstance(raw_output_binding, dict) else {}
    identifier = _text(output_binding.get("identifier") or node.get("display_identifier") or node.get("node_id"))
    label = _text(output_binding.get("label") or node.get("label"))
    usage = _text(output_binding.get("usage"))
    usage_source = _text(output_binding.get("usage_source"))
    diagnostics = _list(node.get("diagnostics"))
    if not usage:
        usage, usage_source, usage_diagnostics = resolve_usage(None, identifier, label)
        diagnostics.extend(usage_diagnostics)
    if not usage and (identifier or label):
        diagnostics.append(
            {
                "severity": "info",
                "code": "output_usage_unset",
                "message": "Graph output usage is unset; identifier and label remain available for caller policy.",
                "source": "canonical_graph",
            }
        )
    if not usage and not (identifier or label):
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unresolved_output_usage",
                "message": "Graph output usage could not be resolved from host metadata or identifier.",
                "source": "canonical_graph",
            }
        )
    source = producers[0] if producers else None
    if not source:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "unconnected_graph_output",
                "message": "Graph output has no upstream source connection.",
                "source": "canonical_graph",
            }
        )
    return {
        "node_id": node.get("node_id"),
        "identifier": identifier,
        "label": label,
        "usage": usage,
        "usage_source": usage_source,
        "source": source,
        "source_node_id": source.get("node") if source else None,
        "source_output": source.get("output") if source else None,
        "source_output_uid": source.get("output_uid") if source else None,
        "diagnostics": diagnostics,
    }


def _endpoint_connection(edge: JsonMap) -> JsonMap:
    source = {
        "node": edge.get("from_node"),
        "output": edge.get("from_output"),
        **_compact({"output_uid": edge.get("from_output_uid")}),
    }
    target = {
        "node": edge.get("to_node"),
        "input": edge.get("to_input"),
        **_compact({"input_uid": edge.get("to_input_uid")}),
    }
    return {"from": source, "to": target}


def _connection_diagnostics(edge: JsonMap) -> list[JsonMap]:
    if edge.get("from_output_uid") or edge.get("conn_ref_output"):
        return []
    return [
        {
            "severity": "info",
            "code": "missing_source_output_uid",
            "message": "Connection source output uid was not provided by the host response.",
            "source": "canonical_graph",
        }
    ]


def _dedupe_diagnostics(diagnostics: list[JsonMap]) -> list[JsonMap]:
    result = []
    seen = set()
    for item in diagnostics:
        key = (item.get("severity"), item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _text(value: JsonValue) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _list(value: JsonValue) -> list[JsonMap]:
    if not isinstance(value, list):
        return []
    result: list[JsonMap] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
    return result


def _compact(value: JsonMap) -> JsonMap:
    return {key: item for key, item in value.items() if item is not None}
