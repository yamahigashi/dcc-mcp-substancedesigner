"""Tests for plugin-side parameter helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PARAMETER_APPLY_PATH = REPO_ROOT / "plugin" / "parameters" / "parameters.py"
PARAMETER_SINGLE_SET_PATH = REPO_ROOT / "plugin" / "parameters" / "parameters.py"


class FakeSDValue:
    """Fake SDValue handle."""

    def __init__(self, value: FakeValue) -> None:
        """Store the wrapped value."""
        self.value = value

    @staticmethod
    def sNew(value: FakeValue) -> FakeSDValue:
        """Create a fake SDValue."""
        return FakeSDValue(value)

    def getType(self) -> FakeType:
        """Return a fake value type."""
        return FakeType("unknown")


class FakeSDValueUsage(FakeSDValue):
    """Fake SDValueUsage handle."""

    @staticmethod
    def sNew(value: object) -> FakeSDValueUsage:
        """Create a fake usage value."""
        if not isinstance(value, FakeSDUsage):
            raise TypeError("SDValueUsage.sNew requires SDUsage")
        return FakeSDValueUsage(value)

    def getType(self) -> FakeType:
        """Return usage type."""
        return FakeType("SDTypeUsage")


class FakeSDValueArray:
    """Fake SDValueArray handle."""

    def __init__(self, value_type: FakeType, size: int) -> None:
        """Store array type and items."""
        self.value_type = value_type
        self.items: list[object | None] = [None] * size

    @staticmethod
    def sNew(value_type: FakeType, size: int) -> FakeSDValueArray:
        """Create a fake SDValueArray."""
        return FakeSDValueArray(value_type, size)

    def setItem(self, index: int, value: object) -> None:
        """Set a fake array item."""
        if self.value_type.getId() == "SDTypeUsage" and not isinstance(value, FakeSDValueUsage):
            raise TypeError("SDTypeUsage arrays only accept SDValueUsage items")
        self.items[index] = value


class FakeSDUsage:
    """Fake SDUsage handle."""

    def __init__(self, name: str, components: str, color_space: str) -> None:
        """Store usage metadata."""
        self.name = name
        self.components = components
        self.color_space = color_space

    @staticmethod
    def sNew(name: str, components: str, color_space: str) -> FakeSDUsage:
        """Create a fake usage."""
        return FakeSDUsage(name, components, color_space)


class FakeValue:
    """Fake host value."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        return "fake"


class FakeType:
    """Fake property type."""

    def __init__(self, type_id: str) -> None:
        """Store a type identifier."""
        self.type_id = type_id

    def getId(self) -> str:
        """Return the type identifier."""
        return self.type_id


class FakeProperty:
    """Fake parameter property."""

    def __init__(self, property_id: str, type_id: str) -> None:
        """Store property metadata."""
        self.property_id = property_id
        self.type_id = type_id

    def getId(self) -> str:
        """Return the property identifier."""
        return self.property_id

    def getType(self) -> FakeType:
        """Return the fake type."""
        return FakeType(self.type_id)


class FakeNode:
    """Fake node with input and annotation parameters."""

    def __init__(self) -> None:
        """Initialize fake node state."""
        self.input_props = [
            FakeProperty("gain", "float"),
            FakeProperty("offset", "float2"),
            FakeProperty("normal", "float3"),
            FakeProperty("bounds", "float4"),
            FakeProperty("tint", "ColorRGBA"),
            FakeProperty("blendmode", "enum"),
        ]
        self.annotation_props = [FakeProperty("label", "string"), FakeProperty("usages", "SDTypeArray<SDTypeUsage>")]
        self.inputs: dict[str, FakeSDValue] = {}
        self.annotations: dict[str, FakeSDValue] = {}
        self.setter_calls: list[tuple[str, str]] = []

    def getProperties(self, category: int) -> list[FakeProperty]:
        """Return fake properties for a category."""
        if category == 0:
            return self.input_props
        return self.annotation_props

    def setInputPropertyValueFromId(self, parameter_id: str, value: FakeSDValue) -> None:
        """Record a fake input value."""
        self.setter_calls.append(("input", parameter_id))
        self.inputs[parameter_id] = value

    def setAnnotationPropertyValueFromId(self, parameter_id: str, value: FakeSDValue) -> None:
        """Record a fake annotation value."""
        self.setter_calls.append(("annotation", parameter_id))
        self.annotations[parameter_id] = value


def test_apply_node_params_sets_inputs_annotations_and_skips_system_params() -> None:
    """Parameter helper sets known params and skips host system params."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.apply_node_params(
        node,
        {
            "gain": 0.5,
            "offset": {"value": [1, 2], "type": "float2"},
            "label": {"value": "hello", "type": "string"},
            "$outputsize": [8, 8],
            "missing": True,
        },
    )

    assert result == {
        "gain": "ok",
        "offset": "ok",
        "label": "ok",
        "$outputsize": "skipped_system",
        "missing": "skipped",
    }
    assert set(node.inputs) == {"gain", "offset"}
    assert set(node.annotations) == {"label"}


def test_set_parameter_value_validates_known_properties() -> None:
    """Single parameter setter validates known node properties."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(node, "node_a", "gain", 0.25, "float")

    assert result == {"node_id": "node_a", "parameter_id": "gain", "value": 0.25, "value_type": "float"}
    assert "gain" in node.inputs
    assert node.setter_calls == [("input", "gain")]


