"""Declarative nested graph state helpers."""

from __future__ import annotations

import re
from typing import Any

from dcc_mcp_substancedesigner.authoring_reference import AUTHORING_PREFIX, node_definition_by_id
from dcc_mcp_substancedesigner.input_types import (
    NestedGraphStateInput,
    OptionalNestedGraphStateInput,
)
from dcc_mcp_substancedesigner.json_types import JsonMap

NESTED_GRAPH_MODES = {"sync", "replace", "param_update"}
EXTERNAL_REFERENCE_VALUE_TYPES = {
    "float",
    "int",
    "bool",
    "string",
    "float2",
    "float3",
    "float4",
    "int2",
    "int3",
    "int4",
    "color",
    "colorrgba",
}
EXTERNAL_REFERENCE_ANNOTATIONS = {"description", "min", "max", "step", "clamp", "editor", "group"}
INPUT_NODE_DEFINITIONS = {
    "bool": "sbs::function::get_bool",
    "color": "sbs::function::get_float4",
    "colorrgba": "sbs::function::get_float4",
    "float": "sbs::function::get_float1",
    "float2": "sbs::function::get_float2",
    "float3": "sbs::function::get_float3",
    "float4": "sbs::function::get_float4",
    "int": "sbs::function::get_integer1",
    "int2": "sbs::function::get_integer2",
    "int3": "sbs::function::get_integer3",
    "int4": "sbs::function::get_integer4",
    "string": "sbs::function::get_string",
}


class NestedGraphStateValidationError(ValueError):
    """Raised when a nested graph state payload is structurally invalid."""


def validate_nested_graph_state(state: NestedGraphStateInput, *, mode: str = "sync") -> dict[str, Any]:
    """Validate a nested graph desired-state payload."""
    mode = _validate_mode(mode)
    normalized = _normalize_state(state)
    errors = _state_errors(normalized, mode=mode)
    warnings = _state_warnings(normalized) if not errors else []
    return {
        "valid": not errors,
        "mode": mode,
        "errors": errors,
        "warnings": warnings,
        "reference_uris": _reference_uris_from_errors(errors),
        "state": normalized if not errors else None,
    }


def diff_nested_graph_state(
    current: OptionalNestedGraphStateInput, desired: NestedGraphStateInput, *, mode: str = "sync"
) -> dict[str, Any]:
    """Return a conservative structural diff between current and desired state."""
    validation = validate_nested_graph_state(desired, mode=mode)
    if not validation["valid"]:
        return {
            "valid": False,
            "mode": mode,
            "status": "invalid",
            "errors": validation["errors"],
            "reference_uris": validation.get("reference_uris", []),
            "changes": [],
            "requires_replace": False,
        }
    desired_state = validation["state"]
    current = current or {}
    current_nodes = _nodes_by_id(current.get("nodes"))
    desired_nodes = _nodes_by_id(desired_state.get("nodes"))
    current_connections = _connection_set(current.get("connections"))
    desired_connections = _connection_set(desired_state.get("connections"))
    current_external_references = _external_reference_set(current.get("external_references"))
    desired_external_references = _external_reference_set(desired_state.get("external_references"))

    added_nodes = sorted(set(desired_nodes) - set(current_nodes))
    removed_nodes = sorted(set(current_nodes) - set(desired_nodes))
    changed_nodes = []
    for node_id in sorted(set(desired_nodes) & set(current_nodes)):
        if _node_signature(desired_nodes[node_id]) != _node_signature(current_nodes[node_id]):
            changed_nodes.append(node_id)

    added_connections = sorted(desired_connections - current_connections)
    removed_connections = sorted(current_connections - desired_connections)
    added_external_references = sorted(desired_external_references - current_external_references)
    removed_external_references = sorted(current_external_references - desired_external_references)
    output_changed = _output_id(current.get("output")) != _output_id(desired_state.get("output"))

    changes = []
    if added_nodes:
        changes.append({"type": "add_nodes", "ids": added_nodes})
    if removed_nodes:
        changes.append({"type": "remove_nodes", "ids": removed_nodes})
    if changed_nodes:
        changes.append({"type": "change_nodes", "ids": changed_nodes})
    if added_connections:
        changes.append({"type": "add_connections", "connections": [list(item) for item in added_connections]})
    if removed_connections:
        changes.append({"type": "remove_connections", "connections": [list(item) for item in removed_connections]})
    if added_external_references:
        changes.append({"type": "add_external_references", "ids": added_external_references})
    if removed_external_references:
        changes.append({"type": "remove_external_references", "ids": removed_external_references})
    if output_changed:
        changes.append(
            {
                "type": "change_output",
                "from": _output_id(current.get("output")),
                "to": _output_id(desired_state.get("output")),
            }
        )
    structural = bool(
        added_nodes
        or removed_nodes
        or added_connections
        or removed_connections
        or added_external_references
        or removed_external_references
        or output_changed
    )
    return {
        "valid": True,
        "mode": mode,
        "status": "changed" if changes else "unchanged",
        "changes": changes,
        "requires_replace": mode == "replace" or structural,
        "param_only": bool(changed_nodes and not structural),
    }


