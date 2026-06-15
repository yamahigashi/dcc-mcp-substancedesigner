"""SDValue inference, coercion, input conversion, and construction helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from sd.api.sdbasetypes import ColorRGBA, float2, float3, float4, int2, int3, int4
from sd.api.sdusage import SDUsage
from sd.api.sdvaluearray import SDValueArray
from sd.api.sdvaluebool import SDValueBool
from sd.api.sdvaluecolorrgba import SDValueColorRGBA
from sd.api.sdvalueenum import SDValueEnum
from sd.api.sdvaluefloat import SDValueFloat
from sd.api.sdvaluefloat2 import SDValueFloat2
from sd.api.sdvaluefloat3 import SDValueFloat3
from sd.api.sdvaluefloat4 import SDValueFloat4
from sd.api.sdvalueint import SDValueInt
from sd.api.sdvalueint2 import SDValueInt2
from sd.api.sdvalueint3 import SDValueInt3
from sd.api.sdvalueint4 import SDValueInt4
from sd.api.sdvaluestring import SDValueString
from sd.api.sdvalueusage import SDValueUsage

from .parameter_types import ScalarValue, SDValue, SDValueFactory, ValueInput

VECTOR_KEYS = ("x", "y", "z", "w")
INDEX_KEYS = ("0", "1", "2", "3")
COLOR_KEYS = ("r", "g", "b", "a")
OUTPUT_USAGE_DEFAULTS = {
    "basecolor": ("RGBA", "sRGB"),
    "base_color": ("RGBA", "sRGB"),
    "diffuse": ("RGBA", "sRGB"),
    "emissive": ("RGB", "sRGB"),
    "normal": ("RGB", "linear"),
    "height": ("R", "linear"),
    "roughness": ("R", "linear"),
    "metallic": ("R", "linear"),
    "metalness": ("R", "linear"),
    "ambientocclusion": ("R", "linear"),
    "ambient_occlusion": ("R", "linear"),
    "ao": ("R", "linear"),
    "opacity": ("A", "linear"),
    "alpha": ("A", "linear"),
}


class ParameterValueError(ValueError):
    """Value conversion error with machine-readable bridge details."""

    def __init__(
        self,
        message: str,
        *,
        expected_type: str,
        received_value_type: str,
        parameter_id: str | None = None,
    ) -> None:
        """Create a conversion error for a parameter value."""
        super().__init__(message)
        self.details: dict[str, str] = {
            "expected_type": expected_type,
            "received_value_type": received_value_type,
        }
        if parameter_id is not None:
            self.details["parameter_id"] = parameter_id

    def for_parameter(self, parameter_id: str) -> ParameterValueError:
        """Return a copy with a parameter id attached."""
        return ParameterValueError(
            str(self),
            expected_type=self.details["expected_type"],
            received_value_type=self.details["received_value_type"],
            parameter_id=parameter_id,
        )


def infer_value_type(value: ValueInput) -> str:
    """Infer the default SDValue type for a Python value."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "float"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        value_count = len(value)
        if value_count == 2:
            return "float2"
        if value_count == 3:
            return "float3"
        if value_count == 4:
            return "float4"
    if isinstance(value, Mapping):
        keys = set(value)
        if {"r", "g", "b"}.issubset(keys):
            return "color"
        if {"x", "y", "z", "w"}.issubset(keys) or {"0", "1", "2", "3"}.issubset(keys):
            return "float4"
        if {"x", "y", "z"}.issubset(keys) or {"0", "1", "2"}.issubset(keys):
            return "float3"
        if {"x", "y"}.issubset(keys) or {"0", "1"}.issubset(keys):
            return "float2"
    return "float"


