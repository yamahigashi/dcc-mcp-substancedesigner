"""Runtime node inspection response shaping and static catalog comparison."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    node_definition_by_id,
    node_definition_by_kind_slug,
)


def build_node_inspection(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a tooling-facing node inspection payload."""
    runtime = _runtime_summary(raw)
    static_node = _static_node_for_runtime(raw, runtime)
    static_reference = _static_reference(static_node)
    comparison = _compare_runtime_to_static(runtime, static_node)
    reference_uris = _reference_uris(static_reference)
    return {
        "status": "ok",
        "target": raw.get("target", {}),
        "runtime": runtime,
        "static_reference": static_reference,
        "comparison": comparison,
        "reference_uris": reference_uris,
        "evidence": {
            "source": "live_host_introspection",
            "node_id": raw.get("node_id"),
            "temporary_node_id": raw.get("temporary_node_id"),
        },
    }


def _runtime_summary(raw: dict[str, Any]) -> dict[str, Any]:
    inputs = raw.get("inputs", [])
    outputs = raw.get("outputs", [])
    parameters = []
    input_ports = []
    for prop in inputs if isinstance(inputs, list) else []:
        if not isinstance(prop, dict):
            continue
        item = _runtime_property(prop)
        if "value" in prop:
            parameters.append(item)
        else:
            input_ports.append({**item, "role": "connection_port"})
    return {
        "definition": raw.get("definition"),
        "is_library_node": bool(raw.get("is_library_node")),
        "instance": raw.get("instance"),
        "ports": {
            "inputs": input_ports,
            "outputs": [_runtime_property(prop) for prop in outputs if isinstance(prop, dict)],
        },
        "parameters": parameters,
        "annotations": raw.get("annotations", []),
        "nested_graph_refs": raw.get("nested_graph_refs", []),
        "property_context": raw.get("property_context"),
    }


def _runtime_property(prop: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": prop.get("id"),
        "label": prop.get("label"),
        "type": prop.get("type"),
    }
    if "value" in prop:
        item["current_value"] = prop.get("value")
    return {key: value for key, value in item.items() if value is not None}


def _static_node_for_runtime(raw: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any] | None:
    target = raw.get("target", {})
    if isinstance(target, dict):
        definition_id = target.get("definition_id")
        if isinstance(definition_id, str):
            node = node_definition_by_id(definition_id)
            if node is not None:
                return node
        resource_url = target.get("resource_url")
        if isinstance(resource_url, str):
            node = node_definition_by_kind_slug("library", _slug_from_resource_url(resource_url))
            if node is not None:
                return node
    definition = runtime.get("definition")
    if isinstance(definition, str):
        return node_definition_by_id(definition)
    return None


def _slug_from_resource_url(resource_url: str) -> str:
    parsed = urlparse(resource_url)
    return (parsed.path.rsplit("/", 1)[-1] or parsed.netloc or resource_url).lower()


def _static_reference(static_node: dict[str, Any] | None) -> dict[str, Any]:
    if static_node is None:
        return {"matched": False}
    kind = static_node.get("kind")
    slug = static_node.get("slug")
    return {
        "matched": True,
        "uri": f"{AUTHORING_PREFIX}/node/{kind}/{slug}",
        "definition_id": static_node.get("definition_id"),
        "kind": kind,
        "slug": slug,
    }


def _reference_uris(static_reference: dict[str, Any]) -> list[str]:
    uris = [
        "substancedesigner://authoring/contracts/node-introspection",
        "substancedesigner://authoring/contracts/operation-safety",
    ]
    uri = static_reference.get("uri")
    if isinstance(uri, str):
        uris.insert(0, uri)
    definition_id = static_reference.get("definition_id")
    if isinstance(definition_id, str):
        uris.append(f"{AUTHORING_PREFIX}/node-definition/{definition_id}")
    return list(dict.fromkeys(uris))


def _compare_runtime_to_static(runtime: dict[str, Any], static_node: dict[str, Any] | None) -> dict[str, Any]:
    if static_node is None:
        return {"status": "static_not_found", "differences": []}
    static_ports = static_node.get("ports", {}) if isinstance(static_node.get("ports"), dict) else {}
    expected_inputs = _ids(static_ports.get("inputs", []))
    expected_outputs = _ids(static_ports.get("outputs", []))
    expected_parameters = _ids(static_node.get("parameters", []))
    runtime_ports = runtime.get("ports", {}) if isinstance(runtime.get("ports"), dict) else {}
    actual_inputs = _ids(runtime_ports.get("inputs", []))
    actual_outputs = _ids(runtime_ports.get("outputs", []))
    actual_parameters = _ids(runtime.get("parameters", []))

    differences = []
    differences.extend(_missing_extra("ports.inputs", expected_inputs, actual_inputs))
    differences.extend(_missing_extra("ports.outputs", expected_outputs, actual_outputs))
    differences.extend(_missing_extra("parameters", expected_parameters, actual_parameters))
    return {"status": "match" if not differences else "mismatch", "differences": differences}


def _ids(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {str(item["id"]) for item in items if isinstance(item, dict) and item.get("id") is not None}


def _missing_extra(path: str, expected: set[str], actual: set[str]) -> list[dict[str, Any]]:
    differences = []
    for item in sorted(expected - actual):
        differences.append({"path": path, "id": item, "static": "present", "runtime": "missing"})
    for item in sorted(actual - expected):
        differences.append({"path": path, "id": item, "static": "missing", "runtime": "present"})
    return differences