def normalize_nested_graph_state_for_apply(state: NestedGraphStateInput, *, mode: str) -> dict[str, Any]:
    """Validate and return the normalized desired state or raise a facade error."""
    validation = validate_nested_graph_state(state, mode=mode)
    if not validation["valid"]:
        details = "; ".join(validation["errors"])
        raise NestedGraphStateValidationError(f"nested graph state is invalid: {details}")
    return validation["state"]


def _normalize_state(state: NestedGraphStateInput) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise NestedGraphStateValidationError("state must be an object")
    target = _dict(state.get("target"), "target")
    graph_type = _text(state.get("graph_type", "SDSBSFunctionGraph"), "graph_type")
    property_id = (
        state.get("property") or state.get("property_id") or target.get("property") or target.get("property_id")
    )
    target = _compact(
        {
            "package_path": _optional_text(target.get("package_path"), "target.package_path"),
            "package_index": target.get("package_index"),
            "graph_identifier": _optional_text(target.get("graph_identifier"), "target.graph_identifier"),
            "node_id": _node_id(target.get("node_id"), "target.node_id"),
            "property": _text(property_id, "target.property"),
        }
    )
    raw_nodes = _list(state.get("nodes"), "nodes")
    external_references = [
        _normalize_external_reference(item, index)
        for index, item in enumerate(_list(state.get("external_references", []), "external_references"))
    ]
    nodes = []
    input_references = []
    for index, item in enumerate(raw_nodes):
        normalized_node, external_reference = _normalize_node_with_reference(item, index)
        nodes.append(normalized_node)
        if external_reference is not None:
            input_references.append(external_reference)
    connections = [
        _normalize_connection(item, index)
        for index, item in enumerate(_list(state.get("connections", []), "connections"))
    ]
    normalized = {
        "target": target,
        "graph_type": graph_type,
        "nodes": nodes,
        "connections": connections,
        "external_references": _merge_external_references(external_references, input_references),
        "output": _normalize_output(state.get("output")),
    }
    metadata = state.get("metadata")
    if metadata is not None:
        normalized["metadata"] = _dict(metadata, "metadata")
    return normalized