def test_set_parameter_value_accepts_enum_id_strings() -> None:
    """Single parameter setter accepts enum id strings for enum properties."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(node, "node_a", "blendmode", "multiply", "string")

    assert result == {"node_id": "node_a", "parameter_id": "blendmode", "value": "multiply", "value_type": "enum"}
    assert node.inputs["blendmode"].value == "multiply"
    assert node.setter_calls == [("input", "blendmode")]


def test_set_parameter_value_uses_annotation_setter_directly() -> None:
    """Single parameter setter does not route known annotations through input setters."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(node, "node_a", "label", "Base Color", "float")

    assert result == {"node_id": "node_a", "parameter_id": "label", "value": "Base Color", "value_type": "string"}
    assert node.annotations["label"].value == "Base Color"
    assert node.setter_calls == [("annotation", "label")]


def test_set_parameter_value_builds_usage_array_for_output_usages_annotation() -> None:
    """Single parameter setter converts public usage strings to SDTypeUsage arrays."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(node, "node_a", "usages", "baseColor", "string")

    usage_array = node.annotations["usages"]
    usage_value = usage_array.items[0].value
    assert result == {"node_id": "node_a", "parameter_id": "usages", "value": "baseColor", "value_type": "usage_array"}
    assert usage_value.name == "baseColor"
    assert usage_value.components == "RGBA"
    assert usage_value.color_space == "sRGB"
    assert node.setter_calls == [("annotation", "usages")]


def test_set_parameter_value_builds_usage_array_from_usage_object() -> None:
    """Usage array accepts explicit usage metadata."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(
        node,
        "node_a",
        "usages",
        {"name": "baseColor", "components": "RGBA", "color_space": "Linear"},
        "usage_array",
    )

    usage_array = node.annotations["usages"]
    usage_value = usage_array.items[0].value
    assert result == {
        "node_id": "node_a",
        "parameter_id": "usages",
        "value": {"name": "baseColor", "components": "RGBA", "color_space": "Linear"},
        "value_type": "usage_array",
    }
    assert usage_value.name == "baseColor"
    assert usage_value.components == "RGBA"
    assert usage_value.color_space == "Linear"


