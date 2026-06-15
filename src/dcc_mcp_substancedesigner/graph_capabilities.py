"""Capability-driven graph authoring contracts."""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Any

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    FUNCTION_CONTRACTS_URI,
    FUNCTION_LIVE_PROBE_RESULTS_URI,
    FX_MAP_GRAPH_URI,
    SDF_FUNCTION_WORKFLOW_URI,
    SDF_VISUAL_ITERATION_UNITS,
    load_function_contract_registry,
    load_fx_map_graph_definition,
    node_definitions,
    node_definitions_by_id,
    public_tool_action_id,
    reference_next_tools,
    tool_hint,
)
from dcc_mcp_substancedesigner.graph_change_types import OutputUsageParameterValue
from dcc_mcp_substancedesigner.json_types import JsonMap, JsonValue, cast_json_map

FUNCTION_GRAPH_TYPE = "SDSBSFunctionGraph"
FX_MAP_GRAPH_TYPE = "SDSBSFxMapGraph"

SUBSTANCE_GRAPH_CHANGES = ["ensure_node", "ensure_connection", "remove_connection", "set_parameter", "move_node"]
FUNCTION_GRAPH_CHANGES = [
    "ensure_node",
    "ensure_connection",
    "remove_connection",
    "set_parameter",
    "set_property_graph",
    "move_node",
    "set_output",
]
FX_MAP_GRAPH_CHANGES = [
    "ensure_node",
    "ensure_connection",
    "remove_connection",
    "set_parameter",
    "set_property_graph",
    "move_node",
    "set_output",
]

GENERIC_FUNCTION_SCOPE = "generic_function"
UNKNOWN_FUNCTION_SCOPE = "unknown_function_context"
SDF_VIEWER_SCOPE = "3d_viewer"
SDF_FUNCTION_FAMILY = "sdf_function_library"


class GraphChangeValidationError(ValueError):
    """Raised when a graph change cannot be applied safely."""


def authoring_plan(
    *,
    graph_ref: JsonMap | None = None,
    context: JsonMap | str | None = None,
    intent: str | None = None,
) -> JsonMap:
    """Return the evidence and preview plan before concrete graph capabilities."""
    normalized_ref = normalize_graph_ref(graph_ref)
    graph_context = resolve_graph_context(graph_ref=normalized_ref, context=context)
    workflow_suggestions = _workflow_suggestions(graph_context, intent)
    workflow_refs = _dedupe_strings(
        [str(suggestion["workflow_uri"]) for suggestion in workflow_suggestions if suggestion.get("workflow_uri")]
    )
    sdf_plan = graph_context.get("graph_kind") == "substance_graph" and _is_sdf_intent(intent)
    payload: JsonMap = {
        "graph_ref": normalized_ref,
        "graph_context": graph_context,
        "intent": intent,
        "phase": "plan_before_capabilities",
        "mutation_unlocked": False,
        "required_evidence": _authoring_plan_required_evidence(sdf_plan),
        "workflow_refs": workflow_refs,
        "workflow_suggestions": workflow_suggestions,
        "preview_targets": _authoring_plan_preview_targets(normalized_ref, sdf_plan),
        "visual_units": SDF_VISUAL_ITERATION_UNITS if sdf_plan else [],
        "next_unit": "sdf_function" if sdf_plan else None,
        "next_tools": _authoring_plan_next_tools(normalized_ref, workflow_refs),
    }
    return payload


def authoring_capabilities(
    *,
    graph_ref: JsonMap | None = None,
    context: JsonMap | str | None = None,
    intent: str | None = None,
) -> JsonMap:
    """Return the graph-kind and contract-specific toolbelt available to an LLM author."""
    normalized_ref = normalize_graph_ref(graph_ref)
    graph_context = resolve_graph_context(graph_ref=normalized_ref, context=context)
    unsupported_reasons = _maps(graph_context.get("unsupported_reasons"))
    allowed_nodes = _allowed_node_definitions(graph_context, intent) if not unsupported_reasons else []
    workflow_suggestions = _workflow_suggestions(graph_context, intent)
    reference_uris = _dedupe_strings(
        [
            *_reference_uris(graph_context),
            *[str(suggestion["workflow_uri"]) for suggestion in workflow_suggestions if suggestion.get("workflow_uri")],
        ]
    )
    contract = _map_or_empty(graph_context.get("contract"))
    payload: JsonMap = {
        "graph_ref": normalized_ref,
        "graph_context": graph_context,
        "intent": intent,
        "definition_filter": _definition_filter(graph_context, intent),
        "allowed_definitions": [str(node["definition_id"]) for node in allowed_nodes if node.get("definition_id")],
        "nodes": [_node_capability(node) for node in allowed_nodes],
        "builtins": contract.get("builtins", []),
        "output_contract": _output_contract(graph_context),
        "authoring_surfaces": _authoring_surfaces(normalized_ref, graph_context),
        "contract_supported_changes": _supported_changes(graph_context),
        "apply_supported_changes": _apply_supported_changes(graph_context),
        "workflow_profile": _workflow_profile(graph_context),
        "workflow_suggestions": workflow_suggestions,
        "unsupported_reasons": unsupported_reasons,
        "diagnostics": _capability_diagnostics(graph_context),
        "reference_uris": reference_uris,
    }
    if workflow_suggestions and graph_context.get("graph_kind") == "substance_graph":
        payload["next_tools"] = _planning_next_tools(normalized_ref, intent, reference_uris)
    else:
        payload["apply_tool"] = public_tool_action_id("apply_graph_change")
        payload["next_tools"] = _capability_next_tools(normalized_ref, graph_context, reference_uris)
    return payload


