"""Analysis views over the canonical Substance Designer graph model."""

from __future__ import annotations

from collections import deque

from dcc_mcp_substancedesigner.json_types import JsonMap, JsonValue


def graph_outputs(graph_state: JsonMap) -> JsonMap:
    """Return semantic graph output bindings."""
    outputs = _list(graph_state.get("graph_outputs") or graph_state.get("output_bindings"))
    return {
        "graph_identifier": graph_state.get("identifier"),
        "outputs": outputs,
        "output_count": len(outputs),
        "diagnostics": _list(graph_state.get("diagnostics")),
    }


def trace_output(graph_state: JsonMap, output_identifier: str) -> JsonMap:
    """Trace the upstream chain feeding a graph output."""
    output = _resolve_output(graph_state, output_identifier)
    if output is None:
        return {
            "graph_identifier": graph_state.get("identifier"),
            "output_identifier": output_identifier,
            "found": False,
            "chain": [],
            "node_ids": [],
            "diagnostics": [
                {
                    "severity": "error",
                    "code": "output_not_found",
                    "message": f"Graph output '{output_identifier}' was not found.",
                    "source": "graph_analysis",
                }
            ],
        }

    output_node = _text(output.get("node_id"))
    chain = upstream_chain(graph_state, output_node) if output_node else []
    node_ids = _ordered_node_ids(chain)
    return {
        "graph_identifier": graph_state.get("identifier"),
        "output": output,
        "output_identifier": output_identifier,
        "found": True,
        "chain": chain,
        "node_ids": node_ids,
        "diagnostics": _list(output.get("diagnostics")),
    }


def summarize_graph(graph_state: JsonMap) -> JsonMap:
    """Build a review-oriented summary from canonical graph facts."""
    nodes = _list(graph_state.get("nodes"))
    connections = _list(graph_state.get("connections"))
    outputs = _list(graph_state.get("graph_outputs") or graph_state.get("output_bindings"))
    output_node_ids = {_text(output.get("node_id")) for output in outputs if _text(output.get("node_id"))}
    reached = _nodes_reaching_outputs(connections, output_node_ids)
    all_node_ids = {_text(node.get("node_id") or node.get("identifier")) for node in nodes}
    all_node_ids.discard(None)
    raw_consumers = graph_state.get("consumers")
    consumers: JsonMap = raw_consumers if isinstance(raw_consumers, dict) else {}

    output_summaries = []
    for output in outputs:
        output_node = _text(output.get("node_id"))
        chain = upstream_chain(graph_state, output_node) if output_node else []
        output_summaries.append(
            {
                **output,
                "upstream_chain": chain,
                "upstream_node_ids": _ordered_node_ids(chain),
                "unresolved": not bool(output.get("source_node_id")),
            }
        )

    unused_nodes = []
    dead_branch_nodes = []
    disconnected_inputs = []
    pixel_processors = []
    parameters = []
    diagnostics = list(_list(graph_state.get("diagnostics")))

    for node in nodes:
        node_id = _text(node.get("node_id") or node.get("identifier"))
        if not node_id:
            continue
        if node.get("kind") == "pixel_processor":
            pixel_processors.append(
                {
                    "node_id": node_id,
                    "label": node.get("label"),
                    "nested_graph_refs": node.get("nested_graph_refs", []),
                    "diagnostics": node.get("diagnostics", []),
                }
            )
        valued_parameters = _list(node.get("parameters"))
        if valued_parameters:
            parameters.append(
                {
                    "node_id": node_id,
                    "parameters": [
                        {
                            "identifier": item.get("identifier"),
                            "label": item.get("label"),
                            "value": item.get("value"),
                            "display_value": item.get("display_value"),
                            "value_type": item.get("value_type"),
                            "semantic_role": item.get("semantic_role"),
                        }
                        for item in valued_parameters
                    ],
                }
            )
        if node_id not in consumers and node_id not in output_node_ids:
            unused_nodes.append(_node_ref(node))
        if node_id not in reached and node_id not in output_node_ids:
            dead_branch_nodes.append(_node_ref(node))
        for input_port in _list(node.get("inputs")):
            if "value" in input_port or input_port.get("connected_from") or input_port.get("connections"):
                continue
            disconnected_inputs.append({"node_id": node_id, "input": input_port.get("id")})
        diagnostics.extend(_list(node.get("diagnostics")))

    return {
        "graph_identifier": graph_state.get("identifier"),
        "node_count": graph_state.get("node_count", len(nodes)),
        "connection_count": graph_state.get("connection_count", len(connections)),
        "outputs": output_summaries,
        "unused_nodes": unused_nodes,
        "dead_branch_nodes": dead_branch_nodes,
        "disconnected_inputs": disconnected_inputs,
        "parameters": parameters,
        "pixel_processors": pixel_processors,
        "diagnostics": _dedupe_diagnostics(diagnostics),
    }


def upstream_chain(graph_state: JsonMap, target_node_id: str | None) -> list[JsonMap]:
    """Return upstream edges ordered from sources toward the target where possible."""
    if not target_node_id:
        return []
    raw_producers = graph_state.get("producers")
    producers: JsonMap = raw_producers if isinstance(raw_producers, dict) else {}
    queue: deque[str] = deque([target_node_id])
    visited = {target_node_id}
    reverse_edges = []
    while queue:
        node_id = queue.popleft()
        for producer in _list(producers.get(node_id)):
            source = _text(producer.get("node"))
            if not source:
                continue
            edge = {
                "from_node": source,
                "from_output": producer.get("output"),
                "from_output_uid": producer.get("output_uid"),
                "to_node": node_id,
                "to_input": producer.get("to_input"),
            }
            reverse_edges.append(edge)
            if source not in visited:
                visited.add(source)
                queue.append(source)
    return list(reversed(reverse_edges))


def _nodes_reaching_outputs(connections: list[JsonMap], output_node_ids: set[str | None]) -> set[str]:
    reverse_adjacency: dict[str, list[str]] = {}
    for edge in connections:
        from_node = _text(edge.get("from_node"))
        to_node = _text(edge.get("to_node"))
        if not from_node or not to_node:
            continue
        reverse_adjacency.setdefault(to_node, []).append(from_node)
    reached: set[str] = set()
    queue: deque[str] = deque(node_id for node_id in output_node_ids if node_id)
    while queue:
        node_id = queue.popleft()
        for source in reverse_adjacency.get(node_id, []):
            if source in reached:
                continue
            reached.add(source)
            queue.append(source)
    return reached


def _resolve_output(graph_state: JsonMap, output_identifier: str) -> JsonMap | None:
    for output in _list(graph_state.get("graph_outputs") or graph_state.get("output_bindings")):
        values = {
            _text(output.get("node_id")),
            _text(output.get("identifier")),
            _text(output.get("label")),
            _text(output.get("usage")),
        }
        if output_identifier in values:
            return output
    return None


def _ordered_node_ids(chain: list[JsonMap]) -> list[str]:
    ordered = []
    for edge in chain:
        for key in ("from_node", "to_node"):
            node_id = _text(edge.get(key))
            if node_id and node_id not in ordered:
                ordered.append(node_id)
    return ordered


def _node_ref(node: JsonMap) -> JsonMap:
    return {
        "node_id": node.get("node_id") or node.get("identifier"),
        "definition": node.get("definition"),
        "kind": node.get("kind"),
        "label": node.get("label"),
    }


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