def test_set_parameter_value_accepts_get_node_detail_vector_mappings() -> None:
    """Single parameter setter accepts get_node_detail vector mapping values."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.set_parameter_value(node, "node_a", "offset", {"x": 0.46, "y": 0.014}, "float2")

    assert result == {
        "node_id": "node_a",
        "parameter_id": "offset",
        "value": {"x": 0.46, "y": 0.014},
        "value_type": "float2",
    }
    assert node.inputs["offset"].value == (0.46, 0.014)


def test_set_parameter_value_accepts_float3_float4_and_color_mappings() -> None:
    """Single parameter setter accepts vector and color mapping values."""
    module = _load_parameters_module()
    node = FakeNode()

    module.set_parameter_value(node, "node_a", "normal", {"x": 1, "y": 0, "z": 0.5}, "float3")
    module.set_parameter_value(node, "node_a", "bounds", {"x": 1, "y": 2, "z": 3, "w": 4}, "float4")
    module.set_parameter_value(node, "node_a", "tint", {"r": 0, "g": 0.25, "b": 0.5, "a": 1}, "ColorRGBA")

    assert node.inputs["normal"].value == (1.0, 0.0, 0.5)
    assert node.inputs["bounds"].value == (1.0, 2.0, 3.0, 4.0)
    assert node.inputs["tint"].value == (0.0, 0.25, 0.5, 1.0)


def test_set_parameter_value_accepts_wrapped_color_aliases() -> None:
    """Single parameter setter accepts common color wrapper objects."""
    module = _load_parameters_module()
    node = FakeNode()

    module.set_parameter_value(node, "node_a", "tint", {"rgba": [0.1, 0.2, 0.3, 0.4]}, "color")
    rgba_value = node.inputs["tint"].value
    module.set_parameter_value(node, "node_a", "tint", {"red": 0.5, "green": 0.6, "blue": 0.7}, "color")

    assert rgba_value == (0.1, 0.2, 0.3, 0.4)
    assert node.inputs["tint"].value == (0.5, 0.6, 0.7, 1.0)


def test_apply_node_params_accepts_mapping_values() -> None:
    """Bulk parameter helper accepts mapping values from serialized node detail."""
    module = _load_parameters_module()
    node = FakeNode()

    result = module.apply_node_params(node, {"offset": {"x": 0.5, "y": 0.25}, "tint": {"r": 0, "g": 0, "b": 0}})

    assert result == {"offset": "ok", "tint": "ok"}
    assert node.inputs["offset"].value == (0.5, 0.25)
    assert node.inputs["tint"].value == (0.0, 0.0, 0.0, 1.0)


def test_set_parameter_value_reports_structured_value_errors() -> None:
    """Single parameter setter exposes parameter diagnostics for bridge errors."""
    module = _load_parameters_module()
    node = FakeNode()

    try:
        module.set_parameter_value(node, "node_a", "offset", {"x": 0.46}, "float2")
    except Exception as exc:
        assert str(exc) == "Expected float2 mapping with x, y; missing ['y']"
        assert exc.details == {
            "parameter_id": "offset",
            "expected_type": "float2",
            "received_value_type": "dict",
        }
    else:
        raise AssertionError("Expected structured parameter value error")


def _load_parameters_module() -> types.ModuleType:
    """Load concrete parameter helper modules with fake Substance Designer modules."""
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    module = _load_module("plugin.parameters.parameters", PARAMETER_APPLY_PATH)
    single_set = _load_module("plugin.parameters.parameters", PARAMETER_SINGLE_SET_PATH)
    module.set_parameter_value = single_set.set_parameter_value
    _remove_fake_modules()
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load one module from disk without writing bytecode."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


def _install_fake_sd_modules() -> None:
    sd_module = types.ModuleType("sd")
    api_module = types.ModuleType("sd.api")
    sys.modules["sd"] = sd_module
    sys.modules["sd.api"] = api_module

    base_types = types.ModuleType("sd.api.sdbasetypes")
    base_types.ColorRGBA = _fake_constructor
    base_types.float2 = _fake_constructor
    base_types.float3 = _fake_constructor
    base_types.float4 = _fake_constructor
    base_types.int2 = _fake_constructor
    base_types.int3 = _fake_constructor
    base_types.int4 = _fake_constructor
    sys.modules["sd.api.sdbasetypes"] = base_types

    property_module = types.ModuleType("sd.api.sdproperty")

    class FakeCategory:
        """Fake SD property categories."""

        Input = 0
        Annotation = 1
        Output = 2

    property_module.SDPropertyCategory = FakeCategory
    sys.modules["sd.api.sdproperty"] = property_module

    for module_name, class_name in {
        "sd.api.sdvaluebool": "SDValueBool",
        "sd.api.sdvaluecolorrgba": "SDValueColorRGBA",
        "sd.api.sdvaluefloat": "SDValueFloat",
        "sd.api.sdvaluefloat2": "SDValueFloat2",
        "sd.api.sdvaluefloat3": "SDValueFloat3",
        "sd.api.sdvaluefloat4": "SDValueFloat4",
        "sd.api.sdvalueenum": "SDValueEnum",
        "sd.api.sdvalueint": "SDValueInt",
        "sd.api.sdvalueint2": "SDValueInt2",
        "sd.api.sdvalueint3": "SDValueInt3",
        "sd.api.sdvalueint4": "SDValueInt4",
        "sd.api.sdvaluestring": "SDValueString",
    }.items():
        value_module = types.ModuleType(module_name)
        setattr(value_module, class_name, FakeSDValue)
        sys.modules[module_name] = value_module
    array_module = types.ModuleType("sd.api.sdvaluearray")
    array_module.SDValueArray = FakeSDValueArray
    sys.modules["sd.api.sdvaluearray"] = array_module

    usage_module = types.ModuleType("sd.api.sdusage")
    usage_module.SDUsage = FakeSDUsage
    sys.modules["sd.api.sdusage"] = usage_module

    value_usage_module = types.ModuleType("sd.api.sdvalueusage")
    value_usage_module.SDValueUsage = FakeSDValueUsage
    sys.modules["sd.api.sdvalueusage"] = value_usage_module


def _remove_fake_modules() -> None:
    """Remove fake modules installed for parameter helper loading."""
    for module_name in [
        "plugin",
        "plugin.parameters.parameters",
        "plugin.parameters.parameters",
        "plugin.parameters.parameters",
        "plugin.parameters.parameters",
        "plugin.parameters.parameter_types",
        "plugin.parameters.parameters",
        "plugin.parameters.sd_values",
        "plugin.parameters.sd_values",
        "plugin.parameters.sd_values",
        "plugin.parameters.parameter_types",
        "sd",
        "sd.api",
        "sd.api.sdbasetypes",
        "sd.api.sdproperty",
        "sd.api.sdvaluebool",
        "sd.api.sdvaluecolorrgba",
        "sd.api.sdvaluefloat",
        "sd.api.sdvaluefloat2",
        "sd.api.sdvaluefloat3",
        "sd.api.sdvaluefloat4",
        "sd.api.sdvalueenum",
        "sd.api.sdvalueint",
        "sd.api.sdvalueint2",
        "sd.api.sdvalueint3",
        "sd.api.sdvalueint4",
        "sd.api.sdvaluestring",
        "sd.api.sdvaluearray",
        "sd.api.sdusage",
        "sd.api.sdvalueusage",
    ]:
        sys.modules.pop(module_name, None)


def _fake_constructor(*values: FakeValue) -> tuple[FakeValue, ...]:
    """Return constructor arguments as a tuple."""
    return values