def validate_graph_change(
    *,
    graph_ref: JsonMap | None = None,
    context: JsonMap | str | None = None,
    change: JsonMap | None = None,
) -> JsonMap:
    """Validate a declarative graph change against graph kind and function contract capabilities."""
    normalized_ref = normalize_graph_ref(graph_ref)
    if not isinstance(change, dict):
        return _validation_result(
            False,
            normalized_ref,
            context,
            change,
            [_error("invalid_change", "change", "change must be an object")],
        )
    change = normalize_graph_change_parameters(change)
    capabilities = authoring_capabilities(graph_ref=normalized_ref, context=context)
    graph_context = _map_or_empty(capabilities.get("graph_context"))
    operation_plan = _operation_plan(normalized_ref, change, graph_context)
    errors: list[JsonMap] = []
    if _explicit_full_replace(change):
        errors.append(
            _error(
                "full_replace_not_supported_by_apply_graph_change",
                "change",
                "apply_graph_change is a patch/merge operation that preserves omitted state; use the dedicated full-state replace workflow with a complete snapshot.",
                {
                    "requested_strategy": operation_plan.get("strategy"),
                    "replacement_workflow": "replace_graph_state",
                },
            )
        )
    if normalized_ref.get("kind") == "fx_map_graph" and not normalized_ref.get("owner_node_id"):
        errors.append(
            _error(
                "missing_owner_node_id",
                "graph_ref.owner_node_id",
                "fx_map_graph GraphChange requires owner_node_id so the referenced FX-Map resource can be edited",
            )
        )
    errors.extend(_maps(capabilities.get("unsupported_reasons")))

    operations, operation_errors = _operation_maps(change.get("operations")) if "operations" in change else ([], [])
    replace_keys = [key for key in ("nodes", "connections", "output") if key in change]
    if "operations" in change:
        if replace_keys:
            errors.append(
                _error(
                    "mixed_graph_change_modes",
                    "change",
                    "operations cannot be mixed with nodes/connections/output replace state",
                    {"replace_keys": replace_keys},
                )
            )
        errors.extend(operation_errors)
        errors.extend(_validate_graph_change_operations(operations, capabilities))
        return _validation_result(
            not errors,
            normalized_ref,
            graph_context,
            change,
            errors,
            capabilities=capabilities,
            operation_plan=operation_plan,
        )

    allowed = set(_string_list(capabilities.get("allowed_definitions")))
    graph_kind = _text(graph_context.get("graph_kind")) or ""
    contract_kind = _contract_kind(graph_context)
    node_ids: list[str] = []
    definitions_by_node: dict[str, JsonMap] = {}
    for index, node in enumerate(_maps(change.get("nodes"))):
        node_id = _text(node.get("id"))
        definition = _text(node.get("definition"))
        if not node_id:
            errors.append(_error("missing_node_id", f"change.nodes[{index}].id", "node id is required"))
            continue
        node_ids.append(node_id)
        if not definition:
            if not _node_update_without_definition_allowed(normalized_ref, node):
                errors.append(
                    _error("missing_definition", f"change.nodes[{index}].definition", "node definition is required")
                )
            continue
        if definition not in allowed:
            errors.append(
                _error(
                    "definition_not_allowed_in_graph_context",
                    f"change.nodes[{index}].definition",
                    "definition '{}' is not allowed in graph kind '{}' contract '{}'".format(
                        definition,
                        graph_kind,
                        contract_kind,
                    ),
                    {
                        "definition": definition,
                        "graph_kind": graph_kind,
                        "contract": contract_kind,
                    },
                )
            )
            continue
        definition_info = _definition_for_context(definition, graph_context)
        if isinstance(definition_info, dict):
            definitions_by_node[node_id] = definition_info
            if graph_kind == "substance_graph" and definition != "sbs::compositing::output":
                errors.extend(
                    _validate_declared_node_parameters(
                        node,
                        definition_info,
                        f"change.nodes[{index}].parameters",
                    )
                )
            if graph_kind == "function_graph":
                errors.extend(
                    _validate_instance_node_parameters_can_lower(
                        node,
                        definition_info,
                        f"change.nodes[{index}].parameters",
                    )
                )
        errors.extend(_validate_node_parameters(node, definition, f"change.nodes[{index}].parameters"))
    node_set = set(node_ids)

    for index, connection in enumerate(_maps(change.get("connections"))):
        source, source_port = _connection_endpoint(connection, "from")
        target, target_port = _connection_endpoint(connection, "to")
        source_is_builtin = _connection_has_builtin_endpoint(connection, "from") or _is_builtin_endpoint(source)
        if graph_kind == "substance_graph":
            if not source:
                errors.append(
                    _error("missing_connection_source", f"change.connections[{index}].from", "source node is required")
                )
            elif source in node_set:
                errors.extend(
                    _validate_port(
                        definitions_by_node.get(str(source)),
                        "outputs",
                        source_port,
                        f"change.connections[{index}].from_output",
                    )
                )
            if not target:
                errors.append(
                    _error("missing_connection_target", f"change.connections[{index}].to", "target node is required")
                )
            elif target in node_set:
                errors.extend(
                    _validate_port(
                        definitions_by_node.get(str(target)),
                        "inputs",
                        target_port,
                        f"change.connections[{index}].to_input",
                    )
                )
            continue
        if source_is_builtin:
            if source not in _builtin_ids(graph_context):
                errors.append(
                    _error(
                        "unknown_builtin",
                        f"change.connections[{index}].from.builtin",
                        "builtin is not available in this function contract",
                        {"builtin": source},
                    )
                )
        elif source in node_set:
            errors.extend(
                _validate_port(
                    definitions_by_node.get(str(source)),
                    "outputs",
                    source_port,
                    f"change.connections[{index}].from_output",
                )
            )
        if target in node_set:
            errors.extend(
                _validate_port(
                    definitions_by_node.get(str(target)), "inputs", target_port, f"change.connections[{index}].to_input"
                )
            )

    output = _output_node_id(change.get("output"))
    output_contract = _map_or_empty(capabilities.get("output_contract"))
    if output_contract.get("required") and not output and operation_plan["strategy"] != "patch_property_graph":
        errors.append(
            _error("output_required_by_contract", "change.output", "function contract requires an output node")
        )
    if output and output in definitions_by_node:
        output_definition = definitions_by_node[output]
        output_type = _definition_default_output_type(output_definition)
        expected_type = _text(output_contract.get("type"))
        blocked_reason = _root_blocked_reason(output_definition, contract_kind)
        if blocked_reason:
            error_code = (
                "output_type_mismatch" if blocked_reason == "output_type_mismatch" else "output_contract_blocked"
            )
            expected_type = _text(output_contract.get("type"))
            errors.append(
                _error(
                    error_code,
                    "change.output",
                    "output node is blocked by contract '{}' because '{}'".format(contract_kind, blocked_reason),
                    {
                        "definition": output_definition.get("definition_id"),
                        "contract": contract_kind,
                        "reason": blocked_reason,
                        "suggested_root_definitions": _suggested_root_definitions(capabilities, expected_type),
                    },
                )
            )
        if (
            not blocked_reason
            and expected_type
            and expected_type not in {"unknown", "value", "texture", "owner_output_type"}
            and output_type
            and not _types_compatible(output_type, expected_type)
        ):
            errors.append(
                _error(
                    "output_type_mismatch",
                    "change.output",
                    "output node type '{}' does not satisfy contract output '{}'".format(output_type, expected_type),
                    {
                        "actual": output_type,
                        "expected": expected_type,
                        "suggested_root_definitions": _suggested_root_definitions(capabilities, expected_type),
                    },
                )
            )
    if graph_context["graph_kind"] == "substance_graph" and output:
        errors.append(
            _error(
                "graph_output_not_supported",
                "change.output",
                "package graph output changes are not supported by GraphChange yet",
            )
        )

    return _validation_result(
        not errors,
        normalized_ref,
        graph_context,
        change,
        errors,
        capabilities=capabilities,
        operation_plan=operation_plan,
    )


def _validate_graph_change_operations(operations: list[JsonMap], capabilities: JsonMap) -> list[JsonMap]:
    """Validate public partial-edit operations."""
    errors: list[JsonMap] = []
    allowed_ops = set(_string_list(capabilities.get("apply_supported_changes")))
    allowed_definitions = set(_string_list(capabilities.get("allowed_definitions")))
    graph_context = _map_or_empty(capabilities.get("graph_context"))
    graph_kind = _text(graph_context.get("graph_kind")) or ""
    definitions_by_node: dict[str, JsonMap] = {}
    for index, operation in enumerate(operations):
        op = _text(operation.get("op"))
        path = "change.operations[{}]".format(index)
        if not op:
            errors.append(_error("missing_operation", "{}.op".format(path), "operation op is required"))
            continue
        if op not in allowed_ops:
            errors.append(
                _error("operation_not_supported", "{}.op".format(path), "operation '{}' is not supported".format(op))
            )
            continue
        if op == "ensure_node":
            node_id = _text(operation.get("id") or operation.get("node"))
            definition = _text(operation.get("definition"))
            if not node_id:
                errors.append(_error("missing_node_id", "{}.id".format(path), "node id is required"))
            if graph_kind == "substance_graph" and not definition:
                errors.append(_error("missing_definition", "{}.definition".format(path), "node definition is required"))
            if definition:
                if definition not in allowed_definitions:
                    errors.append(
                        _error(
                            "definition_not_allowed_in_graph_context",
                            "{}.definition".format(path),
                            "definition '{}' is not allowed".format(definition),
                        )
                    )
                else:
                    definition_info = _definition_for_context(definition, graph_context)
                    if isinstance(definition_info, dict) and node_id:
                        definitions_by_node[node_id] = definition_info
                        if graph_kind == "function_graph":
                            errors.extend(
                                _validate_instance_node_parameters_can_lower(
                                    operation,
                                    definition_info,
                                    "{}.parameters".format(path),
                                )
                            )
            errors.extend(_validate_operation_parameters(operation, definition, "{}.parameters".format(path)))
            continue
        if op == "set_parameter":
            if not _text(operation.get("node")):
                errors.append(_error("missing_node_id", "{}.node".format(path), "node is required"))
            if not _text(operation.get("parameter")):
                errors.append(_error("missing_parameter", "{}.parameter".format(path), "parameter is required"))
            if "value" not in operation:
                errors.append(_error("missing_value", "{}.value".format(path), "value is required"))
            continue
        if op == "set_property_graph":
            if not _text(operation.get("node")):
                errors.append(_error("missing_node_id", "{}.node".format(path), "node is required"))
            if not _text(operation.get("property") or operation.get("property_id")):
                errors.append(_error("missing_property", "{}.property".format(path), "property is required"))
            continue
        if op == "ensure_connection":
            source, source_port = _connection_endpoint(operation, "from")
            target, target_port = _connection_endpoint(operation, "to")
            if not source:
                errors.append(_error("missing_connection_source", "{}.from".format(path), "source node is required"))
            elif source in definitions_by_node:
                errors.extend(
                    _validate_port(
                        definitions_by_node.get(source), "outputs", source_port, "{}.from_output".format(path)
                    )
                )
            if not target:
                errors.append(_error("missing_connection_target", "{}.to".format(path), "target node is required"))
            elif target in definitions_by_node:
                errors.extend(
                    _validate_port(definitions_by_node.get(target), "inputs", target_port, "{}.to_input".format(path))
                )
            continue
        if op == "remove_connection":
            target, _target_port = _connection_endpoint(operation, "to")
            if not target:
                errors.append(_error("missing_connection_target", "{}.to".format(path), "target node is required"))
            continue
        if op == "move_node":
            if not _text(operation.get("node")):
                errors.append(_error("missing_node_id", "{}.node".format(path), "node is required"))
            if "position" not in operation:
                errors.append(_error("missing_position", "{}.position".format(path), "position is required"))
            continue
        if op == "set_output":
            if not _text(operation.get("node")):
                errors.append(_error("missing_node_id", "{}.node".format(path), "node is required"))
            if graph_kind == "substance_graph":
                errors.append(
                    _error(
                        "operation_not_supported",
                        "{}.op".format(path),
                        "set_output is only supported for nested graphs",
                    )
                )
    return errors


