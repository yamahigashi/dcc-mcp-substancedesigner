"""Helpers for normalized graph inspection and structural validation."""

from __future__ import annotations

from collections import deque
from typing import Any

from dcc_mcp_substancedesigner.canonical_graph import build_canonical_graph


def build_graph_state(
    summary: dict[str, Any], details_by_node_id: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build an inspection-oriented graph state from normalized graph data."""
    return build_canonical_graph(summary, details_by_node_id)


def validate_lineage(
    graph_state: dict[str, Any],
    *,
    source_node_id: str,
    target_node_id: str | None = None,
    target_output_identifier: str | None = None,
    source_output: str | None = None,
) -> dict[str, Any]:
    """Validate that a selected source reaches a target node or graph output."""
    nodes = {str(node["identifier"]): node for node in _list(graph_state.get("nodes")) if node.get("identifier")}
    if source_node_id not in nodes:
        return _lineage_result(False, source_node_id, None, [], [f"source node '{source_node_id}' was not found"])

    resolved_target = _resolve_target(
        nodes, _list(graph_state.get("output_bindings")), target_node_id, target_output_identifier
    )
    if not resolved_target:
        target_text = target_node_id or target_output_identifier or ""
        return _lineage_result(False, source_node_id, target_text, [], [f"target '{target_text}' was not found"])

    path = _find_path(_list(graph_state.get("connections")), source_node_id, resolved_target, source_output)
    if not path:
        return _lineage_result(
            False,
            source_node_id,
            resolved_target,
            [],
            [f"source node '{source_node_id}' does not reach target '{resolved_target}'"],
        )

    return _lineage_result(True, source_node_id, resolved_target, path, [])


def _find_path(
    connections: list[dict[str, Any]],
    source_node_id: str,
    target_node_id: str,
    source_output: str | None,
) -> list[dict[str, str | None]]:
    adjacency: dict[str, list[dict[str, str | None]]] = {}
    for edge in connections:
        from_node = _text(edge.get("from_node"))
        to_node = _text(edge.get("to_node"))
        if not from_node or not to_node:
            continue
        normalized = {
            "from_node": from_node,
            "from_output": _text(edge.get("from_output")),
            "to_node": to_node,
            "to_input": _text(edge.get("to_input")),
        }
        adjacency.setdefault(from_node, []).append(normalized)

    queue: deque[tuple[str, list[dict[str, str | None]]]] = deque([(source_node_id, [])])
    visited = {source_node_id}
    while queue:
        node_id, path = queue.popleft()
        if node_id == target_node_id:
            return path
        for edge in adjacency.get(node_id, []):
            if node_id == source_node_id and source_output and edge.get("from_output") != source_output:
                continue
            next_node = str(edge["to_node"])
            if next_node in visited:
                continue
            visited.add(next_node)
            queue.append((next_node, [*path, edge]))
    return []


def _resolve_target(
    nodes: dict[str, dict[str, Any]],
    output_bindings: list[dict[str, Any]],
    target_node_id: str | None,
    target_output_identifier: str | None,
) -> str | None:
    if target_node_id:
        return target_node_id if target_node_id in nodes else None
    if not target_output_identifier:
        return None
    if target_output_identifier in nodes:
        return target_output_identifier
    for binding in output_bindings:
        values = {
            _text(binding.get("node_id")),
            _text(binding.get("identifier")),
            _text(binding.get("label")),
            _text(binding.get("usage")),
        }
        if target_output_identifier in values:
            return _text(binding.get("node_id"))
    return None


def _output_binding(node: dict[str, Any], producers: list[dict[str, str | None]]) -> dict[str, Any]:
    annotations = {str(item.get("id")): item.get("value") for item in _list(node.get("annotations")) if item.get("id")}
    source = producers[0] if producers else None
    label = annotations.get("label")
    identifier = annotations.get("identifier")
    usage = annotations.get("usage")
    return {
        "node_id": node.get("identifier"),
        "identifier": str(identifier) if identifier is not None else node.get("identifier"),
        "label": str(label) if label is not None else None,
        "usage": str(usage) if usage is not None else None,
        "source": source,
    }


def _lineage_result(
    valid: bool,
    source_node_id: str,
    target_node_id: str | None,
    path: list[dict[str, str | None]],
    errors: list[str],
) -> dict[str, Any]:
    return {
        "valid": valid,
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "path": path,
        "path_length": len(path),
        "errors": errors,
    }


def _list(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