def coerce_value_type(inferred_type: str, value: ValueInput, sd_type_id: str | None) -> str:
    """Coerce an inferred value type to match a Substance Designer property type."""
    if not sd_type_id:
        return inferred_type
    type_id = sd_type_id.lower()

    primitive_types = {
        "int": "int",
        "float": "float",
        "bool": "bool",
        "string": "string",
        "float2": "float2",
        "float3": "float3",
        "float4": "float4",
        "int2": "int2",
        "int3": "int3",
        "int4": "int4",
        "colorrgba": "color",
        "colorrgb": "float3",
    }
    if type_id in primitive_types:
        return primitive_types[type_id]

    if "enum" in type_id:
        return "enum"

    if type_id == "sdtypearray<sdtypeusage>":
        return "usage_array"

    if type_id.startswith("sbs::") or "::" in type_id:
        if inferred_type == "float" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return "int"
        return inferred_type

    if "int" in type_id and "float" not in type_id:
        if inferred_type == "float":
            return "int"
        if inferred_type == "float4" and is_vector_input(value):
            return "int4"
        if inferred_type == "float3" and is_vector_input(value):
            return "int3"
        if inferred_type == "float2" and is_vector_input(value):
            return "int2"

    return inferred_type


def make_sd_value(value_type: str, value: ValueInput) -> SDValue:
    """Create an SDValue instance for the given adapter value type and Python value."""
    normalized_type = value_type.lower()
    if normalized_type == "float":
        return SDValueFloat.sNew(float(as_scalar(value)))
    if normalized_type == "int":
        return SDValueInt.sNew(int(as_scalar(value)))
    if normalized_type == "bool":
        return SDValueBool.sNew(bool(as_scalar(value)))
    if normalized_type == "string":
        return SDValueString.sNew(str(as_scalar(value)))
    if normalized_type == "enum":
        return make_sd_value_enum(str(as_scalar(value)))
    if normalized_type == "float2":
        vector = as_vector(value, 2)
        return SDValueFloat2.sNew(float2(float(vector[0]), float(vector[1])))
    if normalized_type == "float3":
        vector = as_vector(value, 3)
        return SDValueFloat3.sNew(float3(float(vector[0]), float(vector[1]), float(vector[2])))
    if normalized_type == "float4":
        vector = as_vector(value, 4)
        return SDValueFloat4.sNew(float4(float(vector[0]), float(vector[1]), float(vector[2]), float(vector[3])))
    if normalized_type in ("color", "colorrgba"):
        vector = as_color_vector(value)
        alpha = float(vector[3])
        return SDValueColorRGBA.sNew(ColorRGBA(float(vector[0]), float(vector[1]), float(vector[2]), alpha))
    if normalized_type == "int2":
        vector = as_vector(value, 2)
        return SDValueInt2.sNew(int2(int(vector[0]), int(vector[1])))
    if normalized_type == "int3":
        vector = as_vector(value, 3)
        return SDValueInt3.sNew(int3(int(vector[0]), int(vector[1]), int(vector[2])))
    if normalized_type == "int4":
        vector = as_vector(value, 4)
        return SDValueInt4.sNew(int4(int(vector[0]), int(vector[1]), int(vector[2]), int(vector[3])))
    if normalized_type == "usage_array":
        return make_sd_value_usage_array(value)
    raise ValueError(
        "Unknown value_type '{}'. Valid: float, int, bool, string, "
        "enum, float2, float3, float4, color, int2, int3, int4, usage_array".format(value_type)
    )


def make_sd_value_enum(value: str) -> SDValue:
    """Create an SDValueEnum for an enum id string."""
    return cast(SDValueFactory, SDValueEnum).sNew(value)


def make_sd_value_usage_array(value: ValueInput) -> SDValueArray:
    """Create the SDValueArray<SDTypeUsage> used by output node usages."""
    usage_name, components, color_space = usage_metadata(value)
    usage = SDUsage.sNew(usage_name, components, color_space)
    usage_value = SDValueUsage.sNew(usage)
    usage_type = usage_value.getType()
    array_value = SDValueArray.sNew(usage_type, 1)
    array_value.setItem(0, usage_value)
    return array_value


def usage_metadata(value: ValueInput) -> tuple[str, str, str]:
    """Return usage name, components, and color space from scalar or mapping input."""
    if isinstance(value, Mapping):
        usage_name = usage_name_from_mapping(value)
        if not usage_name:
            raise ParameterValueError(
                "Usage object must include name, usage, id, or value.",
                expected_type="usage_object",
                received_value_type=value_type_name(value),
            )
        default_components, default_color_space = usage_metadata_defaults(usage_name)
        components = str(value.get("components") or value.get("component") or default_components)
        color_space = str(value.get("color_space") or value.get("colorSpace") or default_color_space)
        return usage_name, components, color_space
    usage_name = str(as_scalar(value))
    components, color_space = usage_metadata_defaults(usage_name)
    return usage_name, components, color_space