def _validate_operation_parameters(operation: JsonMap, definition: str | None, path: str) -> list[JsonMap]:
    if "parameters" not in operation:
        return []
    if definition is None:
        return []
    return _validate_node_parameters({"parameters": operation.get("parameters")}, definition, path)


def _validate_instance_node_parameters_can_lower(node: JsonMap, definition: JsonMap, path: str) -> list[JsonMap]:
    creation = _map_or_empty(definition.get("creation"))
    if creation.get("method") != "create_instance_node":
        return []
    parameters = node.get("parameters")
    if not isinstance(parameters, dict):
        return []
    errors: list[JsonMap] = []
    for parameter_id in parameters:
        port = _input_port(definition, str(parameter_id))
        if port is None or _constant_definition_for_port(port) is None:
            errors.append(
                _error(
                    "unsupported_instance_parameter",
                    f"{path}.{parameter_id}",
                    "Function graph instance node parameters must target connectable float/int inputs that can be lowered to constant nodes.",
                    {"parameter": parameter_id, "definition": definition.get("definition_id")},
                )
            )
    return errors


def _input_port(definition: JsonMap, port_id: str) -> JsonMap | None:
    ports = _map_or_empty(definition.get("ports"))
    inputs = ports.get("inputs")
    if isinstance(inputs, dict):
        for canonical, port in inputs.items():
            if not isinstance(port, dict):
                continue
            aliases = _string_list(port.get("aliases"))
            if port_id == str(canonical) or port_id == _text(port.get("id")) or port_id in aliases:
                return {"id": str(canonical), **port}
        return None
    for port in _maps(inputs):
        canonical = _text(port.get("id"))
        aliases = _string_list(port.get("aliases"))
        if canonical and (port_id == canonical or port_id in aliases):
            return port
    return None


def _constant_definition_for_port(port: JsonMap | None) -> str | None:
    if not isinstance(port, dict) or port.get("connectable") is False:
        return None
    port_type = port.get("type")
    if isinstance(port_type, list):
        port_type = port_type[0] if port_type else None
    return {
        "float": "sbs::function::const_float1",
        "float1": "sbs::function::const_float1",
        "float2": "sbs::function::const_float2",
        "float3": "sbs::function::const_float3",
        "float4": "sbs::function::const_float4",
        "int": "sbs::function::const_int1",
        "int1": "sbs::function::const_int1",
        "int2": "sbs::function::const_int2",
        "int3": "sbs::function::const_int3",
        "int4": "sbs::function::const_int4",
    }.get(str(port_type or ""))


def graph_change_to_state(*, graph_ref: JsonMap, change: JsonMap) -> JsonMap:
    """Convert a node-property function graph change into the internal property graph state."""
    normalized_ref = normalize_graph_ref(graph_ref)
    if normalized_ref["kind"] != "node_property_graph":
        raise GraphChangeValidationError("graph_change_to_state only supports node_property_graph")
    change = normalize_graph_change_parameters(change)
    definitions_by_node = _definitions_by_change_node(change)
    return {
        "target": {
            "graph_identifier": normalized_ref.get("parent_graph"),
            "node_id": normalized_ref["owner_node_id"],
            "property": normalized_ref["property_id"],
        },
        "graph_type": normalized_ref.get("graph_type") or FUNCTION_GRAPH_TYPE,
        "nodes": [_state_node(node) for node in _maps(change.get("nodes"))],
        "connections": [
            _connection_state(connection, definitions_by_node=definitions_by_node)
            for connection in _maps(change.get("connections"))
        ],
        "output": {"node": _output_node_id(change.get("output"))} if _output_node_id(change.get("output")) else None,
    }


def _definitions_by_change_node(change: JsonMap) -> dict[str, JsonMap]:
    result: dict[str, JsonMap] = {}
    for node in _maps(change.get("nodes")):
        node_id = _text(node.get("id"))
        definition = _text(node.get("definition"))
        if not node_id or not definition:
            continue
        matches = node_definitions_by_id(definition)
        if matches:
            result[node_id] = matches[0]
    return result


def _state_node(node: JsonMap) -> JsonMap:
    result = dict(node)
    definition_id = _text(node.get("definition"))
    host_creation = _host_creation_for_definition(definition_id) if definition_id else None
    if host_creation:
        result["host_creation"] = host_creation
    return result


def _host_creation_for_definition(definition_id: str) -> JsonMap | None:
    if not definition_id:
        return None
    matches = node_definitions_by_id(definition_id)
    function_library = next((node for node in matches if node.get("kind") == "function-library"), None)
    if not function_library:
        return None
    creation = function_library.get("creation")
    if not isinstance(creation, dict):
        return None
    resource_url = _text(creation.get("resource_url"))
    if not resource_url:
        return None
    return {
        "kind": "function_graph_resource_instance",
        "resource_url": resource_url,
        **_compact(
            {
                "package_hint": creation.get("package"),
                "creation": creation,
            }
        ),
    }


def normalize_graph_ref(graph_ref: JsonMap | None) -> JsonMap:
    """Normalize a graph reference to the public graph location model."""
    if not isinstance(graph_ref, dict):
        return {"kind": "package_graph"}
    kind = _text(graph_ref.get("kind")) or "package_graph"
    aliases = {
        "node_property": "node_property_graph",
        "substance_graph": "package_graph",
        "function_graph": "node_property_graph",
    }
    kind = aliases.get(kind, kind)
    if kind == "package_graph":
        return {"kind": kind, **_compact({"graph_identifier": _text(graph_ref.get("graph_identifier"))})}
    if kind == "fx_map_graph":
        owner_node_id = _text(
            graph_ref.get("owner_node_id")
            or graph_ref.get("node_id")
            or graph_ref.get("owner")
            or graph_ref.get("owner_id")
            or graph_ref.get("ownerNodeId")
            or graph_ref.get("nodeId")
        )
        return {
            "kind": kind,
            **_compact(
                {
                    "graph_identifier": _text(
                        graph_ref.get("graph_identifier")
                        or graph_ref.get("parent_graph")
                        or graph_ref.get("graph")
                        or graph_ref.get("parent")
                    ),
                    "owner_node_id": owner_node_id,
                    "graph_type": _text(graph_ref.get("graph_type")) or FX_MAP_GRAPH_TYPE,
                }
            ),
        }
    if kind != "node_property_graph":
        raise GraphChangeValidationError("graph_ref.kind must be package_graph, node_property_graph, or fx_map_graph")
    owner_node_id = _text(
        graph_ref.get("owner_node_id")
        or graph_ref.get("node_id")
        or graph_ref.get("owner")
        or graph_ref.get("owner_id")
        or graph_ref.get("ownerNodeId")
        or graph_ref.get("nodeId")
    )
    property_id = _text(
        graph_ref.get("property_id")
        or graph_ref.get("property")
        or graph_ref.get("input")
        or graph_ref.get("parameter")
    )
    if not owner_node_id or not property_id:
        raise GraphChangeValidationError("node_property_graph requires owner_node_id and property_id")
    return {
        "kind": kind,
        **_compact(
            {
                "parent_graph": _text(
                    graph_ref.get("parent_graph")
                    or graph_ref.get("graph_identifier")
                    or graph_ref.get("graph")
                    or graph_ref.get("parent")
                ),
                "owner_node_id": owner_node_id,
                "owner_definition": _text(graph_ref.get("owner_definition") or graph_ref.get("owner_definition_id")),
                "property_id": property_id,
                "graph_type": _text(graph_ref.get("graph_type")) or FUNCTION_GRAPH_TYPE,
            }
        ),
    }


