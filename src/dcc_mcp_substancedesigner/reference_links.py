"""Helpers that connect tool responses to MCP authoring resources."""

from __future__ import annotations

from typing import Any

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    node_definitions_by_id,
)


def reference_uris_for_definition(definition_id: str | None, *, contracts: list[str] | None = None) -> list[str]:
    """Return resource URIs related to a Substance Designer definition id."""
    uris: list[str] = []
    if definition_id:
        matches = node_definitions_by_id(definition_id)
        uris.extend(f"{AUTHORING_PREFIX}/node/{node.get('kind')}/{node.get('slug')}" for node in matches)
        uris.append(f"{AUTHORING_PREFIX}/node-definition/{definition_id}")
    for contract in contracts or []:
        uris.append(f"{AUTHORING_PREFIX}/contracts/{contract}")
    return _dedupe(uris)


def reference_uris_for_node_detail(node: dict[str, Any]) -> list[str]:
    """Return resource URIs that should be read before editing a node."""
    contracts = ["reference-first-policy", "node-introspection", "operation-safety"]
    if node.get("nested_graph_refs"):
        contracts.append("owner-input-binding")
    contracts.append("compositing-graph-state")
    definition = _text(node.get("resolved_definition")) or _text(node.get("definition"))
    return reference_uris_for_definition(definition, contracts=contracts)


def reference_uris_for_graph_state(graph_state: dict[str, Any], *, include_contracts: bool = True) -> list[str]:
    """Return node and contract resources related to a graph state."""
    uris: list[str] = []
    for node in graph_state.get("nodes", []):
        if isinstance(node, dict):
            uris.extend(reference_uris_for_definition(_text(node.get("definition"))))
    if include_contracts:
        uris.extend(
            [
                f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
                f"{AUTHORING_PREFIX}/contracts/compositing-graph-state",
                f"{AUTHORING_PREFIX}/contracts/node-introspection",
                f"{AUTHORING_PREFIX}/contracts/owner-input-binding",
                f"{AUTHORING_PREFIX}/contracts/operation-safety",
            ]
        )
    return _dedupe(uris)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
