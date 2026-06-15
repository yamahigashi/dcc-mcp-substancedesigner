"""Node parameter mutation and normalization helpers."""

from __future__ import annotations

from collections.abc import Sequence

from ..json_types import JsonValue
from .parameter_types import (
    ParameterNode,
    ParameterStatus,
    PropertySetter,
    PropertyTypeMap,
    SDPropertyCategory,
    SettableSDValue,
    ValueInput,
)
from .sd_values import ParameterValueError, coerce_value_type, infer_value_type, make_sd_value, value_type_name


def apply_node_params(node: ParameterNode, params: dict[str, JsonValue]) -> ParameterStatus:
    """Apply multiple parameter values to a node."""
    if not params:
        return {}
    results: ParameterStatus = {}
    input_type_map = property_type_map(node, SDPropertyCategory.Input)
    annotation_type_map = property_type_map(node, SDPropertyCategory.Annotation)
    for parameter_id, parameter_spec in params.items():
        if parameter_id.startswith("$"):
            results[parameter_id] = "skipped_system"
            continue
        try:
            value, value_type = parameter_value_and_type(parameter_spec)
            property_type_id = input_type_map.get(parameter_id) or annotation_type_map.get(parameter_id) or ""
            coerced_type = coerce_value_type(value_type, value, property_type_id)
            sd_value = make_sd_value(coerced_type, value)
            set_ok = set_known_parameter(node, parameter_id, sd_value, input_type_map, annotation_type_map)
            results[parameter_id] = "ok" if set_ok else "skipped"
        except Exception as exc:
            results[parameter_id] = "error: {}".format(exc)
    return results


def set_parameter_value(
    node: ParameterNode,
    node_id: str,
    parameter_id: str,
    value: JsonValue,
    value_type: str,
) -> dict[str, JsonValue]:
    """Set a single node parameter and return response metadata."""
    normalized_value = value_input(value)
    input_type_map = property_type_map(node, SDPropertyCategory.Input)
    annotation_type_map = property_type_map(node, SDPropertyCategory.Annotation)
    input_ids = set(input_type_map)
    annotation_ids = set(annotation_type_map)
    if (input_ids or annotation_ids) and parameter_id not in input_ids and parameter_id not in annotation_ids:
        all_ids = sorted(input_ids | annotation_ids)
        raise ValueError("Property '{}' not found on node '{}'. Available: {}".format(parameter_id, node_id, all_ids))

    property_type_id = input_type_map.get(parameter_id) or annotation_type_map.get(parameter_id) or ""
    coerced_type = coerce_value_type(value_type, normalized_value, property_type_id)
    try:
        sd_value = make_sd_value(coerced_type, normalized_value)
    except ParameterValueError as exc:
        raise exc.for_parameter(parameter_id) from exc
    except (TypeError, ValueError) as exc:
        raise parameter_value_error(parameter_id, coerced_type, normalized_value, str(exc)) from exc

    set_ok, last_error = try_set_parameter(
        node,
        parameter_id,
        sd_value,
        parameter_setters(node, parameter_id, input_ids, annotation_ids),
    )
    if not set_ok:
        raise RuntimeError("Failed to set '{}' on node '{}': {}".format(parameter_id, node_id, last_error))
    return {
        "node_id": node_id,
        "parameter_id": parameter_id,
        "value": json_value(normalized_value),
        "value_type": coerced_type,
    }


def property_type_map(node: ParameterNode, category: int) -> PropertyTypeMap:
    """Return property type identifiers keyed by property id."""
    type_map: PropertyTypeMap = {}
    try:
        props = list(node.getProperties(category))
    except Exception:
        props = []
    for prop in props:
        property_id = prop.getId()
        try:
            property_type = prop.getType()
            type_map[property_id] = property_type.getId() if property_type else ""
        except Exception:
            type_map[property_id] = ""
    return type_map