def resolve_graph_context(*, graph_ref: JsonMap | None = None, context: JsonMap | str | None = None) -> JsonMap:
    """Resolve graph kind and function contract without guessing from display text."""
    normalized_ref = normalize_graph_ref(graph_ref)
    explicit = _explicit_graph_context(context)
    if explicit is not None:
        return explicit
    if normalized_ref["kind"] == "package_graph":
        return _graph_context(
            "substance_graph", _contract("none", output={"type": "texture"}, required=False), "graph_ref"
        )
    if normalized_ref["kind"] == "fx_map_graph":
        return _graph_context(
            "fx_map_graph", _contract("none", output={"type": "texture"}, required=False), "graph_ref"
        )

    owner_definition = _text(normalized_ref.get("owner_definition"))
    property_id = _text(normalized_ref.get("property_id"))
    if owner_definition and property_id:
        contract = _function_contract_for_property(owner_definition, property_id)
        if contract is not None:
            return _graph_context("function_graph", contract, "function_contract_metadata")
        return _graph_context(
            "function_graph",
            _contract("unknown", output={"type": "unknown"}, required=True),
            "function_contract_metadata_missing",
            unsupported_reasons=[
                _error(
                    "unknown_function_contract",
                    "graph_ref",
                    "no FunctionContract metadata for '{}.{}'".format(owner_definition, property_id),
                    {"owner_definition": owner_definition, "property_id": property_id},
                )
            ],
        )
    if property_id == "perpixel":
        return _graph_context(
            "function_graph",
            _function_contract_for_property("sbs::compositing::pixelprocessor", "perpixel"),
            "property_id",
        )
    return _graph_context(
        "function_graph",
        _contract("unknown", output={"type": "unknown"}, required=True),
        "default",
        unsupported_reasons=[
            _error(
                "unknown_function_contract",
                "graph_ref",
                "node property graph requires owner_definition and property_id to resolve its FunctionContract",
            )
        ],
    )


def resolve_context(*, graph_ref: JsonMap | None = None, context: JsonMap | str | None = None) -> JsonMap:
    """Backward-compatible alias for callers still importing resolve_context."""
    return resolve_graph_context(graph_ref=graph_ref, context=context)


def _explicit_graph_context(context: JsonMap | str | None) -> JsonMap | None:
    if isinstance(context, str):
        legacy = _legacy_context_contract(context)
        return _graph_context(_text(legacy.get("graph_kind")) or "function_graph", _map_or_empty(legacy.get("contract")), "caller")
    if not isinstance(context, dict):
        return None
    graph_kind = _text(context.get("graph_kind"))
    contract_value = _map_or_empty(context.get("contract"))
    if graph_kind:
        contract = _contract_from_mapping(contract_value)
        if context.get("allowed_context_scopes"):
            contract["allowed_context_scopes"] = _string_list(context.get("allowed_context_scopes"))
        return _graph_context(graph_kind, contract, _text(context.get("source")) or "caller")
    legacy_kind = _text(context.get("kind"))
    if legacy_kind:
        legacy = _legacy_context_contract(legacy_kind)
        return _graph_context(
            _text(legacy.get("graph_kind")) or "function_graph",
            _map_or_empty(legacy.get("contract")),
            _text(context.get("source")) or "caller",
        )
    return None


def _legacy_context_contract(kind: str) -> JsonMap:
    if kind == "compositing":
        return {
            "graph_kind": "substance_graph",
            "contract": _contract("none", output={"type": "texture"}, required=False),
        }
    if kind == "sdf_function":
        return {
            "graph_kind": "function_graph",
            "contract": _function_contract_for_property("sbs::library::shape_splatter_v2", "pattern_sdf_function"),
        }
    if kind == "pixel_processor":
        return {
            "graph_kind": "function_graph",
            "contract": _function_contract_for_property("sbs::compositing::pixelprocessor", "perpixel"),
        }
    if kind == "value_processor":
        return {
            "graph_kind": "function_graph",
            "contract": _function_contract_for_property("sbs::compositing::valueprocessor", "function"),
        }
    if kind == "fx_map":
        return {"graph_kind": "fx_map_graph", "contract": _contract("none", output={"type": "texture"}, required=False)}
    return {
        "graph_kind": "function_graph",
        "contract": _contract("parameter_function", output={"type": "value"}, required=True),
    }


def _function_contract_for_property(owner_definition: str, property_id: str) -> JsonMap | None:
    for contract in _function_contracts().values():
        if contract.get("owner_definition_id") == owner_definition and contract.get("property_id") == property_id:
            return _contract_from_mapping(contract)
    return None


def _contract_from_mapping(value: JsonMap) -> JsonMap:
    kind = _text(value.get("kind")) or "none"
    output: JsonMap = _map_or_empty(value.get("output")) or {"type": _text(value.get("output_type")) or "unknown"}
    contract = _contract(
        kind,
        output=output,
        required=bool(value.get("required", kind not in {"none"})),
        builtins=_builtins(value.get("builtins")),
        allowed_context_scopes=_string_list(value.get("allowed_context_scopes")) or [GENERIC_FUNCTION_SCOPE],
        allowed_families=_string_list(value.get("allowed_node_families") or value.get("allowed_families")),
    )
    for key in ("owner_definition_id", "host_definition", "property_id", "type_binding", "type_matrix"):
        if value.get(key) is not None:
            contract[key] = value[key]
    return contract


def _contract(
    kind: str,
    *,
    output: JsonMap,
    required: bool = True,
    builtins: JsonMap | list[JsonMap] | None = None,
    allowed_context_scopes: list[str] | None = None,
    allowed_families: list[str] | None = None,
) -> JsonMap:
    return {
        "kind": kind,
        "output": output,
        "required": required,
        "builtins": builtins if builtins is not None else {},
        "allowed_context_scopes": allowed_context_scopes or [GENERIC_FUNCTION_SCOPE],
        "allowed_families": allowed_families or [],
    }


def _graph_context(
    graph_kind: str,
    contract: JsonMap | None,
    source: str,
    *,
    unsupported_reasons: list[JsonMap] | None = None,
) -> JsonMap:
    reasons = unsupported_reasons or []
    return {
        "graph_kind": graph_kind,
        "contract": contract or _contract("none", output={"type": "unknown"}, required=False),
        "source": source,
        "confidence": "low" if reasons or source in {"default", "function_contract_metadata_missing"} else "high",
        "unsupported_reasons": reasons,
    }


def _allowed_node_definitions(graph_context: JsonMap, intent: str | None) -> list[JsonMap]:
    graph_kind = str(graph_context["graph_kind"])
    contract_kind = _contract_kind(graph_context)
    if graph_kind == "fx_map_graph":
        return _fx_map_node_definitions()
    nodes = []
    for node in node_definitions():
        if _node_allowed_in_graph_context(node, graph_context):
            nodes.append(node)
    sdf_family = _sdf_intent_definition_family(intent)
    if contract_kind == "sdf_function" and sdf_family:
        return [node for node in nodes if _sdf_node_matches_family(node, sdf_family)]
    if _is_sdf_intent(intent) or contract_kind == "sdf_function":
        generic_nodes = [node for node in nodes if _has_context(node, GENERIC_FUNCTION_SCOPE)]
        sdf_nodes = [node for node in nodes if _is_sdf_node(node)]
        return _dedupe_nodes([*generic_nodes, *sdf_nodes])
    return _dedupe_nodes(nodes)


def _node_allowed_in_graph_context(node: JsonMap, graph_context: JsonMap) -> bool:
    graph_kind = str(graph_context["graph_kind"])
    if graph_kind == "substance_graph":
        return "SDSBSCompGraph" in _string_list(node.get("graph_scopes"))
    if graph_kind != "function_graph":
        return False
    if node.get("graph_kind") and node.get("graph_kind") != "function_graph":
        return False
    if node.get("graph_type") and node.get("graph_type") != FUNCTION_GRAPH_TYPE:
        return False
    contract = _contract_map(graph_context)
    allowed_families = set(_string_list(contract.get("allowed_families")))
    node_families = set(_string_list(node.get("families")))
    if allowed_families and node_families & allowed_families:
        return True
    allowed_scopes = set(_string_list(contract.get("allowed_context_scopes")) or [GENERIC_FUNCTION_SCOPE])
    return any(scope.get("id") in allowed_scopes for scope in _context_scopes(node))


def _has_context(node: JsonMap, context_id: str) -> bool:
    return any(scope.get("id") == context_id for scope in _context_scopes(node))


def _definition_for_context(definition_id: str, graph_context: JsonMap) -> JsonMap | None:
    matches = node_definitions_by_id(definition_id)
    if not matches:
        return None
    for node in sorted(matches, key=lambda item: _definition_context_rank(item, graph_context)):
        if _node_allowed_in_graph_context(node, graph_context):
            return node
    return matches[0]


