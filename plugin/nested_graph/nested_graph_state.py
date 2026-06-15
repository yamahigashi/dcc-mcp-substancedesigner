"""Coercion helpers for nested graph JSON state."""

from __future__ import annotations

from typing import cast

from sd.api.sdbasetypes import float2

from ..json_types import JsonValue
from .nested_graph_types import MutableNestedNode, PositionValue


def state_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """Return the root nested graph state mapping."""
    if not isinstance(value, dict):
        raise ValueError("state must be an object")
    return dict(value)


def target_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """Return the nested graph target mapping."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("state.target must be a mapping.")
    return dict(value)


def state_maps(value: JsonValue, field_name: str) -> list[dict[str, JsonValue]]:
    """Return a list of state mappings for a field."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("state.{} must be a list.".format(field_name))
    maps: list[dict[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("state.{} entries must be mappings.".format(field_name))
        maps.append(item)
    return maps


def node_parameter_state(spec: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return parameter state for a node specification."""
    params = parameter_map(spec.get("parameters"))
    normalize_get_node_constant(params)
    if "value" in spec:
        params.setdefault(
            "value",
            {
                "value": spec.get("value"),
                "type": spec.get("value_type", "float"),
            },
        )
    return params


def parameter_map(value: JsonValue) -> dict[str, JsonValue]:
    """Return a parameter mapping from JSON state."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("node parameters must be a mapping.")
    return dict(value)


def normalize_get_node_constant(params: dict[str, JsonValue]) -> None:
    """Normalize get_* global variable references in-place."""
    value = params.get("__constant__")
    if isinstance(value, str):
        params["__constant__"] = normalize_global_variable_reference(value)
        return
    if isinstance(value, dict):
        inner = value.get("value")
        if isinstance(inner, str):
            params["__constant__"] = {**value, "value": normalize_global_variable_reference(inner)}


def normalize_global_variable_reference(value: str) -> str:
    """Return a Designer Function Graph variable reference without an MCP-added prefix."""
    normalized = value.lstrip("#")
    return normalized or value


def set_node_position(node: MutableNestedNode, value: JsonValue) -> None:
    """Set a node position from JSON state when supplied."""
    if value is None:
        return
    if not isinstance(value, list) or len(value) < 2:
        return
    node.setPosition(cast(PositionValue, float2(coordinate(value[0]), coordinate(value[1]))))


def coordinate(value: JsonValue) -> float:
    """Coerce a JSON scalar to a graph coordinate."""
    if isinstance(value, (bool, int, float, str)):
        return float(value)
    raise ValueError("Node position entries must be scalar values.")


def required_string(value: JsonValue, message: str) -> str:
    """Return a required string value."""
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value:
        return value
    raise ValueError(message)


def optional_string(value: JsonValue) -> str | None:
    """Return a string value when supplied."""
    if isinstance(value, str) and value:
        return value
    return None


def optional_identifier(value: JsonValue) -> str | None:
    """Return a string identifier from a string or integer JSON value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    return optional_string(value)


def string_or_default(value: JsonValue, default: str) -> str:
    """Return a string value or a default."""
    if isinstance(value, str) and value:
        return value
    return default
