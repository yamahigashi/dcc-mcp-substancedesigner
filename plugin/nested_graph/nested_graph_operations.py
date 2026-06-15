"""Nested graph apply, rebuild, connection, and output helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias, cast

from sd.api.sdproperty import SDPropertyCategory

from ..json_types import JsonMap, JsonValue
from ..library.library_nodes import (
    ensure_standard_package_for_resource,
    find_library_resource,
    resource_not_found_message,
)
from ..library.library_types import LibraryPackageManager, LibraryResource
from ..parameters.parameter_types import SettableSDValue
from ..parameters.sd_values import make_sd_value
from .nested_graph_state import (
    node_parameter_state,
    normalize_global_variable_reference,
    optional_identifier,
    optional_string,
    required_string,
    set_node_position,
    state_mapping,
    state_maps,
    string_or_default,
    target_mapping,
)
from .nested_graph_types import (
    GraphResolver,
    MutableNestedGraph,
    MutableNestedNode,
    NestedGraphState,
    NestedProperty,
    NodeConnector,
    NodeDefinitionGetter,
    NodeFinder,
    NodePositionGetter,
    OutputNodeCollection,
    OwnerNode,
    ParameterSetter,
    PropertyGraphOwner,
    ReprFallback,
    SDTypeValue,
    ValueSerializer,
)

ScalarValue: TypeAlias = bool | int | float | str
ValueInput: TypeAlias = ScalarValue | list[ScalarValue] | tuple[ScalarValue, ...] | Mapping[str, ScalarValue]


INPUT_NODE_ANNOTATION_TYPES = {
    "description": "string",
    "editor": "string",
    "group": "string",
    "min": "float",
    "max": "float",
    "step": "float",
    "clamp": "bool",
}

INPUT_NODE_DEFINITIONS = {
    "bool": "sbs::function::get_bool",
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


class NestedGraphMutationError(RuntimeError):
    """Mutation failure with MCP-facing diagnostic details."""

    def __init__(self, message: str, details: dict[str, JsonValue]) -> None:
        """Store a message and JSON-safe diagnostic details."""
        super().__init__(message)
        self.details = details


class OwnerInputMutationError(RuntimeError):
    """Owner input update failure with the failing sub-phase."""

    def __init__(self, phase: str, message: str) -> None:
        """Store the failed owner-input mutation phase."""
        super().__init__(message)
        self.phase = phase


class PropertyGraphRebuildError(RuntimeError):
    """Property graph replacement failure with partial mutation state."""

    def __init__(self, message: str, *, partial_changes: bool) -> None:
        """Store whether the failed rebuild already changed graph state."""
        super().__init__(message)
        self.partial_changes = partial_changes


def apply_nested_graph_state_command(
    state_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
    get_node_position: NodePositionGetter | None = None,
    serialize_value: ValueSerializer | None = None,
) -> NestedGraphState:
    """Validate and apply a nested graph command state payload."""
    return apply_property_graph_state_command(
        state_value,
        mode,
        resolve_graph,
        find_node,
        set_node_params,
        connect_nodes,
        get_node_definition,
        operation="apply_nested_graph_state",
        default_graph_type="SDSBSFunctionGraph",
        supported_graph_types={"SDSBSFunctionGraph"},
        package_manager=package_manager,
        get_node_position=get_node_position,
        serialize_value=serialize_value,
    )


def apply_fx_map_graph_state_command(
    state_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
    get_node_position: NodePositionGetter | None = None,
    serialize_value: ValueSerializer | None = None,
) -> NestedGraphState:
    """Apply serialized FX-Map graph state to a node's referenced SDSBSFxMapGraph."""
    if mode not in ("sync", "replace"):
        raise ValueError("mode must be one of: sync, replace")
    state = state_mapping(state_value)
    graph_type = string_or_default(state.get("graph_type"), "SDSBSFxMapGraph")
    if graph_type != "SDSBSFxMapGraph":
        raise ValueError("Only SDSBSFxMapGraph is supported.")
    target = target_mapping(state.get("target"))
    graph_identifier = optional_string(target.get("graph_identifier"))
    node_id = optional_identifier(target.get("node_id"))
    if node_id is None:
        raise ValueError("state.target.node_id is required.")
    graph = resolve_graph(graph_identifier)
    owner_node = find_node(graph, node_id)
    fx_graph = fx_map_referenced_graph_for_apply(owner_node, node_id)
    if fx_graph is None:
        raise ValueError("Node '{}' does not reference an SDSBSFxMapGraph.".format(node_id))
    target_result: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "graph_type": graph_type,
    }
    saved_state = restorable_nested_graph_state(
        fx_graph,
        get_node_definition,
        get_node_position or default_node_position,
        serialize_value or default_serialize_value,
    )
    assert_restorable_nested_graph_state(saved_state)
    try:
        clear_graph_nodes(fx_graph)
        result = apply_nested_graph_state_to_graph(
            fx_graph,
            {**state, "graph_type": graph_type},
            mode,
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
    except Exception as exc:
        rolled_back = restore_mutable_graph(
            fx_graph,
            {**saved_state, "graph_type": graph_type},
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        raise mutation_error(
            "apply_fx_map_graph_state",
            "apply_nested_graph_state",
            target_result,
            "",
            [],
            rolled_back,
            str(exc),
        ) from None
    result["operation"] = "apply_fx_map_graph_state"
    result["next_tools"] = fx_map_graph_next_tools(target_result)
    return result


def apply_nested_graph_patch_command(
    patch_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
    get_node_position: NodePositionGetter | None = None,
    serialize_value: ValueSerializer | None = None,
) -> NestedGraphState:
    """Patch an existing property graph without rebuilding it."""
    if mode != "patch":
        raise ValueError("mode must be patch")
    patch = state_mapping(patch_value)
    target = target_mapping(patch.get("target"))
    graph_type = string_or_default(patch.get("graph_type"), "SDSBSFunctionGraph")
    if graph_type != "SDSBSFunctionGraph":
        raise ValueError("Only SDSBSFunctionGraph is supported.")
    graph_identifier = optional_string(target.get("graph_identifier"))
    node_id = optional_identifier(target.get("node_id"))
    property_id = optional_string(target.get("property")) or optional_string(target.get("property_id"))
    if node_id is None or property_id is None:
        raise ValueError("patch.target.node_id and patch.target.property are required.")
    graph = resolve_graph(graph_identifier)
    owner_node = find_node(graph, node_id)
    prop = find_node_property(owner_node, property_id)
    nested_graph = owner_node.getPropertyGraph(prop)
    created_property_graph = False
    if nested_graph is None:
        try:
            nested_graph = owner_node.newPropertyGraph(prop, graph_type)
        except Exception as exc:
            raise ValueError("Failed to create nested graph '{}.{}': {}".format(node_id, property_id, exc)) from exc
        if nested_graph is None:
            raise ValueError("newPropertyGraph returned None for '{}.{}'.".format(node_id, property_id))
        created_property_graph = True
    target_result: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "property": property_id,
    }
    saved_state = current_nested_graph_restore_state(
        owner_node, prop, get_node_definition, get_node_position, serialize_value
    )
    try:
        result = apply_nested_graph_patch_to_graph(
            nested_graph,
            patch,
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        result["created_property_graph"] = created_property_graph
    except Exception as exc:
        rolled_back = restore_property_graph(
            owner_node,
            prop,
            node_id,
            property_id,
            graph_type,
            saved_state,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        raise mutation_error(
            "apply_nested_graph_patch",
            "apply_nested_graph_patch",
            target_result,
            "",
            [],
            rolled_back,
            str(exc),
        ) from None
    result["operation"] = "apply_nested_graph_patch"
    result["next_tools"] = nested_graph_next_tools(target_result)
    return result


def apply_fx_map_graph_patch_command(
    patch_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
    get_node_position: NodePositionGetter | None = None,
    serialize_value: ValueSerializer | None = None,
) -> NestedGraphState:
    """Patch an existing FX-Map referenced graph without rebuilding it."""
    if mode != "patch":
        raise ValueError("mode must be patch")
    patch = state_mapping(patch_value)
    graph_type = string_or_default(patch.get("graph_type"), "SDSBSFxMapGraph")
    if graph_type != "SDSBSFxMapGraph":
        raise ValueError("Only SDSBSFxMapGraph is supported.")
    target = target_mapping(patch.get("target"))
    graph_identifier = optional_string(target.get("graph_identifier"))
    node_id = optional_identifier(target.get("node_id"))
    if node_id is None:
        raise ValueError("patch.target.node_id is required.")
    graph = resolve_graph(graph_identifier)
    owner_node = find_node(graph, node_id)
    fx_graph = fx_map_referenced_graph_for_apply(owner_node, node_id)
    if fx_graph is None:
        raise ValueError("Node '{}' does not reference an SDSBSFxMapGraph.".format(node_id))
    target_result: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "graph_type": graph_type,
    }
    saved_state = restorable_nested_graph_state(
        fx_graph,
        get_node_definition,
        get_node_position or default_node_position,
        serialize_value or default_serialize_value,
    )
    assert_restorable_nested_graph_state(saved_state)
    try:
        result = apply_nested_graph_patch_to_graph(
            fx_graph,
            patch,
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
    except Exception as exc:
        rolled_back = restore_mutable_graph(
            fx_graph,
            {**saved_state, "graph_type": graph_type},
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        raise mutation_error(
            "apply_fx_map_graph_patch",
            "apply_nested_graph_patch",
            target_result,
            "",
            [],
            rolled_back,
            str(exc),
        ) from None
    result["operation"] = "apply_fx_map_graph_patch"
    result["next_tools"] = fx_map_graph_next_tools(target_result)
    return result


def fx_map_referenced_graph_for_apply(owner_node: PropertyGraphOwner, node_id: str) -> MutableNestedGraph | None:
    """Return the mutable SDSBSFxMapGraph referenced by an FX-Map compositing node."""
    try:
        resource = owner_node.getReferencedResource()
    except Exception as exc:
        raise RuntimeError("Failed to read FX-Map referenced graph '{}': {}".format(node_id, exc)) from exc
    if resource is None:
        return None
    try:
        class_name = resource.getClassName()
    except Exception:
        class_name = ""
    if class_name and class_name != "SDSBSFxMapGraph":
        raise ValueError("Node '{}' references '{}', not SDSBSFxMapGraph.".format(node_id, class_name))
    return resource


def apply_property_graph_state_command(
    state_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    *,
    operation: str,
    default_graph_type: str,
    supported_graph_types: set[str],
    package_manager: LibraryPackageManager | None = None,
    get_node_position: NodePositionGetter | None = None,
    serialize_value: ValueSerializer | None = None,
) -> NestedGraphState:
    """Validate and apply a node-owned property graph command state payload."""
    if mode == "param_update":
        return {
            "status": "conflict",
            "operation": "param_update",
            "reason": "param_update requires persisted provenance metadata; use replace for now.",
            "allowed_operations": ["replace", "inspect"],
        }
    if mode not in ("sync", "replace"):
        raise ValueError("mode must be one of: sync, replace, param_update")
    state = state_mapping(state_value)

    target = target_mapping(state.get("target"))
    graph_type = string_or_default(state.get("graph_type"), default_graph_type)
    if graph_type not in supported_graph_types:
        raise ValueError("Only {} is supported.".format(", ".join(sorted(supported_graph_types))))

    graph_identifier = optional_string(target.get("graph_identifier"))
    node_id = optional_identifier(target.get("node_id"))
    property_id = optional_string(target.get("property")) or optional_string(target.get("property_id"))
    if node_id is None or property_id is None:
        raise ValueError("state.target.node_id and state.target.property are required.")

    graph = resolve_graph(graph_identifier)
    owner_node = find_node(graph, node_id)
    prop = find_node_property(owner_node, property_id)
    validate_external_references(owner_node, state)
    target_result: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "property": property_id,
    }
    if graph_type != "SDSBSFunctionGraph":
        target_result["graph_type"] = graph_type
    existing_state = current_nested_graph_restore_state(
        owner_node,
        prop,
        get_node_definition,
        get_node_position,
        serialize_value,
    )
    phase = "rebuild_property_graph"
    try:
        nested_graph = rebuild_property_graph(owner_node, prop, node_id, property_id, graph_type)
        phase = "apply_nested_graph_state"
        result = apply_nested_graph_state_to_graph(
            nested_graph,
            {**state, "graph_type": graph_type},
            mode,
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        result["operation"] = operation
        result["next_tools"] = nested_graph_next_tools(target_result)
        return result
    except Exception as exc:
        rolled_back = restore_property_graph(
            owner_node,
            prop,
            node_id,
            property_id,
            graph_type,
            existing_state,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        partial_changes_override = False if rolled_back else True
        if isinstance(exc, PropertyGraphRebuildError):
            phase = "rebuild_property_graph"
            partial_changes_override = False if rolled_back else exc.partial_changes
        raise mutation_error(
            operation,
            phase,
            target_result,
            "",
            [],
            rolled_back,
            str(exc),
            partial_changes_override=partial_changes_override,
        ) from None


def bind_parameter_input_command(
    target_value: JsonValue,
    input_value: JsonValue,
    mode: str,
    resolve_graph: GraphResolver,
    find_node: NodeFinder,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
) -> NestedGraphState:
    """Bind a node parameter property to an owner input through a function graph."""
    if mode not in ("sync", "replace"):
        raise ValueError("mode must be one of: sync, replace")
    target = target_mapping(target_value)
    graph_identifier = optional_string(target.get("graph_identifier"))
    node_id = optional_identifier(target.get("node_id"))
    property_id = optional_string(target.get("property")) or optional_string(target.get("property_id"))
    if node_id is None or property_id is None:
        raise ValueError("target.node_id and target.property are required.")

    input_spec = normalize_input_spec(input_value)
    requested_input_id = required_string(input_spec.get("id"), "input.id is required.")
    input_id = normalize_global_variable_reference(requested_input_id)
    input_spec = {**input_spec, "id": input_id, "requested_id": requested_input_id}
    value_type = input_value_type(input_spec)
    input_spec["value_type"] = value_type
    getter_definition = owner_input_get_node_definition({"value_type": value_type})

    graph = resolve_graph(graph_identifier)
    owner_node = find_node(graph, node_id)
    prop = find_node_property(owner_node, property_id)
    target_result: dict[str, JsonValue] = {
        "graph_identifier": graph.getIdentifier(),
        "node_id": node_id,
        "property": property_id,
    }
    phase = "rebuild_property_graph"
    created_owner_inputs: list[JsonValue] = []
    input_result: JsonValue | None = None
    property_graph_rebuilt = False
    partial_changes_override: bool | None = None
    try:
        nested_graph = rebuild_property_graph(owner_node, prop, node_id, property_id, "SDSBSFunctionGraph")
        property_graph_rebuilt = True
        phase = "ensure_owner_input"
        input_result = ensure_owner_input(owner_node, input_spec, created_owner_inputs)
        if isinstance(input_result, dict) and input_result.get("status") == "created":
            created_owner_inputs[:] = [input_result]
        function_reference = owner_input_binding_reference(input_result, input_id)
        state: dict[str, JsonValue] = {
            "graph_type": "SDSBSFunctionGraph",
            "nodes": [
                {
                    "id": "read_{}".format(input_id),
                    "definition": getter_definition,
                    "parameters": {"__constant__": {"value": function_reference, "type": "string"}},
                }
            ],
            "connections": [],
            "output": {"node": "read_{}".format(input_id)},
        }
        phase = "apply_nested_graph_state"
        result = apply_nested_graph_state_to_graph(
            nested_graph,
            state,
            mode,
            target_result,
            set_node_params,
            connect_nodes,
            get_node_definition,
        )
    except Exception as exc:
        if isinstance(input_result, dict) and input_result.get("status") == "created":
            created_owner_inputs[:] = [input_result]
        if isinstance(exc, OwnerInputMutationError):
            phase = exc.phase
        if isinstance(exc, PropertyGraphRebuildError):
            partial_changes_override = exc.partial_changes
        rolled_back = False
        if property_graph_rebuilt:
            try:
                rollback_property_graph(owner_node, prop)
                rolled_back = True
            except Exception:
                rolled_back = False
        raise mutation_error(
            "bind_parameter_input",
            phase,
            target_result,
            requested_input_id,
            created_owner_inputs,
            rolled_back,
            str(exc),
            partial_changes_override=partial_changes_override,
        ) from None
    result["input"] = input_result
    result["operation"] = "bind_parameter_input"
    result["next_tools"] = nested_graph_next_tools(target_result)
    return result


def apply_nested_graph_state_to_graph(
    nested_graph: MutableNestedGraph,
    state: dict[str, JsonValue],
    mode: str,
    target: dict[str, JsonValue],
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
) -> NestedGraphState:
    """Apply serialized nested graph state to a fresh nested graph."""
    known_definitions = known_definition_ids(nested_graph)
    logical_to_node: dict[str, MutableNestedNode] = {}
    created: list[JsonValue] = []
    for spec in state_maps(state.get("nodes", []), "nodes"):
        logical_id = required_string(spec.get("id"), "Each nested graph node requires id and definition.")
        definition = required_string(spec.get("definition"), "Each nested graph node requires id and definition.")
        params = node_parameter_state(spec)
        host_creation = host_creation_state(spec.get("host_creation"))
        if host_creation is None and known_definitions and definition not in known_definitions:
            raise ValueError("Unknown nested graph node definition '{}'.".format(definition))
        node, creation_result = create_nested_graph_node(nested_graph, definition, host_creation, package_manager)
        set_node_position(node, spec.get("position"))
        parameter_status = set_node_params(node, params)
        logical_to_node[logical_id] = node
        node_result: JsonMap = {
            "id": logical_id,
            "node_id": node.getIdentifier(),
            "definition": get_node_definition(node),
        }
        if parameter_status:
            node_result["parameter_status"] = parameter_status
        if creation_result:
            node_result["host_creation"] = creation_result
        created.append(node_result)

    restore_node_property_graphs(
        logical_to_node,
        state,
        target,
        set_node_params,
        connect_nodes,
        get_node_definition,
        package_manager,
    )
    connection_results = apply_connections(
        nested_graph,
        state,
        logical_to_node,
        connect_nodes,
    )
    output_id = apply_output_node(nested_graph, state.get("output"), logical_to_node)

    return {
        "status": "applied",
        "operation": "replace" if mode == "replace" else "sync",
        "target": target,
        "graph_type": state.get("graph_type", "SDSBSFunctionGraph"),
        "nodes_created": len(created),
        "connections_created": sum(
            1 for result in connection_results if connection_result_created_host_connection(result)
        ),
        "node_map": {cast(str, item["id"]): cast(str, item["node_id"]) for item in created if isinstance(item, dict)},
        "nodes": created,
        "connections": connection_results,
        "output": output_id,
        "next_tools": nested_graph_next_tools(target),
        "warning": "sync currently applies by rebuilding the nested graph." if mode == "sync" else "",
    }


def restore_node_property_graphs(
    logical_to_node: dict[str, MutableNestedNode],
    state: dict[str, JsonValue],
    target: dict[str, JsonValue],
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None,
) -> None:
    """Restore child property graphs captured in a graph snapshot."""
    for spec in state_maps(state.get("nodes", []), "nodes"):
        node_id = required_string(spec.get("id"), "Each nested graph node requires id.")
        node = logical_to_node[node_id]
        for graph_spec in state_maps(spec.get("property_graphs", []), "property_graphs"):
            property_id = required_string(graph_spec.get("property"), "property_graphs[].property is required.")
            prop = find_node_property(node, property_id)
            graph_type = string_or_default(graph_spec.get("graph_type"), "SDSBSFunctionGraph")
            child_graph = rebuild_property_graph(cast(PropertyGraphOwner, node), prop, node_id, property_id, graph_type)
            child_state = state_mapping(graph_spec.get("state"))
            apply_nested_graph_state_to_graph(
                child_graph,
                {**child_state, "graph_type": graph_type},
                "replace",
                {"graph_identifier": target.get("graph_identifier"), "node_id": node_id, "property": property_id},
                set_node_params,
                connect_nodes,
                get_node_definition,
                package_manager,
            )


def connection_result_created_host_connection(result: JsonValue) -> bool:
    """Return whether a connection result represents a concrete host edge."""
    return isinstance(result, dict) and result.get("success") is True and not result.get("from_builtin")


def apply_nested_graph_patch_to_graph(
    nested_graph: MutableNestedGraph,
    patch: dict[str, JsonValue],
    target: dict[str, JsonValue],
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None = None,
) -> NestedGraphState:
    """Apply partial-edit operations to an existing nested graph."""
    known_definitions = known_definition_ids(nested_graph)
    logical_to_node: dict[str, MutableNestedNode] = {
        node.getIdentifier(): node for node in list(nested_graph.getNodes())
    }
    results: list[JsonValue] = []
    created: list[JsonValue] = []
    connections: list[JsonValue] = []
    for index, operation in enumerate(state_maps(patch.get("operations", []), "operations")):
        op = required_string(operation.get("op"), "Each patch operation requires op.")
        if op == "ensure_node":
            logical_id = required_string(operation.get("id") or operation.get("node"), "ensure_node requires id.")
            node = logical_to_node.get(logical_id)
            definition = optional_string(operation.get("definition"))
            if node is None:
                if definition is None:
                    raise ValueError("ensure_node '{}' requires definition when creating a node.".format(logical_id))
                host_creation = host_creation_state(operation.get("host_creation"))
                if host_creation is None and known_definitions and definition not in known_definitions:
                    raise ValueError("Unknown nested graph node definition '{}'.".format(definition))
                node, creation_result = create_nested_graph_node(
                    nested_graph, definition, host_creation, package_manager
                )
                logical_to_node[logical_id] = node
                created_result: dict[str, JsonValue] = {
                    "op": op,
                    "id": logical_id,
                    "node_id": node.getIdentifier(),
                    "definition": get_node_definition(node),
                }
                if creation_result:
                    created_result["host_creation"] = creation_result
                created.append(created_result)
                results.append(created_result)
            elif definition is not None and get_node_definition(node) != definition:
                raise ValueError(
                    "Existing node '{}' definition is '{}', not '{}'.".format(
                        logical_id, get_node_definition(node), definition
                    )
                )
            set_node_position(node, operation.get("position"))
            params = node_parameter_state(operation)
            if params:
                parameter_status = set_node_params(node, params)
                results.append(
                    {
                        "op": op,
                        "id": logical_id,
                        "node_id": node.getIdentifier(),
                        "parameters": sorted(params.keys()),
                        "parameter_status": parameter_status or {},
                    }
                )
            continue
        if op == "set_parameter":
            node_id = required_string(operation.get("node"), "set_parameter requires node.")
            node = require_nested_patch_node(logical_to_node, node_id)
            parameter_id = required_string(operation.get("parameter"), "set_parameter requires parameter.")
            if "value" not in operation:
                raise ValueError("set_parameter '{}' requires value.".format(parameter_id))
            parameter_status = set_node_params(node, {parameter_id: operation.get("value")})
            results.append(
                {
                    "op": op,
                    "node": node_id,
                    "node_id": node.getIdentifier(),
                    "parameter": parameter_id,
                    "parameter_status": parameter_status or {},
                }
            )
            continue
        if op == "set_property_graph":
            node_id = required_string(operation.get("node"), "set_property_graph requires node.")
            node = require_nested_patch_node(logical_to_node, node_id)
            property_id = required_string(
                operation.get("property") or operation.get("property_id"),
                "set_property_graph requires property.",
            )
            property_graph_type = string_or_default(operation.get("graph_type"), "SDSBSFunctionGraph")
            prop = find_node_property(node, property_id)
            property_graph = rebuild_property_graph(cast(PropertyGraphOwner, node), prop, node_id, property_id, property_graph_type)
            state = {
                "graph_type": property_graph_type,
                "nodes": state_maps(operation.get("nodes", []), "nodes"),
                "connections": state_maps(operation.get("connections", []), "connections"),
                "output": operation.get("output"),
            }
            apply_result = apply_nested_graph_state_to_graph(
                property_graph,
                state,
                "replace",
                {"graph_identifier": target.get("graph_identifier"), "node_id": node_id, "property": property_id},
                set_node_params,
                connect_nodes,
                get_node_definition,
                package_manager,
            )
            result = {
                "op": op,
                "node": node_id,
                "property": property_id,
                "graph_type": property_graph_type,
                "nodes_created": apply_result.get("nodes_created", 0),
                "connections_created": apply_result.get("connections_created", 0),
                "output": apply_result.get("output"),
            }
            results.append(result)
            continue
        if op == "ensure_connection":
            from_builtin = patch_builtin_endpoint(operation)
            if from_builtin:
                to_id, to_input = patch_connection_endpoint(operation, "to", "input1")
                require_nested_patch_node(logical_to_node, to_id)
                result = {
                    "op": op,
                    "from_builtin": from_builtin,
                    "to": to_id,
                    "to_input": to_input,
                    "success": True,
                    "binding": "host_implicit_builtin",
                }
                connections.append(result)
                results.append(result)
                continue
            from_id, from_output = patch_connection_endpoint(operation, "from", "unique_filter_output")
            to_id, to_input = patch_connection_endpoint(operation, "to", "input1")
            from_node = require_nested_patch_node(logical_to_node, from_id)
            to_node = require_nested_patch_node(logical_to_node, to_id)
            connect_nodes(nested_graph, from_node, from_output, to_node, to_input)
            result = {
                "op": op,
                "from": from_id,
                "from_output": from_output,
                "to": to_id,
                "to_input": to_input,
                "success": True,
            }
            connections.append(result)
            results.append(result)
            continue
        if op == "remove_connection":
            target_id, target_input = patch_connection_endpoint(operation, "to", "input1")
            target_node = require_nested_patch_node(logical_to_node, target_id)
            remove_nested_graph_input_connections(target_node, target_input)
            result = {"op": op, "to": target_id, "to_input": target_input, "success": True}
            results.append(result)
            continue
        if op == "move_node":
            node_id = required_string(operation.get("node"), "move_node requires node.")
            node = require_nested_patch_node(logical_to_node, node_id)
            set_node_position(node, operation.get("position"))
            results.append({"op": op, "node": node_id, "node_id": node.getIdentifier()})
            continue
        if op == "set_output":
            node_id = required_string(operation.get("node"), "set_output requires node.")
            node = require_nested_patch_node(logical_to_node, node_id)
            try:
                nested_graph.setOutputNode(node, True)
            except Exception as exc:
                raise RuntimeError("Failed to set nested graph output '{}': {}".format(node_id, exc)) from exc
            results.append({"op": op, "node": node_id, "node_id": node.getIdentifier()})
            continue
        raise ValueError("Unsupported patch operation '{}' at operations[{}].".format(op, index))
    return {
        "status": "patched",
        "operation": "patch",
        "target": target,
        "graph_type": patch.get("graph_type", "SDSBSFunctionGraph"),
        "nodes_created": len(created),
        "connections_created": len(connections),
        "node_map": {item["id"]: item["node_id"] for item in created if isinstance(item, dict)},
        "nodes": created,
        "connections": connections,
        "operations": results,
    }


def require_nested_patch_node(nodes: dict[str, MutableNestedNode], node_id: str) -> MutableNestedNode:
    """Return a patch node or raise a clear error."""
    node = nodes.get(node_id)
    if node is None:
        raise ValueError("Patch node '{}' was not found.".format(node_id))
    return node


def patch_builtin_endpoint(operation: dict[str, JsonValue]) -> str | None:
    """Return a builtin source endpoint from a patch operation when present."""
    endpoint = operation.get("from")
    if isinstance(endpoint, dict):
        builtin = optional_string(endpoint.get("builtin"))
        if builtin:
            return builtin
    builtin = optional_string(operation.get("from_builtin"))
    return builtin


def patch_connection_endpoint(operation: dict[str, JsonValue], side: str, default_port: str) -> tuple[str, str]:
    """Return a patch connection endpoint node and port."""
    endpoint = operation.get(side)
    if isinstance(endpoint, dict):
        node_id = required_string(endpoint.get("node") or endpoint.get("id"), "{} endpoint requires node.".format(side))
        port_key = "output" if side == "from" else "input"
        port = string_or_default(endpoint.get(port_key) or endpoint.get("port"), default_port)
        return node_id, port
    node_id = required_string(endpoint, "{} endpoint requires node.".format(side))
    direct_key = "from_output" if side == "from" else "to_input"
    fallback_key = "output" if side == "from" else "input"
    return node_id, string_or_default(operation.get(direct_key) or operation.get(fallback_key), default_port)


def remove_nested_graph_input_connections(node: MutableNestedNode, input_id: str) -> None:
    """Delete all connections attached to one nested graph node input."""
    get_property_from_id = getattr(node, "getPropertyFromId", None)
    prop = get_property_from_id(input_id, SDPropertyCategory.Input) if callable(get_property_from_id) else None
    if prop is None:
        for candidate in list(node.getProperties(SDPropertyCategory.Input)):
            if candidate.getId() == input_id:
                prop = candidate
                break
    if prop is None:
        raise ValueError("Input property '{}' not found on node '{}'.".format(input_id, node.getIdentifier()))
    delete_connections = getattr(node, "deletePropertyConnections", None)
    if not callable(delete_connections):
        raise ValueError("Node '{}' does not support deleting input connections.".format(node.getIdentifier()))
    delete_connections(prop)


def host_creation_state(value: JsonValue) -> dict[str, JsonValue] | None:
    """Return optional host creation metadata for nested Function Graph nodes."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("node.host_creation must be a mapping.")
    result = dict(value)
    kind = optional_string(result.get("kind"))
    if kind != "function_graph_resource_instance":
        raise ValueError("Unsupported nested graph host_creation kind '{}'.".format(kind or ""))
    return result


def create_nested_graph_node(
    nested_graph: MutableNestedGraph,
    definition: str,
    host_creation: dict[str, JsonValue] | None,
    package_manager: LibraryPackageManager | None,
) -> tuple[MutableNestedNode, dict[str, JsonValue] | None]:
    """Create a native nested node or a package-backed function graph instance."""
    if host_creation is None:
        node = nested_graph.newNode(definition)
        if node is None:
            raise RuntimeError("newNode('{}') returned None.".format(definition))
        return node, None

    if package_manager is None:
        raise ValueError("Nested graph resource instance creation requires a package manager.")
    resource_url = required_string(host_creation.get("resource_url"), "host_creation.resource_url is required.")
    package_hint = host_creation.get("package_hint")
    resource = find_library_resource(package_manager, resource_url)
    load_attempt: JsonValue = {}
    if resource is None:
        load_attempt = ensure_standard_package_for_resource(package_manager, resource_url, package_hint)
        resource = find_library_resource(package_manager, resource_url)
    if resource is None:
        raise ValueError(resource_not_found_message(package_manager, resource_url, load_attempt))
    node = nested_graph.newInstanceNode(resource)
    if node is None:
        raise RuntimeError("newInstanceNode failed for '{}'.".format(resource_url))
    return node, {
        "kind": "function_graph_resource_instance",
        "resource_url": resource_url,
        "package_load": load_attempt,
    }


def current_nested_graph_restore_state(
    owner_node: PropertyGraphOwner,
    prop: NestedProperty,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter | None,
    serialize_value: ValueSerializer | None,
) -> dict[str, JsonValue] | None:
    """Serialize the current property graph into a state that can be reapplied."""
    try:
        nested_graph = owner_node.getPropertyGraph(prop)
    except Exception as exc:
        raise ValueError("Cannot read existing nested graph before replace: {}".format(exc)) from exc
    if nested_graph is None:
        return None
    state = restorable_nested_graph_state(
        nested_graph,
        get_node_definition,
        get_node_position or default_node_position,
        serialize_value or default_serialize_value,
    )
    assert_restorable_nested_graph_state(state)
    return state


def restorable_nested_graph_state(
    nested_graph: MutableNestedGraph,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter,
    serialize_value: ValueSerializer,
) -> dict[str, JsonValue]:
    """Return a replace-state snapshot for rollback."""
    nodes: list[JsonValue] = []
    connections: list[JsonValue] = []
    try:
        nested_nodes = list(nested_graph.getNodes())
    except Exception:
        nested_nodes = []
    for nested_node in nested_nodes:
        node_state: dict[str, JsonValue] = {
            "id": nested_node.getIdentifier(),
            "definition": get_node_definition(nested_node),
            "position": get_node_position(nested_node),
        }
        host_creation = host_creation_from_referenced_resource(nested_node)
        if host_creation is not None:
            node_state["host_creation"] = host_creation
        params = restorable_node_parameters_and_connections(nested_node, serialize_value, connections)
        if params:
            node_state["parameters"] = params
        property_graphs = restorable_node_property_graphs(
            nested_node,
            get_node_definition,
            get_node_position,
            serialize_value,
        )
        if property_graphs:
            node_state["property_graphs"] = property_graphs
        nodes.append(node_state)
    return {
        "nodes": nodes,
        "connections": connections,
        "output": nested_graph_output_state(nested_graph),
    }


def restorable_node_property_graphs(
    node: MutableNestedNode,
    get_node_definition: NodeDefinitionGetter,
    get_node_position: NodePositionGetter,
    serialize_value: ValueSerializer,
) -> list[JsonValue]:
    """Serialize property graphs owned by a nested node."""
    property_graphs: list[JsonValue] = []
    try:
        input_props = list(node.getProperties(SDPropertyCategory.Input))
    except Exception:
        input_props = []
    for prop in input_props:
        try:
            child_graph = node.getPropertyGraph(prop)
        except Exception:
            child_graph = None
        if child_graph is None:
            continue
        property_graphs.append(
            {
                "property": prop.getId(),
                "graph_type": nested_graph_type(child_graph),
                "state": restorable_nested_graph_state(
                    child_graph,
                    get_node_definition,
                    get_node_position,
                    serialize_value,
                ),
            }
        )
    return property_graphs


def nested_graph_type(nested_graph: MutableNestedGraph) -> str:
    """Return a restorable graph type for a nested graph."""
    try:
        graph_type = nested_graph.getClassName()
    except Exception:
        graph_type = ""
    return graph_type or "SDSBSFunctionGraph"


def host_creation_from_referenced_resource(node: MutableNestedNode) -> dict[str, JsonValue] | None:
    """Return host_creation metadata when a nested node is backed by a package resource."""
    try:
        resource = cast(LibraryResource | None, node.getReferencedResource())
    except Exception:
        return None
    if resource is None:
        return None
    try:
        resource_url = resource.getUrl()
    except Exception:
        resource_url = ""
    if not resource_url:
        return None
    return {
        "kind": "function_graph_resource_instance",
        "resource_url": resource_url,
    }


def restorable_node_parameters_and_connections(
    node: MutableNestedNode,
    serialize_value: ValueSerializer,
    connections: list[JsonValue],
) -> dict[str, JsonValue]:
    """Serialize unconnected node inputs and append connection states."""
    params: dict[str, JsonValue] = {}
    try:
        input_props = list(node.getProperties(SDPropertyCategory.Input))
    except Exception:
        input_props = []
    for input_prop in input_props:
        property_id = input_prop.getId()
        try:
            connection_list = list(node.getPropertyConnections(input_prop) or [])
        except Exception:
            connection_list = []
        if connection_list:
            for connection in connection_list:
                try:
                    source_node = connection.getInputPropertyNode()
                    source_property = connection.getInputProperty()
                    if source_node is not None and source_property is not None:
                        connections.append(
                            {
                                "from": source_node.getIdentifier(),
                                "from_output": source_property.getId(),
                                "to": node.getIdentifier(),
                                "to_input": property_id,
                            }
                        )
                except Exception:
                    pass
            continue
        try:
            value = node.getPropertyValue(input_prop)
            if value is not None:
                params[property_id] = serialize_value(value)
        except Exception:
            pass
    return params


def nested_graph_output_state(nested_graph: MutableNestedGraph) -> JsonValue:
    """Return the first nested graph output node state."""
    for method_name in ("getOutputNodes", "getOutputNode"):
        try:
            result = getattr(nested_graph, method_name)()
        except Exception:
            continue
        nodes = output_nodes_from_host_result(result)
        if nodes:
            return {"node": nodes[0].getIdentifier()}
    return None


def output_nodes_from_host_result(value: ReprFallback | None) -> list[MutableNestedNode]:
    """Normalize Substance output-node API variants."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [cast(MutableNestedNode, item) for item in value if item is not None]
    if hasattr(value, "getSize") and hasattr(value, "getItem"):
        collection = cast(OutputNodeCollection, value)
        nodes: list[MutableNestedNode] = []
        for index in range(collection.getSize()):
            item = collection.getItem(index)
            if item is not None:
                nodes.append(cast(MutableNestedNode, item))
        return nodes
    return [cast(MutableNestedNode, value)]


def assert_restorable_nested_graph_state(state: dict[str, JsonValue]) -> None:
    """Reject destructive replace when the current graph cannot be restored."""
    for node in state_maps(state.get("nodes"), "nodes"):
        definition = required_string(node.get("definition"), "snapshot node definition is required.")
        if definition in {"unknown", "sbs::function::instance"} and not isinstance(node.get("host_creation"), dict):
            raise ValueError(
                "Existing nested graph contains non-restorable package instance node '{}'. "
                "Refusing destructive replace before mutation.".format(node.get("id"))
            )
        for graph_spec in state_maps(node.get("property_graphs", []), "property_graphs"):
            assert_restorable_nested_graph_state(state_mapping(graph_spec.get("state")))


def default_node_position(_node: object) -> list[float]:
    """Fallback node position serializer used in tests and non-host callers."""
    return [0.0, 0.0]


def default_serialize_value(value: ReprFallback) -> JsonValue:
    """Fallback JSON value serializer used when host serialization is unavailable."""
    return repr(value)


def validate_external_references(owner_node: PropertyGraphOwner, state: dict[str, JsonValue]) -> None:
    """Validate that declared external references already exist on the owner node."""
    missing = []
    for spec in state_maps(state.get("external_references", []), "external_references"):
        input_id = normalize_global_variable_reference(
            required_string(spec.get("id"), "Each external reference requires id.")
        )
        if input_property_from_id(owner_node, input_id) is None:
            missing.append(input_id)
    if missing:
        raise ValueError("Missing owner input properties for external references: {}".format(sorted(missing)))


def ensure_owner_input(
    owner_node: PropertyGraphOwner,
    spec: dict[str, JsonValue],
    created_owner_inputs: list[JsonValue] | None = None,
) -> JsonValue:
    """Create or update one owner-node input property."""
    requested_input_id = required_string(spec.get("requested_id", spec.get("id")), "input.id is required.")
    input_id = normalize_global_variable_reference(required_string(spec.get("id"), "input.id is required."))
    value_type = string_or_default(spec.get("value_type"), "float")
    prop = input_property_from_id(owner_node, input_id)
    status = "existing"
    if prop is None:
        try:
            prop = owner_node.newProperty(input_id, sd_type_for_value_type(value_type), SDPropertyCategory.Input)
        except Exception as exc:
            raise RuntimeError("Failed to create owner input property '{}': {}".format(input_id, exc)) from exc
        if prop is None:
            raise RuntimeError("newProperty returned None for owner input property '{}'.".format(input_id))
        status = "created"
        created_owner_inputs = created_owner_inputs if created_owner_inputs is not None else []
        actual_property_id = property_id(prop) or input_id
        created_owner_inputs.append(owner_input_result(requested_input_id, actual_property_id, value_type, status))
    if "default" in spec:
        try:
            set_owner_input_default(owner_node, prop, input_id, value_type, spec.get("default"))
        except Exception as exc:
            raise OwnerInputMutationError("set_owner_input_default", str(exc)) from exc
    try:
        apply_owner_input_annotations(owner_node, prop, spec)
    except Exception as exc:
        raise OwnerInputMutationError("apply_owner_input_annotations", str(exc)) from exc
    actual_property_id = property_id(prop) or input_id
    return owner_input_result(requested_input_id, actual_property_id, value_type, status)


def owner_input_result(input_id: str, actual_property_id: str, value_type: str, status: str) -> dict[str, JsonValue]:
    """Return the MCP-facing owner input binding metadata."""
    return {
        "id": actual_property_id,
        "requested_id": input_id,
        "actual_property_id": actual_property_id,
        "function_reference": owner_input_function_reference(actual_property_id),
        "value_type": value_type,
        "status": status,
    }


def rollback_property_graph(owner_node: PropertyGraphOwner, prop: NestedProperty) -> None:
    """Remove a partially-created property graph."""
    owner_node.deletePropertyGraph(prop)


def restore_property_graph(
    owner_node: PropertyGraphOwner,
    prop: NestedProperty,
    node_id: str,
    property_id: str,
    graph_type: str,
    saved_state: dict[str, JsonValue] | None,
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None,
) -> bool:
    """Restore the graph that existed before a failed destructive replace."""
    try:
        if saved_state is None:
            rollback_property_graph(owner_node, prop)
            return True
        nested_graph = rebuild_property_graph(owner_node, prop, node_id, property_id, graph_type)
        apply_nested_graph_state_to_graph(
            nested_graph,
            saved_state,
            "replace",
            {"node_id": node_id, "property": property_id},
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        return True
    except Exception:
        return False


def input_property_from_id(owner_node: PropertyGraphOwner, input_id: str) -> NestedProperty | None:
    """Return an owner-node input property by id when it exists."""
    candidates = [input_id]
    if input_id.startswith("#"):
        candidates.append(input_id[1:])
    else:
        candidates.append("#{}".format(input_id))
    for candidate in dict.fromkeys(candidates):
        try:
            prop = owner_node.getPropertyFromId(candidate, SDPropertyCategory.Input)
            if prop is not None:
                return prop
        except Exception:
            pass
    return None


def set_owner_input_default(
    owner_node: PropertyGraphOwner,
    prop: NestedProperty,
    input_id: str,
    value_type: str,
    value: JsonValue,
) -> None:
    """Set the default value for an owner input."""
    sd_value = sd_value_for(value_type, value)
    try:
        owner_node.setPropertyValue(prop, sd_value)
        return
    except Exception:
        pass
    try:
        owner_node.setInputPropertyValueFromId(input_id, sd_value)
    except Exception as exc:
        raise RuntimeError("Failed to set default for owner input '{}': {}".format(input_id, exc)) from exc


def apply_owner_input_annotations(
    owner_node: PropertyGraphOwner,
    prop: NestedProperty,
    spec: dict[str, JsonValue],
) -> None:
    """Apply supported annotations to an owner input."""
    input_id = required_string(spec.get("id"), "input.id is required.")
    for annotation_id, value_type in INPUT_NODE_ANNOTATION_TYPES.items():
        if annotation_id not in spec:
            continue
        try:
            owner_node.setPropertyAnnotationValueFromId(
                prop, annotation_id, sd_value_for(value_type, spec[annotation_id])
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to set annotation '{}' for owner input '{}': {}".format(annotation_id, input_id, exc)
            ) from exc


def property_id(prop: NestedProperty) -> str | None:
    """Return a property id when the host object exposes one."""
    try:
        value = prop.getId()
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def owner_input_function_reference(actual_property_id: str) -> str:
    """Return the Function Graph string used by get_* nodes for an owner input."""
    return normalize_global_variable_reference(actual_property_id)


def owner_input_binding_reference(input_result: JsonValue | None, fallback_input_id: str) -> str:
    """Return the concrete owner input reference for a generated get_* node."""
    if isinstance(input_result, dict) and isinstance(input_result.get("function_reference"), str):
        return input_result["function_reference"]
    return owner_input_function_reference(fallback_input_id)


def mutation_error(
    operation: str,
    phase: str,
    target: dict[str, JsonValue],
    input_id: str,
    created_owner_inputs: list[JsonValue],
    rolled_back: bool,
    error: str,
    *,
    partial_changes_override: bool | None = None,
) -> NestedGraphMutationError:
    """Build a structured mutation error for bridge clients."""
    partial_changes = (
        partial_changes_override
        if partial_changes_override is not None
        else bool(created_owner_inputs) or not rolled_back
    )
    details: dict[str, JsonValue] = {
        "status": "error",
        "operation": operation,
        "phase": phase,
        "target": target,
        "rolled_back": rolled_back,
        "partial_changes": partial_changes,
        "error": error,
        "error_classification": classify_mutation_error(phase, error),
        "created_owner_inputs": created_owner_inputs,
        "requested_owner_input_id": input_id,
        "next_tools": nested_graph_next_tools(target),
    }
    return NestedGraphMutationError(
        "{} failed during phase '{}'; rolled_back={}, partial_changes={}".format(
            operation, phase, rolled_back, partial_changes
        ),
        details,
    )


def nested_graph_next_tools(target: dict[str, JsonValue]) -> list[JsonValue]:
    """Return concrete verification tool hints after nested graph mutations."""
    node_id = target.get("node_id")
    property_id = target.get("property")
    graph_identifier = target.get("graph_identifier")
    graph_type = target.get("graph_type") or "SDSBSFunctionGraph"
    nested_args = {"node_id": node_id, "property_id": property_id, "graph_type": graph_type}
    detail_args = {"node_id": node_id}
    preview_args = {"node_id": node_id}
    if graph_identifier:
        nested_args["graph_identifier"] = graph_identifier
        detail_args["graph_identifier"] = graph_identifier
        preview_args["graph_identifier"] = graph_identifier
    return [
        {
            "tool": "get_nested_graph_state",
            "reason": "Verify the generated Function Graph structure.",
            "arguments": nested_args,
        },
        {
            "tool": "get_node_detail",
            "reason": "Verify owner-node inputs and nested graph references.",
            "arguments": detail_args,
        },
        {
            "tool": "get_preview",
            "reason": "Render the owner node after mutation when visual output matters.",
            "arguments": preview_args,
        },
    ]


def fx_map_graph_next_tools(target: dict[str, JsonValue]) -> list[JsonValue]:
    """Return concrete verification tool hints after FX-Map graph mutations."""
    node_id = target.get("node_id")
    graph_identifier = target.get("graph_identifier")
    graph_ref: dict[str, JsonValue] = {
        "kind": "fx_map_graph",
        "owner_node_id": node_id,
        "graph_type": "SDSBSFxMapGraph",
    }
    if graph_identifier:
        graph_ref["graph_identifier"] = graph_identifier
    preview_args: dict[str, JsonValue] = {"node_id": node_id}
    if graph_identifier:
        preview_args["graph_identifier"] = graph_identifier
    return [
        {
            "tool": "get_graph",
            "reason": "Verify the generated FX-Map graph structure.",
            "arguments": {"graph_ref": graph_ref},
        },
        {
            "tool": "get_node_detail",
            "reason": "Verify owner FX-Map node inputs and outputs.",
            "arguments": preview_args,
        },
        {
            "tool": "get_preview",
            "reason": "Render the FX-Map owner node after mutation.",
            "arguments": preview_args,
        },
    ]


def clear_graph_nodes(nested_graph: MutableNestedGraph) -> None:
    """Delete all current nodes from a mutable nested graph."""
    try:
        nodes = list(nested_graph.getNodes())
    except Exception as exc:
        raise RuntimeError("Failed to list existing graph nodes before replace: {}".format(exc)) from exc
    for node in nodes:
        try:
            nested_graph.deleteNode(node)
        except Exception as exc:
            raise RuntimeError(
                "Failed to delete existing graph node '{}': {}".format(node.getIdentifier(), exc)
            ) from exc


def restore_mutable_graph(
    nested_graph: MutableNestedGraph,
    saved_state: dict[str, JsonValue],
    target: dict[str, JsonValue],
    set_node_params: ParameterSetter,
    connect_nodes: NodeConnector,
    get_node_definition: NodeDefinitionGetter,
    package_manager: LibraryPackageManager | None,
) -> bool:
    """Restore a mutable graph from a previously serialized state."""
    try:
        clear_graph_nodes(nested_graph)
        apply_nested_graph_state_to_graph(
            nested_graph,
            saved_state,
            "replace",
            target,
            set_node_params,
            connect_nodes,
            get_node_definition,
            package_manager,
        )
        return True
    except Exception:
        return False


def owner_input_get_node_definition(spec: dict[str, JsonValue]) -> str:
    """Return the Designer get_* node definition for an owner input value type."""
    value_type = string_or_default(spec.get("value_type"), "float").lower()
    if value_type in ("color", "colorrgba"):
        value_type = "float4"
    definition = INPUT_NODE_DEFINITIONS.get(value_type)
    if definition is None:
        raise ValueError("Unsupported owner input value_type '{}'.".format(value_type))
    return definition


def normalize_input_spec(value: JsonValue) -> dict[str, JsonValue]:
    """Return a flexible owner-input spec from common graph-input shapes."""
    spec = state_mapping(value)
    source = spec.get("source")
    if not spec.get("id"):
        for key in ("input_id", "name", "variable"):
            if spec.get(key):
                spec["id"] = spec[key]
                break
    if not spec.get("id") and isinstance(source, dict):
        for key in ("input_id", "id", "identifier", "name", "variable"):
            if source.get(key):
                spec["id"] = source[key]
                break
    return spec


def input_value_type(spec: dict[str, JsonValue]) -> str:
    """Return explicit owner input value_type or infer it from the default value."""
    explicit = optional_string(spec.get("value_type"))
    if explicit:
        return explicit
    if "default" in spec:
        from ..parameters.sd_values import infer_value_type

        return infer_value_type(value_input(spec["default"]))
    return "float"


def classify_mutation_error(phase: str, error: str) -> dict[str, JsonValue]:
    """Return a stable diagnostic classification for nested graph mutation failures."""
    normalized = error.lower()
    classification: dict[str, JsonValue] = {
        "kind": "unknown",
        "phase": phase,
        "retry_safe": phase == "rebuild_property_graph",
    }
    if "dataisreadonly" in normalized or "read-only" in normalized or "readonly" in normalized:
        classification.update(
            {
                "kind": "read_only",
                "scope": read_only_scope_for_phase(phase),
                "message": (
                    "The target property graph or owner node rejected mutation as read-only; "
                    "verify package writability, node instance ownership, and property editability."
                ),
            }
        )
    return classification


def read_only_scope_for_phase(phase: str) -> str:
    """Return the likely read-only scope for a failed mutation phase."""
    if phase == "rebuild_property_graph":
        return "property_graph"
    if phase.startswith("set_owner_input") or phase == "ensure_owner_input":
        return "owner_input"
    if phase == "apply_nested_graph_state":
        return "nested_graph_contents"
    return "unknown"


def sd_type_for_value_type(value_type: str) -> SDTypeValue:
    """Return an SDType object for an owner input value type."""
    normalized = value_type.lower()
    if normalized == "float":
        from sd.api.sdtypefloat import SDTypeFloat

        return SDTypeFloat.sNew()
    if normalized == "int":
        from sd.api.sdtypeint import SDTypeInt

        return SDTypeInt.sNew()
    if normalized == "bool":
        from sd.api.sdtypebool import SDTypeBool

        return SDTypeBool.sNew()
    if normalized == "string":
        from sd.api.sdtypestring import SDTypeString

        return SDTypeString.sNew()
    if normalized == "float2":
        from sd.api.sdtypefloat2 import SDTypeFloat2

        return SDTypeFloat2.sNew()
    if normalized == "float3":
        from sd.api.sdtypefloat3 import SDTypeFloat3

        return SDTypeFloat3.sNew()
    if normalized == "float4":
        from sd.api.sdtypefloat4 import SDTypeFloat4

        return SDTypeFloat4.sNew()
    if normalized == "int2":
        from sd.api.sdtypeint2 import SDTypeInt2

        return SDTypeInt2.sNew()
    if normalized == "int3":
        from sd.api.sdtypeint3 import SDTypeInt3

        return SDTypeInt3.sNew()
    if normalized == "int4":
        from sd.api.sdtypeint4 import SDTypeInt4

        return SDTypeInt4.sNew()
    if normalized in ("color", "colorrgba"):
        from sd.api.sdtypecolorrgba import SDTypeColorRGBA

        return SDTypeColorRGBA.sNew()
    raise ValueError("Unknown owner input value_type '{}'.".format(value_type))


def sd_value_for(value_type: str, value: JsonValue) -> SettableSDValue:
    """Return an SDValue object for an owner input default or annotation value."""
    return make_sd_value(value_type, value_input(value))


def value_input(value: JsonValue) -> ValueInput:
    """Return a JsonValue narrowed to the parameter value surface."""
    if isinstance(value, dict):
        for key in ("rgba", "rgb", "value", "components"):
            item = value.get(key)
            if isinstance(item, list):
                value = item
                break
        else:
            if all(key in value for key in ("red", "green", "blue")):
                value = {
                    "r": value["red"],
                    "g": value["green"],
                    "b": value["blue"],
                    **({"a": value["alpha"]} if "alpha" in value else {}),
                }
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return scalar_list(value)
    if isinstance(value, dict):
        return scalar_mapping(value)
    raise ValueError("Input node values must be scalar, scalar lists, or scalar mappings.")


def scalar_list(values: list[JsonValue]) -> list[ScalarValue]:
    """Return a list containing only scalar parameter values."""
    scalars: list[ScalarValue] = []
    for item in values:
        if isinstance(item, (bool, int, float, str)):
            scalars.append(item)
            continue
        raise ValueError("Input node list values must be scalar.")
    return scalars


def scalar_mapping(values: dict[str, JsonValue]) -> dict[str, ScalarValue]:
    """Return a mapping containing only scalar parameter values."""
    scalars: dict[str, ScalarValue] = {}
    for key, item in values.items():
        if isinstance(item, (bool, int, float, str)):
            scalars[key] = item
            continue
        raise ValueError("Input node mapping values must be scalar.")
    return scalars


def apply_connections(
    nested_graph: MutableNestedGraph,
    state: dict[str, JsonValue],
    logical_to_node: dict[str, MutableNestedNode],
    connect_nodes: NodeConnector,
) -> list[JsonValue]:
    """Apply state connections to nested graph nodes."""
    connection_results: list[JsonValue] = []
    for conn in state_maps(state.get("connections", []), "connections"):
        from_builtin = optional_string(conn.get("from_builtin"))
        if from_builtin:
            to_id = required_string(conn.get("to"), "Connection target is required.")
            if to_id not in logical_to_node:
                raise ValueError("Connection target '{}' was not created.".format(to_id))
            to_input = string_or_default(conn.get("to_input"), "input1")
            connection_results.append(
                {
                    "from_builtin": from_builtin,
                    "to": to_id,
                    "to_input": to_input,
                    "success": True,
                    "binding": "host_implicit_builtin",
                }
            )
            continue
        from_id = required_string(conn.get("from"), "Connection source is required.")
        to_id = required_string(conn.get("to"), "Connection target is required.")
        if from_id not in logical_to_node:
            raise ValueError("Connection source '{}' was not created.".format(from_id))
        if to_id not in logical_to_node:
            raise ValueError("Connection target '{}' was not created.".format(to_id))
        from_output = string_or_default(conn.get("from_output"), "unique_filter_output")
        to_input = string_or_default(conn.get("to_input"), "input1")
        connect_nodes(nested_graph, logical_to_node[from_id], from_output, logical_to_node[to_id], to_input)
        connection_results.append(
            {
                "from": from_id,
                "from_output": from_output,
                "to": to_id,
                "to_input": to_input,
                "success": True,
            }
        )
    return connection_results


def apply_output_node(
    nested_graph: MutableNestedGraph,
    value: JsonValue,
    logical_to_node: dict[str, MutableNestedNode],
) -> str | None:
    """Apply a nested graph output node from state."""
    output_id: str | None = None
    if isinstance(value, dict):
        output_id = optional_string(value.get("node"))
    elif isinstance(value, str):
        output_id = value
    if not output_id:
        return None
    if output_id not in logical_to_node:
        raise ValueError("Output node '{}' was not created.".format(output_id))
    try:
        nested_graph.setOutputNode(logical_to_node[output_id], True)
    except Exception as exc:
        raise RuntimeError("Failed to set nested graph output '{}': {}".format(output_id, exc)) from exc
    return output_id


def find_node_property(node: OwnerNode, property_id: str) -> NestedProperty:
    """Return an input or annotation property by identifier."""
    for category in (SDPropertyCategory.Input, SDPropertyCategory.Annotation):
        try:
            prop = node.getPropertyFromId(property_id, category)
            if prop:
                return prop
        except Exception:
            pass
    available: list[str] = []
    for category in (SDPropertyCategory.Input, SDPropertyCategory.Annotation):
        try:
            for prop in list(node.getProperties(category)):
                available.append(prop.getId())
        except Exception:
            pass
    raise ValueError(
        "Property '{}' not found on node '{}'. Available: {}".format(
            property_id,
            node.getIdentifier(),
            sorted(set(available)),
        )
    )


def rebuild_property_graph(
    owner_node: PropertyGraphOwner,
    prop: NestedProperty,
    node_id: str,
    property_id: str,
    graph_type: str,
) -> MutableNestedGraph:
    """Delete an existing property graph and create a fresh nested graph."""
    existing_graph: MutableNestedGraph | None = None
    try:
        existing_graph = owner_node.getPropertyGraph(prop)
    except Exception:
        existing_graph = None
    if existing_graph is not None:
        try:
            owner_node.deletePropertyGraph(prop)
        except Exception as exc:
            raise PropertyGraphRebuildError(
                "Failed to clear nested graph '{}.{}': {}".format(node_id, property_id, exc),
                partial_changes=False,
            ) from exc

    try:
        nested_graph = owner_node.newPropertyGraph(prop, graph_type)
    except Exception as exc:
        raise PropertyGraphRebuildError(
            "Failed to create nested graph '{}.{}': {}".format(node_id, property_id, exc),
            partial_changes=existing_graph is not None,
        ) from exc
    if nested_graph is None:
        raise PropertyGraphRebuildError(
            "newPropertyGraph returned None for '{}.{}'.".format(node_id, property_id),
            partial_changes=existing_graph is not None,
        )
    return nested_graph


def known_definition_ids(nested_graph: MutableNestedGraph) -> set[str]:
    """Return known node definition identifiers for a nested graph."""
    try:
        return {definition.getId() for definition in list(nested_graph.getNodeDefinitions())}
    except Exception:
        return set()