def _definition_context_rank(node: JsonMap, graph_context: JsonMap) -> int:
    graph_kind = str(graph_context["graph_kind"])
    kind = str(node.get("kind") or "")
    if graph_kind == "function_graph" and kind.startswith("function-"):
        return 0
    if graph_kind == "substance_graph" and kind in {"atomic", "library"}:
        return 0
    return 1


def _is_sdf_node(node: JsonMap) -> bool:
    if SDF_FUNCTION_FAMILY in _string_list(node.get("families")):
        return True
    availability = _map_or_empty(node.get("availability"))
    requires_context = _string_list(availability.get("requires_context"))
    return SDF_VIEWER_SCOPE in requires_context


def _node_capability(node: JsonMap) -> JsonMap:
    return {
        "definition": node.get("definition_id"),
        "display_name": node.get("display_name"),
        "category": node.get("category"),
        "graph_scopes": node.get("graph_scopes", []),
        "graph_kind": node.get("graph_kind"),
        "graph_type": node.get("graph_type"),
        "families": node.get("families", []),
        "context_scopes": node.get("context_scopes", []),
        "ports_evidence": _ports_evidence_status(node),
        "root": node.get("root", {}),
        "creation": node.get("creation", {"method": "create_node"}),
        "reference_uri": f"{AUTHORING_PREFIX}/node/{node.get('kind')}/{node.get('slug')}",
    }


def _validate_port(definition: JsonMap | None, direction: str, port_id: str | None, path: str) -> list[JsonMap]:
    if not isinstance(definition, dict):
        return [_error("port_evidence_missing", path, "node definition evidence is missing")]
    allowed_ports = set(_port_aliases(definition, direction))
    if not allowed_ports:
        return [_error("port_evidence_missing", path, "node definition has no '{}' port evidence".format(direction))]
    if "*" in allowed_ports:
        return []
    if not port_id or port_id not in allowed_ports:
        return [
            _error(
                "{}_port_not_allowed".format("source" if direction == "outputs" else "target"),
                path,
                "port is not allowed for the node definition",
                {"port": port_id},
            )
        ]
    return []


def _validate_node_parameters(node: JsonMap, definition_id: str, path: str) -> list[JsonMap]:
    if definition_id != "sbs::compositing::output":
        return []
    parameters = node.get("parameters")
    if not isinstance(parameters, dict):
        return []
    errors: list[JsonMap] = []
    for key in ("component", "components", "color_space", "colorSpace"):
        if key in parameters:
            errors.append(
                _error(
                    "orphan_output_usage_metadata",
                    f"{path}.{key}",
                    "output usage metadata must be nested inside public parameter 'usage'",
                    {"parameter": key, "public_parameter": "usage", "host_parameter": "usages"},
                )
            )
    has_usage = "usage" in parameters
    has_usages = "usages" in parameters
    if has_usage and has_usages:
        errors.append(
            _error(
                "ambiguous_output_usage_parameter",
                path,
                "output usage must be declared once; use public parameter 'usage'",
                {"public_parameter": "usage", "host_parameter": "usages"},
            )
        )
        return errors
    key = "usage" if has_usage else "usages" if has_usages else None
    if key is None:
        return errors
    valid, reason = _output_usage_parameter_valid(parameters[key])
    if not valid:
        errors.append(
            _error(
                "invalid_output_usage_value",
                f"{path}.{key}",
                "output usage must be a string; declare GraphChange output metadata with public parameter 'usage'",
                {"reason": reason, "public_parameter": "usage", "host_parameter": "usages"},
            )
        )
    return errors


def _validate_declared_node_parameters(node: JsonMap, definition: JsonMap, path: str) -> list[JsonMap]:
    parameters = node.get("parameters")
    if not isinstance(parameters, dict):
        return []
    known = _parameters_by_id(definition)
    if not known:
        return []
    errors: list[JsonMap] = []
    for parameter_id, parameter_value in parameters.items():
        parameter = known.get(str(parameter_id))
        if parameter is None:
            candidates = sorted(known)
            suggestion = _parameter_suggestions(str(parameter_id), candidates)
            errors.append(
                _error(
                    "unknown_parameter",
                    f"{path}.{parameter_id}",
                    "Parameter '{}' is not declared on node definition '{}'.".format(
                        parameter_id,
                        definition.get("definition_id"),
                    ),
                    {
                        "parameter": parameter_id,
                        "definition": definition.get("definition_id"),
                        "available": candidates,
                        **({"did_you_mean": suggestion[0]} if suggestion else {}),
                    },
                )
            )
            continue
        value = _parameter_raw_value(parameter_value)
        enum = parameter.get("enum")
        if isinstance(enum, dict) and isinstance(enum.get("options"), list):
            allowed = [option.get("value") for option in _maps(enum.get("options"))]
            if value not in allowed:
                errors.append(
                    _error(
                        "invalid_enum_value",
                        f"{path}.{parameter_id}",
                        "Enum parameter '{}' must use one of the declared option values.".format(parameter_id),
                        {
                            "parameter": parameter_id,
                            "value": value,
                            "allowed_values": allowed,
                            "options": enum.get("options"),
                        },
                    )
                )
        if _unsupported_parameter_value_shape(value, parameter):
            errors.append(
                _error(
                    "unsupported_parameter_value_shape",
                    f"{path}.{parameter_id}",
                    "Parameter '{}' value shape is not supported by GraphChange.".format(parameter_id),
                    {
                        "parameter": parameter_id,
                        "type": parameter.get("type"),
                        "guidance": "Use scalar values or typed scalar vectors; inspect node reference for a dedicated schema/helper.",
                    },
                )
            )
    return errors


def _parameters_by_id(definition: JsonMap) -> dict[str, JsonMap]:
    parameters = definition.get("parameters")
    if isinstance(parameters, dict):
        return {str(key): value for key, value in parameters.items() if isinstance(value, dict)}
    return {str(item["id"]): item for item in _maps(parameters) if item.get("id")}


def _parameter_suggestions(parameter_id: str, candidates: list[str]) -> list[str]:
    if "width" in parameter_id and "distance" in candidates:
        return ["distance"]
    return get_close_matches(parameter_id, candidates, n=1)


def _parameter_raw_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _unsupported_parameter_value_shape(value: JsonValue, parameter: JsonMap) -> bool:
    if isinstance(value, dict):
        return True
    if not isinstance(value, list):
        return False
    if any(isinstance(item, (dict, list)) for item in value):
        return True
    parameter_types = _string_list(parameter.get("type"))
    return not any(
        parameter_type in {"float2", "float3", "float4", "int2", "int3", "int4", "color", "ColorRGBA"}
        for parameter_type in parameter_types
    )


def _output_usage_parameter_valid(value: JsonValue | OutputUsageParameterValue) -> tuple[bool, str | None]:
    if isinstance(value, str) and value.strip():
        return True, None
    if isinstance(value, dict):
        value_type = _text(value.get("value_type"))
        raw_value = value.get("value") if "value" in value else value
        if value_type and value_type not in {"string", "usage_array"}:
            return False, "value_type must be string or usage_array"
        if isinstance(raw_value, str) and raw_value.strip():
            return True, None
        if isinstance(raw_value, dict) and _text(
            raw_value.get("name") or raw_value.get("usage") or raw_value.get("id")
        ):
            return True, None
        return False, "value must be a non-empty string or usage object with name"
    if isinstance(value, list):
        return False, "arrays are not a public GraphChange output usage value"
    return False, "value must be a non-empty string"


def _port_ids(definition: JsonMap, direction: str) -> set[str]:
    return set(_port_aliases(definition, direction).values())