def _normalize_node_with_reference(raw: Any, index: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    node = _dict(raw, f"nodes[{index}]")
    node_type = _optional_text(node.get("node_type"), f"nodes[{index}].node_type")
    if node_type != "input":
        return _normalize_node(node, index), None

    requested_input_id = _text(node.get("id"), f"nodes[{index}].id")
    input_id = _normalize_global_variable_reference(requested_input_id)
    value_type = _optional_text(node.get("value_type"), f"nodes[{index}].value_type") or "float"
    normalized_type = value_type.lower()
    if normalized_type == "colorrgba":
        value_type = "color"
        normalized_type = "color"
    definition = INPUT_NODE_DEFINITIONS.get(normalized_type)
    if definition is None:
        raise NestedGraphStateValidationError(
            "nodes[{}].value_type is not supported for input node: {}".format(index, value_type)
        )
    normalized: JsonMap = {
        "id": input_id,
        "definition": definition,
        "parameters": {"__constant__": {"value": input_id, "type": "string"}},
    }
    if "position" in node:
        normalized["position"] = _position(node["position"], f"nodes[{index}].position")
    reference: JsonMap = {"id": input_id, "value_type": "color" if normalized_type == "color" else value_type}
    if requested_input_id != input_id:
        reference["requested_id"] = requested_input_id
    for key in sorted(EXTERNAL_REFERENCE_ANNOTATIONS):
        if key in node:
            reference[key] = node[key]
    if "default" in node:
        reference["default"] = node["default"]
    return normalized, reference


def _normalize_node(raw: Any, index: int) -> dict[str, Any]:
    node = _dict(raw, f"nodes[{index}]")
    node_type = _optional_text(node.get("node_type"), f"nodes[{index}].node_type")
    if node_type is not None:
        raise NestedGraphStateValidationError("nodes[{}].node_type is not supported".format(index))
    normalized: JsonMap = {"id": _text(node.get("id"), f"nodes[{index}].id")}
    normalized["definition"] = _text(node.get("definition"), f"nodes[{index}].definition")
    if "position" in node:
        normalized["position"] = _position(node["position"], f"nodes[{index}].position")
    if "parameters" in node:
        normalized["parameters"] = _normalize_parameters(_dict(node["parameters"], f"nodes[{index}].parameters"))
    if "value" in node:
        normalized["value"] = node["value"]
    return normalized


def _merge_external_references(
    references: list[dict[str, Any]], input_references: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for reference in [*references, *input_references]:
        merged[str(reference["id"])] = {**merged.get(str(reference["id"]), {}), **reference}
    return list(merged.values())


def _normalize_external_reference(raw: Any, index: int) -> dict[str, Any]:
    reference = _dict(raw, f"external_references[{index}]")
    requested_id = _text(reference.get("id"), f"external_references[{index}].id")
    normalized_id = _normalize_global_variable_reference(requested_id)
    normalized: JsonMap = {"id": normalized_id}
    if requested_id != normalized_id:
        normalized["requested_id"] = requested_id
    if "value_type" not in reference:
        return normalized
    value_type = _text(reference.get("value_type"), f"external_references[{index}].value_type")
    normalized_type = value_type.lower()
    if normalized_type == "colorrgba":
        value_type = "color"
        normalized_type = "color"
    if normalized_type not in EXTERNAL_REFERENCE_VALUE_TYPES:
        raise NestedGraphStateValidationError(
            "external_references[{}].value_type must be one of {}".format(
                index,
                sorted(EXTERNAL_REFERENCE_VALUE_TYPES),
            )
        )
    normalized["value_type"] = value_type
    for key in sorted(EXTERNAL_REFERENCE_ANNOTATIONS):
        if key in reference:
            normalized[key] = reference[key]
    return normalized


def _normalize_connection(raw: Any, index: int) -> dict[str, str]:
    conn = _dict(raw, f"connections[{index}]")
    return {
        "from": _text(conn.get("from"), f"connections[{index}].from"),
        "from_output": _port_ref(conn.get("from_output", "unique_filter_output"), f"connections[{index}].from_output"),
        "to": _text(conn.get("to"), f"connections[{index}].to"),
        "to_input": _port_ref(conn.get("to_input", "input1"), f"connections[{index}].to_input"),
    }


def _normalize_output(raw: Any) -> dict[str, str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return {"node": _text(raw, "output")}
    output = _dict(raw, "output")
    return {"node": _text(output.get("node"), "output.node")}


def _normalize_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(parameters)
    value = normalized.get("__constant__")
    if isinstance(value, str):
        normalized["__constant__"] = _normalize_global_variable_reference(value)
    elif isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, str):
            normalized["__constant__"] = {**value, "value": _normalize_global_variable_reference(inner)}
    return normalized


def _normalize_global_variable_reference(value: str) -> str:
    normalized = value.lstrip("#")
    return normalized or value


def _state_errors(state: NestedGraphStateInput, *, mode: str) -> list[str]:
    errors = []
    if state["graph_type"] != "SDSBSFunctionGraph":
        errors.append("only SDSBSFunctionGraph is supported in the initial implementation")
    node_ids = [node["id"] for node in state["nodes"]]
    duplicate_ids = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    if duplicate_ids:
        errors.append(f"duplicate logical node ids: {duplicate_ids}")
    node_id_set = set(node_ids)
    for conn in state["connections"]:
        if conn["from"] not in node_id_set:
            errors.append(f"connection source '{conn['from']}' is not a declared node")
        if conn["to"] not in node_id_set:
            errors.append(f"connection target '{conn['to']}' is not a declared node")
    errors.extend(_catalog_errors(state))
    output = state.get("output")
    if output and output["node"] not in node_id_set:
        errors.append(f"output node '{output['node']}' is not a declared node")
    elif output:
        output_node = _nodes_by_id(state["nodes"]).get(output["node"])
        if output_node is not None:
            definition = node_definition_by_id(str(output_node.get("definition", "")))
            if definition is not None and not _root_selectable(definition):
                errors.append(
                    "output node '{}' uses definition '{}' which cannot be a nested graph root; see {}".format(
                        output["node"],
                        output_node.get("definition"),
                        _node_resource_uri(definition),
                    )
                )
    if mode == "param_update" and not state.get("metadata"):
        errors.append("param_update requires metadata that identifies a generated compatible state")
    return errors


def _catalog_errors(state: NestedGraphStateInput) -> list[str]:
    errors: list[str] = []
    definitions_by_node: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(state["nodes"]):
        definition_id = str(node.get("definition", ""))
        definition = node_definition_by_id(definition_id)
        if definition is None:
            errors.append(
                "nodes[{}].definition '{}' is not in the static authoring reference; read {}, {}, or {} first".format(
                    index,
                    definition_id,
                    f"{AUTHORING_PREFIX}/nodes/atomic",
                    f"{AUTHORING_PREFIX}/nodes/function-atomic",
                    f"{AUTHORING_PREFIX}/nodes/function-library",
                )
            )
            continue
        definitions_by_node[str(node["id"])] = definition
        for parameter in definition.get("parameters", []):
            if not parameter.get("required", False):
                continue
            parameter_id = str(parameter.get("id"))
            parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
            if parameter_id not in parameters:
                errors.append(
                    "nodes[{}] definition '{}' requires parameter '{}'; see {}".format(
                        index,
                        definition_id,
                        parameter_id,
                        _node_resource_uri(definition),
                    )
                )
        for func_data in definition.get("funcDatas", []):
            if not func_data.get("required", False):
                continue
            func_data_id = str(func_data.get("id"))
            func_datas = node.get("funcDatas") if isinstance(node.get("funcDatas"), dict) else {}
            if func_data_id not in func_datas:
                errors.append(
                    "nodes[{}] definition '{}' requires funcData '{}'; see {}".format(
                        index,
                        definition_id,
                        func_data_id,
                        _node_resource_uri(definition),
                    )
                )
    for index, conn in enumerate(state["connections"]):
        source_definition = definitions_by_node.get(conn["from"])
        if source_definition is not None:
            outputs = _port_ids(source_definition, "outputs")
            if conn["from_output"] not in outputs and "*" not in outputs:
                errors.append(
                    "connections[{}].from_output '{}' is not an output port on '{}'; see {}".format(
                        index,
                        conn["from_output"],
                        source_definition.get("definition_id"),
                        _node_resource_uri(source_definition),
                    )
                )
        target_definition = definitions_by_node.get(conn["to"])
        if target_definition is not None:
            inputs = _port_ids(target_definition, "inputs")
            if conn["to_input"] not in inputs and "*" not in inputs:
                errors.append(
                    "connections[{}].to_input '{}' is not an input port on '{}'; see {}".format(
                        index,
                        conn["to_input"],
                        target_definition.get("definition_id"),
                        _node_resource_uri(target_definition),
                    )
                )
    return errors


def _state_warnings(state: NestedGraphStateInput) -> list[dict[str, Any]]:
    warnings = []
    for index, node in enumerate(state["nodes"]):
        definition = node_definition_by_id(str(node.get("definition", "")))
        if definition is None:
            continue
        availability = definition.get("availability", {})
        required_contexts = availability.get("requires_context", []) if isinstance(availability, dict) else []
        if required_contexts:
            warnings.append(
                {
                    "type": "context_scope_required",
                    "node_index": index,
                    "node_id": node.get("id"),
                    "definition": definition.get("definition_id"),
                    "required_contexts": required_contexts,
                    "resource_uri": _node_resource_uri(definition),
                    "message": (
                        "Definition '{}' requires function context {}; verify the target property context before "
                        "applying."
                    ).format(definition.get("definition_id"), required_contexts),
                }
            )
    return warnings


def _port_ids(definition: dict[str, Any], direction: str) -> set[str]:
    ports = definition.get("ports", {}).get(direction, [])
    if isinstance(ports, dict):
        return {str(port_id) for port_id in ports}
    return {str(port.get("id")) for port in ports if isinstance(port, dict)}


def _root_selectable(definition: dict[str, Any]) -> bool:
    root = definition.get("root", {})
    if not isinstance(root, dict):
        return False
    if "selectable" in root:
        return bool(root["selectable"])
    return bool(root.get("can_be_root", False))


def _node_resource_uri(definition: dict[str, Any]) -> str:
    return f"{AUTHORING_PREFIX}/node/{definition.get('kind')}/{definition.get('slug')}"


def _reference_uris_from_errors(errors: list[str]) -> list[str]:
    uris = []
    for error in errors:
        for uri in re.findall(r"substancedesigner://authoring/[^\s;]+", error):
            uris.append(uri.rstrip(".,)"))
    return sorted(set(uris))


def _validate_mode(mode: str) -> str:
    mode = _text(mode, "mode")
    if mode not in NESTED_GRAPH_MODES:
        raise NestedGraphStateValidationError(f"mode must be one of {sorted(NESTED_GRAPH_MODES)}")
    return mode


def _nodes_by_id(nodes: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(nodes, list):
        return {}
    result = {}
    for node in nodes:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            result[node["id"]] = node
    return result


def _connection_set(connections: Any) -> set[tuple[str, str, str, str]]:
    if not isinstance(connections, list):
        return set()
    result = set()
    for conn in connections:
        if not isinstance(conn, dict):
            continue
        result.add(
            (
                str(conn.get("from", "")),
                str(conn.get("from_output", "unique_filter_output")),
                str(conn.get("to", "")),
                str(conn.get("to_input", "input1")),
            )
        )
    return result


def _external_reference_set(references: Any) -> set[str]:
    if not isinstance(references, list):
        return set()
    return {item["id"] for item in references if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _node_signature(node: dict[str, Any]) -> tuple[Any, ...]:
    return (
        node.get("definition"),
        _freeze(node.get("parameters")),
        _freeze(node.get("value")),
    )


def _output_id(output: Any) -> str | None:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        value = output.get("node")
        return value if isinstance(value, str) else None
    return None


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NestedGraphStateValidationError(f"{name} must be an object")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise NestedGraphStateValidationError(f"{name} must be a list")
    return value


def _text(value: Any, name: str) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str) or not value.strip():
        raise NestedGraphStateValidationError(f"{name} must be a non-empty string")
    return value


def _port_ref(value: Any, name: str) -> str:
    if isinstance(value, dict):
        source = value.get("source")
        for key in ("id", "identifier", "property_id", "parameter_id", "input_id", "output_id", "port"):
            item = value.get(key)
            if isinstance(item, (str, int)) and not isinstance(item, bool) and str(item).strip():
                return str(item)
        if isinstance(source, dict):
            return _port_ref(source, name)
    return _text(value, name)


def _node_id(value: Any, name: str) -> str:
    if isinstance(value, bool):
        raise NestedGraphStateValidationError(f"{name} must be a non-empty string or integer")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    raise NestedGraphStateValidationError(f"{name} must be a non-empty string or integer")


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _position(value: Any, name: str) -> list[float]:
    if isinstance(value, dict):
        for first, second in (("x", "y"), ("left", "top"), ("0", "1")):
            if first in value and second in value:
                try:
                    return [float(value[first]), float(value[second])]
                except (TypeError, ValueError) as exc:
                    raise NestedGraphStateValidationError(f"{name} must contain exactly two numbers") from exc
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise NestedGraphStateValidationError(f"{name} must contain exactly two numbers")
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError) as exc:
        raise NestedGraphStateValidationError(f"{name} must contain exactly two numbers") from exc