def set_known_parameter(
    node: ParameterNode,
    parameter_id: str,
    value: SettableSDValue,
    input_type_map: PropertyTypeMap,
    annotation_type_map: PropertyTypeMap,
) -> bool:
    """Set a parameter only when it is known as input or annotation."""
    if parameter_id in input_type_map:
        try:
            node.setInputPropertyValueFromId(parameter_id, value)
            return True
        except Exception:
            pass
    if parameter_id in annotation_type_map:
        try:
            node.setAnnotationPropertyValueFromId(parameter_id, value)
            return True
        except Exception:
            pass
    return False


def parameter_setters(
    node: ParameterNode,
    parameter_id: str,
    input_ids: set[str],
    annotation_ids: set[str],
) -> Sequence[PropertySetter]:
    """Return setters appropriate for the known property category."""
    if parameter_id in input_ids and parameter_id not in annotation_ids:
        return (node.setInputPropertyValueFromId,)
    if parameter_id in annotation_ids and parameter_id not in input_ids:
        return (node.setAnnotationPropertyValueFromId,)
    return (node.setInputPropertyValueFromId, node.setAnnotationPropertyValueFromId)


def try_set_parameter(
    node: ParameterNode,
    parameter_id: str,
    value: SettableSDValue,
    setters: Sequence[PropertySetter],
) -> tuple[bool, BaseException | None]:
    """Try setters in order and return whether one succeeded."""
    del node
    last_error: BaseException | None = None
    for setter in setters:
        try:
            setter(parameter_id, value)
            return True, None
        except Exception as exc:
            last_error = exc
    return False, last_error


def parameter_value_and_type(parameter_spec: JsonValue) -> tuple[ValueInput, str]:
    """Return normalized parameter value and requested value type."""
    if isinstance(parameter_spec, dict) and "value" in parameter_spec:
        value = value_input(parameter_spec.get("value"))
        raw_type = parameter_spec.get("type")
        value_type = raw_type if isinstance(raw_type, str) else infer_value_type(value)
        return value, value_type
    value = value_input(parameter_spec)
    return value, infer_value_type(value)


def value_input(value: JsonValue) -> ValueInput:
    """Convert JSON parameter data to an SDValue input."""
    value = normalize_value_input(value)
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return scalar_sequence(value)
    if isinstance(value, dict):
        return scalar_mapping(value)
    raise ValueError("Parameter value must be a scalar, scalar list, or scalar mapping.")


def normalize_value_input(value: JsonValue) -> JsonValue:
    """Accept common vector/color wrapper objects at the MCP boundary."""
    if not isinstance(value, dict):
        return value
    for key in ("rgba", "rgb", "value", "components"):
        item = value.get(key)
        if isinstance(item, list):
            return item
    if all(key in value for key in ("red", "green", "blue")):
        return {
            "r": value["red"],
            "g": value["green"],
            "b": value["blue"],
            **({"a": value["alpha"]} if "alpha" in value else {}),
        }
    return value


def scalar_sequence(values: list[JsonValue]) -> tuple[bool | int | float | str, ...]:
    """Return scalar sequence values."""
    scalars: list[bool | int | float | str] = []
    for value in values:
        if isinstance(value, (bool, int, float, str)):
            scalars.append(value)
            continue
        raise ValueError("Parameter list values must be scalar.")
    return tuple(scalars)


def scalar_mapping(values: dict[str, JsonValue]) -> dict[str, bool | int | float | str]:
    """Return scalar mapping values."""
    scalars: dict[str, bool | int | float | str] = {}
    for key, value in values.items():
        if isinstance(value, (bool, int, float, str)):
            scalars[key] = value
            continue
        raise ValueError("Parameter mapping values must be scalar.")
    return scalars


def json_value(value: ValueInput) -> JsonValue:
    """Return a JSON-safe representation of a value input."""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return [json_value(item) for item in value]


def parameter_value_error(
    parameter_id: str, expected_type: str, value: ValueInput, message: str
) -> ParameterValueError:
    """Return a structured value error for bridge responses."""
    return ParameterValueError(
        "Invalid value for parameter '{}': {}".format(parameter_id, message),
        expected_type=expected_type,
        received_value_type=value_type_name(value),
        parameter_id=parameter_id,
    )