def _port_aliases(definition: JsonMap, direction: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    ports = _map_or_empty(definition.get("ports")).get(direction, [])
    if isinstance(ports, dict):
        for port_id, port in ports.items():
            canonical = str(port_id)
            aliases[canonical] = canonical
            if isinstance(port, dict):
                for alias in _string_list(port.get("aliases")):
                    aliases[alias] = canonical
        return aliases
    if not isinstance(ports, list):
        return aliases
    for port in ports:
        if not isinstance(port, dict) or port.get("id") is None:
            continue
        canonical = str(port["id"])
        aliases[canonical] = canonical
        for alias in _string_list(port.get("aliases")):
            aliases[alias] = canonical
    return aliases


def _canonical_port_id(definition: JsonMap | None, direction: str, port_id: str | None) -> str | None:
    if not port_id or not isinstance(definition, dict):
        return port_id
    return _port_aliases(definition, direction).get(port_id, port_id)


def _ports_evidence_status(definition: JsonMap) -> str:
    evidence = definition.get("ports_evidence")
    if isinstance(evidence, dict):
        return _text(evidence.get("status")) or "unknown"
    ports = definition.get("ports")
    if isinstance(ports, dict) and (ports.get("inputs") or ports.get("outputs")):
        return "complete"
    return "unknown"


def _output_contract(graph_context: JsonMap) -> JsonMap:
    if graph_context["graph_kind"] == "substance_graph":
        return {"required": False, "type": "texture"}
    if graph_context["graph_kind"] == "fx_map_graph":
        return {"required": False, "type": "texture"}
    contract = _contract_map(graph_context)
    output = _map_or_empty(contract.get("output")) or {"type": "unknown"}
    return {"required": bool(contract.get("required", True)), "type": _text(output.get("type")) or "unknown"}


def _supported_changes(graph_context: JsonMap) -> list[str]:
    graph_kind = graph_context["graph_kind"]
    if graph_kind == "substance_graph":
        return SUBSTANCE_GRAPH_CHANGES
    if graph_kind == "fx_map_graph":
        return FX_MAP_GRAPH_CHANGES
    return FUNCTION_GRAPH_CHANGES


def _capability_diagnostics(graph_context: JsonMap) -> list[JsonMap]:
    diagnostics: list[JsonMap] = []
    for reason in _maps(graph_context.get("unsupported_reasons")):
        diagnostics.append({"severity": "error", **reason})
    return diagnostics


def _operation_plan(graph_ref: JsonMap, change: JsonMap, graph_context: JsonMap) -> JsonMap:
    """Return the public apply-ready plan for GraphChange."""
    strategy = _apply_strategy(graph_ref, change)
    explicit_remove = _has_explicit_remove(change)
    full_replace = _explicit_full_replace(change)
    return {
        "intent": "replace_full_state" if full_replace else "patch_graph",
        "strategy": strategy,
        "preserves_unmentioned": not full_replace,
        "destructive": bool(explicit_remove or full_replace),
        **({"destructive_scope": "explicit_remove_connection"} if explicit_remove and not full_replace else {}),
        "sets_output": _sets_output(change),
        "removes_connections": explicit_remove,
        "rollback": "required",
        "host_strategy_hidden": True,
        "apply_ready": not full_replace,
        "blocking_errors": [
            {
                "code": "full_replace_not_supported_by_apply_graph_change",
                "path": "change",
                "message": "Full graph replacement is not part of the public GraphChange apply model.",
            }
        ]
        if full_replace
        else [],
        "graph_kind": graph_ref.get("kind"),
        "contract": _contract_kind(graph_context) or None,
    }


def _apply_strategy(graph_ref: JsonMap, change: JsonMap) -> str:
    if "operations" in change:
        if graph_ref["kind"] == "package_graph":
            return "patch_package_graph"
        if graph_ref["kind"] == "fx_map_graph":
            return "patch_fx_map_graph"
        return "patch_property_graph"
    if _property_graph_parameter_patch(graph_ref, change):
        if graph_ref.get("kind") == "fx_map_graph":
            return "patch_fx_map_graph"
        return "patch_property_graph"
    if graph_ref["kind"] == "package_graph":
        return "merge_package_graph"
    if not _explicit_full_replace(change):
        if graph_ref["kind"] == "fx_map_graph":
            return "patch_fx_map_graph"
        return "patch_property_graph"
    if graph_ref["kind"] == "fx_map_graph":
        return "replace_fx_map_graph"
    return "replace_property_graph"


def _sets_output(change: JsonMap) -> bool:
    operations = _maps(change.get("operations"))
    return "output" in change or any(_text(operation.get("op")) == "set_output" for operation in operations)


def _has_explicit_remove(change: JsonMap) -> bool:
    return any(_text(operation.get("op")) == "remove_connection" for operation in _maps(change.get("operations")))


def _apply_supported_changes(graph_context: JsonMap) -> list[str]:
    return list(_supported_changes(graph_context))


def _authoring_surfaces(graph_ref: JsonMap, graph_context: JsonMap) -> list[JsonMap]:
    graph_kind = graph_context.get("graph_kind")
    return [
        {
            "graph_ref": graph_ref,
            "surface_kind": graph_kind,
            "available_intents": ["patch"],
            "unavailable_intents": [
                {
                    "intent": "replace_full_state",
                    "reason": "Full replacement is separated from apply_graph_change to preserve unmentioned graph state.",
                }
            ],
            "operation_model": {
                "omitted_means": "preserve",
                "validate_means": "apply_ready",
                "host_strategy_hidden": True,
            },
        }
    ]


def _explicit_full_replace(change: JsonMap) -> bool:
    return change.get("replace_all") is True or _text(change.get("kind")) in {"full_state", "replace_all"}


def _property_graph_parameter_patch(graph_ref: JsonMap, change: JsonMap) -> bool:
    if graph_ref.get("kind") not in {"node_property_graph", "fx_map_graph"}:
        return False
    if change.get("output") is not None or _maps(change.get("connections")):
        return False
    nodes = _maps(change.get("nodes"))
    if not nodes:
        return False
    return all(isinstance(node.get("parameters"), dict) and node.get("parameters") for node in nodes)


def _node_update_without_definition_allowed(graph_ref: JsonMap, node: JsonMap) -> bool:
    if not isinstance(node.get("parameters"), dict) and "position" not in node:
        return False
    if graph_ref.get("kind") in {"node_property_graph", "fx_map_graph"}:
        return True
    return graph_ref.get("kind") == "package_graph" and _looks_like_existing_host_node_id(_text(node.get("id")))


def _looks_like_existing_host_node_id(value: str | None) -> bool:
    return bool(value and value.isdigit())


def _reference_uris(graph_context: JsonMap) -> list[str]:
    common = [
        f"{AUTHORING_PREFIX}/contracts/reference-first-policy",
        f"{AUTHORING_PREFIX}/contracts/graph-change",
        f"{AUTHORING_PREFIX}/contracts/operation-safety",
    ]
    if graph_context["graph_kind"] == "substance_graph":
        return [*common, f"{AUTHORING_PREFIX}/contracts/compositing-graph-state"]
    if graph_context["graph_kind"] == "fx_map_graph":
        return [*common, FX_MAP_GRAPH_URI]
    if _contract_kind(graph_context) == "sdf_function":
        return [
            *common,
            SDF_FUNCTION_WORKFLOW_URI,
            FUNCTION_CONTRACTS_URI,
            FUNCTION_LIVE_PROBE_RESULTS_URI,
        ]
    return [
        *common,
        FUNCTION_CONTRACTS_URI,
        FUNCTION_LIVE_PROBE_RESULTS_URI,
    ]


def _workflow_profile(graph_context: JsonMap) -> JsonMap | None:
    contract = _contract_map(graph_context)
    if contract.get("kind") != "sdf_function":
        return None
    return {
        "workflow_kind": "sdf_function",
        "workflow_uri": SDF_FUNCTION_WORKFLOW_URI,
        "mental_model": (
            "Author an SDF as a Function Graph over 3D point space P; transform P with offset, rotate, "
            "and scale nodes before evaluating primitives."
        ),
        "entrypoints": [
            "Start with 3D Viewer.sdf_scene for inspection and debugging.",
            "Use Shape Splatter v2.pattern_sdf_function when the SDF shape is ready for scattering.",
        ],
        "visual_iteration_units": SDF_VISUAL_ITERATION_UNITS,
        "debug_controls": [
            "scene_type = SDF",
            "enable_bounding_frame = true",
            "colorize_out_of_frame = true",
            "enable_sdf_isolines = true",
            "bounding_frame_size aligned with Shape Splatter v2.sdf_bounding_frame_size",
        ],
        "avoid": [
            "Do not treat 3d_texture_sdf as the Designer 16 SDF Function scene-building workflow.",
            "Do not look for SDF primitive nodes in the outer SDSBSCompGraph.",
            "Do not guess enum integer meanings; inspect enum labels in node metadata.",
        ],
    }


def _workflow_suggestions(graph_context: JsonMap, intent: str | None) -> list[JsonMap]:
    if graph_context.get("graph_kind") != "substance_graph" or not _is_sdf_intent(intent):
        return []
    return [
        {
            "workflow_kind": "sdf_function",
            "workflow_uri": SDF_FUNCTION_WORKFLOW_URI,
            "title": "SDF Function workflow",
            "reason": (
                "SDF intent in Substance Designer 16.0+ should start from the SDF Function workflow, "
                "then enter an SDSBSFunctionGraph property graph."
            ),
            "entry_nodes": [
                {
                    "definition": "sbs::library::3d_viewer",
                    "role": "sdf_function_debug_entrypoint",
                    "property_id": "sdf_scene",
                    "reference_uri": f"{AUTHORING_PREFIX}/node/library/3d_viewer",
                },
                {
                    "definition": "sbs::library::shape_splatter_v2",
                    "role": "sdf_function_production_consumer",
                    "property_id": "pattern_sdf_function",
                    "reference_uri": f"{AUTHORING_PREFIX}/node/library/shape_splatter_v2",
                },
            ],
            "avoid": [
                "Do not treat 3d_texture_sdf as the SDF Function scene-building entry point; it belongs to the 3D texture / volume render workflow.",
                "Do not search for SDF primitive nodes directly in the outer SDSBSCompGraph; inspect the node property graph instead.",
            ],
            "next_steps": [
                "Read the workflow_uri with get_reference.",
                "Create or inspect a 3D Viewer node, then use get_node graph_surfaces.sdf_scene.",
                "Call get_authoring_plan before requesting concrete SDF graph capabilities.",
            ],
        }
    ]


def _authoring_plan_required_evidence(sdf_plan: bool) -> list[str]:
    evidence = [
        "Inspect the current graph with get_graph.",
        "Read returned workflow and node references with get_reference.",
        "Preview current renderable outputs before the first visual mutation.",
    ]
    if sdf_plan:
        evidence.append("Use get_node on 3D Viewer or Shape Splatter v2 to obtain the concrete SDF property graph.")
    return evidence


def _authoring_plan_preview_targets(graph_ref: JsonMap, sdf_plan: bool) -> list[JsonMap]:
    targets: list[JsonMap] = []
    if graph_ref.get("kind") == "package_graph" and graph_ref.get("graph_identifier"):
        targets.append(
            {
                "graph_identifier": graph_ref["graph_identifier"],
                "preview_type": "graph_3d_view",
                "purpose": "inspect current visual state before authoring",
            }
        )
    if sdf_plan:
        targets.extend(
            [
                {
                    "definition": "sbs::library::3d_viewer",
                    "node_output_id": "output",
                    "purpose": "preview SDF function silhouette before downstream composition",
                },
                {
                    "definition": "sbs::library::shape_splatter_v2",
                    "node_output_id": "sdf_color",
                    "purpose": "verify SDF contribution is readable in Shape Splatter output",
                },
                {
                    "definition": "sbs::library::shape_splatter_v2",
                    "node_output_id": "height",
                    "purpose": "verify scattered SDF height contribution before material composition",
                },
            ]
        )
    return targets


def _authoring_plan_next_tools(graph_ref: JsonMap, workflow_refs: list[str]) -> list[JsonMap]:
    tools = [*reference_next_tools(workflow_refs)]
    if graph_ref:
        tools.append(tool_hint("get_graph", {"graph_ref": graph_ref}))
    if graph_ref.get("kind") == "package_graph" and graph_ref.get("graph_identifier"):
        tools.append(tool_hint("get_preview", {"graph_identifier": graph_ref["graph_identifier"]}))
    return _dedupe_next_tools(tools)


def _planning_next_tools(graph_ref: JsonMap, intent: str | None, reference_uris: list[str]) -> list[JsonMap]:
    tools = [
        *reference_next_tools(reference_uris),
        tool_hint("get_authoring_plan", {"graph_ref": graph_ref, "intent": intent or "<intent>"}),
    ]
    return _dedupe_next_tools(tools)


def _definition_filter(graph_context: JsonMap, intent: str | None) -> JsonMap | None:
    family = _sdf_intent_definition_family(intent)
    if _contract_kind(graph_context) != "sdf_function" or not family:
        return None
    return {
        "contract": "sdf_function",
        "family": family,
        "source": "intent",
    }


def _sdf_intent_definition_family(intent: str | None) -> str | None:
    text = (_text(intent) or "").lower()
    terms = set(re.findall(r"[a-z0-9_]+", text))
    if terms & {"primitive", "primitives", "shape", "shapes"}:
        return "primitive"
    if terms & {"operator", "operators", "op", "ops", "boolean", "union", "subtraction", "intersection"}:
        return "operator"
    if terms & {"material", "materials", "color", "roughness", "metalness", "metallic", "id"}:
        return "material"
    if terms & {"transform", "transforms", "offset", "rotate", "rotation", "scale", "twist"}:
        return "transform"
    return None


def _sdf_node_matches_family(node: JsonMap, family: str) -> bool:
    definition = str(node.get("definition_id") or "").lower()
    slug = str(node.get("slug") or "").lower()
    name = f"{definition} {slug}"
    if family == "primitive":
        return "3d_sdf_" in name and "_op_" not in name and "_transform_" not in name
    if family == "operator":
        return "3d_sdf_op_" in name
    if family == "material":
        return any(token in name for token in ("set_color", "set_roughness", "set_metalness", "set_material", "set_id"))
    if family == "transform":
        return "3d_sdf_transform_" in name
    return False


def _is_sdf_intent(intent: str | None) -> bool:
    text = (_text(intent) or "").lower()
    if not text:
        return False
    if text == "build_sdf_shape":
        return True
    terms = set(re.findall(r"[a-z0-9_]+", text))
    return bool({"sdf", "signed_distance_field"} & terms or "signed distance field" in text)


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _validation_result(
    valid: bool,
    graph_ref: JsonMap | None,
    graph_context: JsonMap | str | None,
    change: JsonMap | None,
    errors: list[JsonMap],
    *,
    capabilities: JsonMap | None = None,
    operation_plan: JsonMap | None = None,
) -> JsonMap:
    reference_uris = (capabilities or {}).get("reference_uris", [])
    graph_context_map = graph_context if isinstance(graph_context, dict) else {}
    next_tools = reference_next_tools(reference_uris)
    if valid:
        next_tools.append(
            tool_hint(
                "apply_graph_change",
                {
                    "graph_ref": graph_ref,
                    "context": graph_context_map,
                    "change": change,
                },
            )
        )
    return {
        "valid": valid,
        "graph_ref": graph_ref,
        "graph_context": graph_context,
        "change": change,
        "errors": errors,
        "warnings": [],
        "preflight_only": True,
        "requires_apply": bool(valid),
        "capabilities": None,
        "capability_summary": _capability_summary(capabilities),
        "operation_plan": operation_plan or {},
        "reference_uris": reference_uris,
        "next_tools": _dedupe_next_tools(next_tools),
    }


def _capability_summary(capabilities: JsonMap | None) -> JsonMap:
    if not isinstance(capabilities, dict):
        return {}
    allowed_definitions = capabilities.get("allowed_definitions")
    nodes = capabilities.get("nodes")
    return {
        "allowed_definition_count": len(allowed_definitions) if isinstance(allowed_definitions, list) else 0,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "contract_supported_changes": capabilities.get("contract_supported_changes", []),
        "apply_supported_changes": capabilities.get("apply_supported_changes", []),
        "authoring_surfaces": capabilities.get("authoring_surfaces", []),
        "output_contract": capabilities.get("output_contract", {}),
        "builtins": capabilities.get("builtins", {}),
        "unsupported_reasons": capabilities.get("unsupported_reasons", []),
        "reference_uris": capabilities.get("reference_uris", []),
    }


def _capability_next_tools(graph_ref: JsonMap, graph_context: JsonMap, reference_uris: list[str]) -> list[JsonMap]:
    next_tools = [
        *reference_next_tools(reference_uris),
        tool_hint(
            "validate_graph_change",
            {
                "graph_ref": graph_ref,
                "context": graph_context,
                "change": "<graph_change>",
            },
        ),
    ]
    if graph_context.get("graph_kind") in {"function_graph", "fx_map_graph"}:
        next_tools.append(
            tool_hint(
                "replace_graph_state",
                {
                    "graph_ref": graph_ref,
                    "state": "<complete_graph_state>",
                    "expected_current_hash": "<state_hash_from_get_graph>",
                },
            )
        )
    return _dedupe_next_tools(next_tools)


def _dedupe_next_tools(next_tools: list[JsonMap]) -> list[JsonMap]:
    seen: set[tuple[str, str]] = set()
    deduped: list[JsonMap] = []
    for item in next_tools:
        key = (str(item.get("tool")), repr(item.get("args", {})))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _definition_default_output_type(definition: JsonMap) -> str | None:
    root = _map_or_empty(definition.get("root"))
    root_type = _text(root.get("output_type"))
    if root_type:
        return root_type
    output_id = _text(root.get("default_output")) or "unique_filter_output"
    ports = _map_or_empty(definition.get("ports")).get("outputs", [])
    if isinstance(ports, dict):
        port = ports.get(output_id)
        if isinstance(port, dict):
            types = _string_list(port.get("type"))
            return types[0] if types else _text(port.get("type"))
    for port in ports if isinstance(ports, list) else []:
        if isinstance(port, dict) and port.get("id") == output_id:
            types = _string_list(port.get("type"))
            return types[0] if types else None
    return None


def _root_blocked_reason(definition: JsonMap, contract_kind: str) -> str | None:
    root = _map_or_empty(definition.get("root"))
    blocked = _map_or_empty(root.get("blocked_contracts"))
    reason = blocked.get(contract_kind)
    return str(reason) if isinstance(reason, str) and reason else None


def _suggested_root_definitions(capabilities: JsonMap, expected_type: str | None) -> list[JsonMap]:
    if not expected_type:
        return []
    suggestions: list[JsonMap] = []
    graph_context = _map_or_empty(capabilities.get("graph_context"))
    contract_kind = _contract_kind(graph_context)
    for node in _maps(capabilities.get("nodes")):
        definition_id = _text(node.get("definition"))
        if not definition_id:
            continue
        definition = _definition_for_context(definition_id, graph_context)
        if not isinstance(definition, dict):
            continue
        if contract_kind and _root_blocked_reason(definition, contract_kind):
            continue
        output_type = _definition_default_output_type(definition)
        if output_type and _types_compatible(output_type, expected_type):
            suggestions.append({"definition": definition_id, "output_type": output_type})
        if len(suggestions) >= 8:
            break
    return suggestions


def _function_contracts() -> dict[str, JsonMap]:
    registry = load_function_contract_registry()
    contracts = registry.get("function_contracts")
    return contracts if isinstance(contracts, dict) else {}


def _fx_map_node_definitions() -> list[JsonMap]:
    graph = load_fx_map_graph_definition().get("fx_map_graph")
    nodes = graph.get("nodes") if isinstance(graph, dict) else {}
    if not isinstance(nodes, dict):
        return []
    return [{"slug": slug, "kind": "fx-map", **node} for slug, node in nodes.items() if isinstance(node, dict)]


def _builtins(value: JsonValue) -> JsonMap | list[JsonMap]:
    if isinstance(value, dict):
        return value
    return _maps(value)


def _types_compatible(actual: str, expected: str) -> bool:
    aliases = {
        "SDTypeTexture": {"texture"},
        "float": {"float", "value"},
        "float2": {"float2", "value"},
        "float3": {"float3", "value"},
        "float4": {"float4", "value"},
        "bool": {"bool", "value"},
        "int": {"int", "value"},
    }
    if actual == expected:
        return True
    return expected in aliases.get(actual, set())


def normalize_graph_change_parameters(change: JsonMap) -> JsonMap:
    """Merge public change.parameters[] entries into node parameter maps."""
    if not isinstance(change, dict) or not _maps(change.get("parameters")):
        return dict(change) if isinstance(change, dict) else {}
    normalized = dict(change)
    nodes = [cast_json_map(dict(node)) for node in _maps(change.get("nodes"))]
    nodes_by_id: dict[str, JsonMap] = {}
    for node in nodes:
        node_id = _text(node.get("id"))
        if node_id:
            nodes_by_id[node_id] = node
    for index, parameter in enumerate(_maps(change.get("parameters"))):
        node_id = _text(parameter.get("node") or parameter.get("id"))
        parameter_id = _text(parameter.get("parameter") or parameter.get("parameter_id"))
        if not node_id or not parameter_id:
            continue
        node = nodes_by_id.get(node_id)
        if node is None:
            node: JsonMap = {"id": node_id}
            nodes.append(node)
            nodes_by_id[node_id] = node
        params = node.get("parameters")
        if not isinstance(params, dict):
            params: JsonMap = {}
            node["parameters"] = params
        params[parameter_id] = _public_parameter_spec(parameter, index)
    normalized["nodes"] = nodes
    return normalized


def _public_parameter_spec(parameter: JsonMap, _index: int) -> JsonValue:
    if "value" not in parameter:
        return {}
    value = parameter.get("value")
    value_type = _text(parameter.get("value_type") or parameter.get("type"))
    if not value_type:
        return value
    return {"value": value, "type": value_type, "value_type": value_type}


def _error(code: str, path: str, message: str, extra: JsonMap | None = None) -> JsonMap:
    return {"code": code, "path": path, "message": message, **(extra or {})}


def _connection_state(connection: JsonMap, *, definitions_by_node: dict[str, JsonMap] | None = None) -> JsonMap:
    definitions = definitions_by_node or {}
    source, source_port = _connection_endpoint(connection, "from")
    target, target_port = _connection_endpoint(connection, "to")
    if _connection_has_builtin_endpoint(connection, "from") or _is_builtin_endpoint(source):
        return _compact(
            {
                "from_builtin": source,
                "to": target,
                "to_input": _canonical_port_id(definitions.get(target or ""), "inputs", target_port),
            }
        )
    source_port = source_port or "unique_filter_output"
    return {
        "from": source,
        "from_output": _canonical_port_id(definitions.get(source or ""), "outputs", source_port),
        "to": target,
        "to_input": _canonical_port_id(definitions.get(target or ""), "inputs", target_port),
    }


def _connection_endpoint(connection: JsonMap, side: str) -> tuple[str | None, str | None]:
    endpoint = connection.get(side)
    if isinstance(endpoint, dict):
        node = _endpoint_node(endpoint)
        port = _endpoint_port(endpoint, side)
        return node, port
    node = _text(endpoint)
    if side == "from":
        port = _text(connection.get("from_output") or connection.get("output"))
    else:
        port = _text(connection.get("to_input") or connection.get("input"))
    return node, port


def _connection_has_builtin_endpoint(connection: JsonMap, side: str) -> bool:
    endpoint = connection.get(side)
    return isinstance(endpoint, dict) and bool(_text(endpoint.get("builtin")))


def _endpoint_node(endpoint: JsonMap) -> str | None:
    builtin = _text(endpoint.get("builtin"))
    if builtin:
        return builtin
    node = endpoint.get("node")
    if isinstance(node, dict):
        return _text(node.get("id") or node.get("node"))
    return _text(node or endpoint.get("id"))


def _endpoint_port(endpoint: JsonMap, side: str) -> str | None:
    if side == "from":
        return _text(endpoint.get("output") or endpoint.get("port") or endpoint.get("from_output"))
    return _text(endpoint.get("input") or endpoint.get("port") or endpoint.get("to_input"))


def _output_node_id(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _text(value.get("node") or value.get("id"))
    return None


def _is_builtin_endpoint(value: str | None) -> bool:
    return bool(value and value.startswith("$"))


def _builtin_ids(graph_context: JsonMap) -> set[str]:
    builtins = _contract_map(graph_context).get("builtins")
    if isinstance(builtins, dict):
        return {str(key) for key in builtins.keys()}
    return {str(item.get("id")) for item in _maps(builtins) if item.get("id")}


def _context_scopes(node: JsonMap) -> list[JsonMap]:
    scopes: list[JsonMap] = []
    context_scopes = node.get("context_scopes")
    for item in context_scopes if isinstance(context_scopes, list) else []:
        if isinstance(item, dict):
            scopes.append(item)
        elif isinstance(item, str):
            scopes.append({"id": item})
    return scopes


def _string_list(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _maps(value: JsonValue) -> list[JsonMap]:
    if not isinstance(value, list):
        return []
    return [cast_json_map(item) for item in value if isinstance(item, dict)]


def _map_or_empty(value: JsonValue) -> JsonMap:
    return cast_json_map(value) if isinstance(value, dict) else {}


def _contract_map(graph_context: JsonMap) -> JsonMap:
    return _map_or_empty(graph_context.get("contract"))


def _contract_kind(graph_context: JsonMap) -> str:
    return _text(_contract_map(graph_context).get("kind")) or ""


def _operation_maps(value: JsonValue) -> tuple[list[JsonMap], list[JsonMap]]:
    if not isinstance(value, list):
        return [], [_error("invalid_operations", "change.operations", "operations must be a list")]
    operations: list[JsonMap] = []
    errors: list[JsonMap] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            operations.append(cast_json_map(item))
        else:
            errors.append(_error("invalid_operation", f"change.operations[{index}]", "operation must be an object"))
    return operations, errors


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compact(value: JsonMap) -> JsonMap:
    return {key: item for key, item in value.items() if item is not None}


def _dedupe_nodes(nodes: list[JsonMap]) -> list[JsonMap]:
    result = []
    seen = set()
    for node in nodes:
        definition = node.get("definition_id")
        if definition in seen:
            continue
        seen.add(definition)
        result.append(node)
    return result