def usage_name_from_mapping(value: Mapping[str, ScalarValue]) -> str:
    """Return the usage name field from a usage metadata mapping."""
    for key in ("name", "usage", "id", "value"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            return item
    return ""


def usage_metadata_defaults(usage_name: str) -> tuple[str, str]:
    """Return components and color space for common material output usages."""
    key = usage_name.replace(" ", "").replace("-", "").lower()
    return OUTPUT_USAGE_DEFAULTS.get(key, ("", ""))


def is_vector_input(value: ValueInput) -> bool:
    """Return whether a value carries vector components."""
    return isinstance(value, (Sequence, Mapping)) and not isinstance(value, (str, bytes, bytearray))


def as_scalar(value: ValueInput) -> ScalarValue:
    """Return a scalar value or raise when a vector was supplied."""
    if isinstance(value, (bool, int, float, str)):
        return value
    raise ParameterValueError(
        "Expected a scalar SDValue input, got {}".format(value_type_name(value)),
        expected_type="scalar",
        received_value_type=value_type_name(value),
    )


def as_vector(value: ValueInput, size: int) -> tuple[ScalarValue, ...]:
    """Return a fixed-size vector, repeating scalar input as needed."""
    if isinstance(value, (list, tuple)):
        vector = cast("list[ScalarValue] | tuple[ScalarValue, ...]", value)
        if len(value) < size:
            raise ParameterValueError(
                "Expected at least {} values, got {}".format(size, len(value)),
                expected_type="float{}".format(size),
                received_value_type=value_type_name(value),
            )
        return tuple(vector[:size])
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, ScalarValue]", value)
        return tuple(component(mapping, key, size) for key in component_keys(mapping, size))
    scalar = as_scalar(value)
    return tuple(scalar for _ in range(size))


def as_color_vector(value: ValueInput) -> tuple[ScalarValue, ScalarValue, ScalarValue, ScalarValue]:
    """Return a four-component color vector with a default alpha channel."""
    if isinstance(value, (list, tuple)):
        vector = cast("list[ScalarValue] | tuple[ScalarValue, ...]", value)
        if len(value) < 3:
            raise ParameterValueError(
                "Expected at least 3 color values, got {}".format(len(value)),
                expected_type="ColorRGBA",
                received_value_type=value_type_name(value),
            )
        alpha = vector[3] if len(vector) > 3 else 1.0
        return vector[0], vector[1], vector[2], alpha
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, ScalarValue]", value)
        missing = [key for key in COLOR_KEYS[:3] if key not in mapping]
        if missing:
            raise ParameterValueError(
                "Expected ColorRGBA mapping with r, g, b, and optional a; missing {}".format(missing),
                expected_type="ColorRGBA",
                received_value_type=value_type_name(value),
            )
        return mapping["r"], mapping["g"], mapping["b"], mapping.get("a", 1.0)
    scalar = as_scalar(value)
    return scalar, scalar, scalar, 1.0


def component_keys(value: Mapping[str, ScalarValue], size: int) -> tuple[str, ...]:
    """Return ordered component keys for a vector mapping."""
    named = VECTOR_KEYS[:size]
    indexed = INDEX_KEYS[:size]
    if all(key in value for key in named):
        return named
    if all(key in value for key in indexed):
        return indexed
    missing = [key for key in named if key not in value]
    raise ParameterValueError(
        "Expected float{} mapping with {}; missing {}".format(size, ", ".join(named), missing),
        expected_type="float{}".format(size),
        received_value_type=value_type_name(value),
    )


def component(value: Mapping[str, ScalarValue], key: str, size: int) -> ScalarValue:
    """Return one scalar vector component."""
    item = value[key]
    if isinstance(item, (bool, int, float, str)):
        return item
    raise ParameterValueError(
        "Expected scalar component '{}' for float{}, got {}".format(key, size, value_type_name(item)),
        expected_type="float{}".format(size),
        received_value_type=value_type_name(item),
    )


def value_type_name(value: ValueInput) -> str:
    """Return a stable JSON-facing type name for diagnostics."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, Mapping):
        return "dict"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "list"
    return type(value).__name__
