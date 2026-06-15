"""Tests for plugin-side unified control helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLS_PATH = REPO_ROOT / "plugin" / "controls.py"


class FakeSDValue:
    """Fake SDValue handle."""

    def __init__(self, value: object) -> None:
        self.value = value

    @staticmethod
    def sNew(value: object) -> FakeSDValue:
        return FakeSDValue(value)


class FakeType:
    """Fake property type."""

    def __init__(self, type_id: str) -> None:
        self.type_id = type_id

    def getId(self) -> str:
        return self.type_id


class FakeProperty:
    """Fake property."""

    def __init__(self, property_id: str, type_id: str = "float", label: str | None = None) -> None:
        self.property_id = property_id
        self.type_id = type_id
        self.label = label

    def getId(self) -> str:
        return self.property_id

    def getType(self) -> FakeType:
        return FakeType(self.type_id)

    def getLabel(self) -> str | None:
        return self.label


class FakeGraph:
    """Fake graph with input properties."""

    def __init__(self) -> None:
        self.inputs = [FakeProperty("color_root", "ColorRGBA", "Color Root"), FakeProperty("$outputsize", "int2")]
        self.values = {"color_root": FakeSDValue((1.0, 0.8, 0.4, 1.0))}
        self.property_annotations: dict[tuple[str, str], FakeSDValue] = {}

    def getIdentifier(self) -> str:
        return "GraphA"

    def getProperties(self, category: int) -> list[FakeProperty]:
        return self.inputs if category == 0 else []

    def getPropertyFromId(self, property_id: str, category: int) -> FakeProperty | None:
        if category != 0:
            return None
        for prop in self.inputs:
            if prop.getId() == property_id:
                return prop
        return None

    def getPropertyValue(self, prop: FakeProperty) -> FakeSDValue | None:
        return self.values.get(prop.getId())

    def newProperty(self, property_id: str, property_type: FakeType, category: int) -> FakeProperty | None:
        if category != 0:
            return None
        prop = FakeProperty(property_id, property_type.getId())
        self.inputs.append(prop)
        return prop

    def setInputPropertyValueFromId(self, property_id: str, value: FakeSDValue) -> None:
        self.values[property_id] = value

    def setPropertyAnnotationValueFromId(self, prop: FakeProperty, annotation_id: str, value: FakeSDValue) -> None:
        self.property_annotations[(prop.getId(), annotation_id)] = value

    def getPropertyAnnotationValueFromId(self, prop: FakeProperty, annotation_id: str) -> FakeSDValue | None:
        return self.property_annotations.get((prop.getId(), annotation_id))


class FakeNode(FakeGraph):
    """Fake node with input and annotation controls."""

    def __init__(self) -> None:
        self.inputs = [FakeProperty("gain", "float")]
        self.annotations = [FakeProperty("label", "string")]
        self.values = {"gain": FakeSDValue(0.5), "label": FakeSDValue("Old")}

    def getProperties(self, category: int) -> list[FakeProperty]:
        if category == 0:
            return self.inputs
        if category == 1:
            return self.annotations
        return []

    def setAnnotationPropertyValueFromId(self, property_id: str, value: FakeSDValue) -> None:
        self.values[property_id] = value


def test_graph_input_controls_list_and_set_values() -> None:
    module = _load_controls_module()
    graph = FakeGraph()
    prop = graph.getPropertyFromId("color_root", 0)
    assert prop is not None
    graph.setPropertyAnnotationValueFromId(prop, "group", FakeSDValue("Palette"))

    listed = module.list_graph_inputs(graph, _serialize)
    updated = module.set_graph_input(graph, "color_root", [0.2, 0.3, 0.4, 1.0], "ColorRGBA", _serialize)

    assert listed["inputs"][0]["id"] == "color_root"
    assert listed["inputs"][0]["role"] == "graph_input"
    assert listed["inputs"][0]["group"] == "Palette"
    assert listed["inputs"][0]["constraints"]["group"] == "Palette"
    assert "$outputsize" not in [item["id"] for item in listed["inputs"]]
    assert updated["status"] == "updated"
    assert graph.values["color_root"].value == (0.2, 0.3, 0.4, 1.0)


def test_graph_input_set_creates_missing_input_with_metadata() -> None:
    module = _load_controls_module()
    _install_fake_sd_modules()
    try:
        graph = FakeGraph()

        created = module.set_graph_input(
            graph,
            "#shaft_width",
            0.25,
            "float",
            _serialize,
            {"description": "Shaft width", "group": "Dimensions", "min": 0, "max": 1, "step": 0.01},
        )

        assert created["status"] == "created"
        assert created["input_id"] == "shaft_width"
        assert graph.getPropertyFromId("shaft_width", 0) is not None
        assert graph.values["shaft_width"].value == 0.25
        assert graph.property_annotations[("shaft_width", "description")].value == "Shaft width"
        assert graph.property_annotations[("shaft_width", "min")].value == 0

        listed = module.list_graph_inputs(graph, _serialize)
        shaft_width = next(item for item in listed["inputs"] if item["id"] == "shaft_width")
        assert shaft_width["description"] == "Shaft width"
        assert shaft_width["group"] == "Dimensions"
        assert shaft_width["min"] == 0
        assert shaft_width["max"] == 1
        assert shaft_width["step"] == 0.01
        assert shaft_width["constraints"]["group"] == "Dimensions"
        assert shaft_width["constraints"]["min"] == 0
        assert shaft_width["constraints"]["max"] == 1
        assert shaft_width["writable"] is True
        assert shaft_width["writable_source"] == "setInputPropertyValueFromId"
    finally:
        _remove_fake_modules()


def test_graph_control_listing_reads_graph_input_metadata() -> None:
    module = _load_controls_module()
    graph = FakeGraph()
    prop = graph.getPropertyFromId("color_root", 0)
    assert prop is not None
    graph.setPropertyAnnotationValueFromId(prop, "group", FakeSDValue("Palette"))
    graph.setPropertyAnnotationValueFromId(prop, "editor", FakeSDValue("color"))
    graph.setPropertyAnnotationValueFromId(prop, "clamp", FakeSDValue(True))

    controls = module.list_controls(
        {"kind": "graph"},
        resolve_graph=lambda _graph_identifier: graph,
        find_node=lambda _graph, _node_id: FakeNode(),
        serialize_value=_serialize,
    )

    color_root = controls["controls"][0]
    assert color_root["group"] == "Palette"
    assert color_root["editor"] == "color"
    assert color_root["clamp"] is True
    assert color_root["constraints"]["group"] == "Palette"


def test_node_controls_include_inputs_and_annotations() -> None:
    module = _load_controls_module()
    node = FakeNode()

    controls = module.node_controls(node, "node_a", _serialize)

    assert [item["id"] for item in controls] == ["gain", "label"]
    assert controls[1]["source"]["category"] == "annotation"


def test_owner_input_control_reads_metadata() -> None:
    module = _load_controls_module()
    owner = FakeGraph()
    prop = owner.getPropertyFromId("color_root", 0)
    assert prop is not None
    owner.setPropertyAnnotationValueFromId(prop, "description", FakeSDValue("Root color"))
    owner.setPropertyAnnotationValueFromId(prop, "group", FakeSDValue("Palette"))

    control = module.owner_input_control(
        owner,
        "node_a",
        "outputcolor",
        "color_root",
        "read_color_root",
        "sbs::function::get_float4",
        _serialize,
    )

    assert control["description"] == "Root color"
    assert control["group"] == "Palette"
    assert control["constraints"]["group"] == "Palette"
    assert control["writable"] is True


def _serialize(value: object) -> object:
    if isinstance(value, FakeSDValue):
        return value.value
    return value


def _load_controls_module() -> types.ModuleType:
    _install_fake_sd_modules()
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]
    sys.modules["plugin"] = package
    try:
        return _load_module("plugin.controls", CONTROLS_PATH)
    finally:
        _remove_fake_modules()


def _load_module(module_name: str, path: Path) -> types.ModuleType:
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
    property_module.SDPropertyCategory = types.SimpleNamespace(Input=0, Annotation=1, Output=2)
    sys.modules["sd.api.sdproperty"] = property_module

    for module_name, class_name in {
        "sd.api.sdtypebool": "SDTypeBool",
        "sd.api.sdtypecolorrgba": "SDTypeColorRGBA",
        "sd.api.sdtypefloat": "SDTypeFloat",
        "sd.api.sdtypefloat2": "SDTypeFloat2",
        "sd.api.sdtypefloat3": "SDTypeFloat3",
        "sd.api.sdtypefloat4": "SDTypeFloat4",
        "sd.api.sdtypeint": "SDTypeInt",
        "sd.api.sdtypeint2": "SDTypeInt2",
        "sd.api.sdtypeint3": "SDTypeInt3",
        "sd.api.sdtypeint4": "SDTypeInt4",
        "sd.api.sdtypestring": "SDTypeString",
    }.items():
        type_module = types.ModuleType(module_name)
        setattr(
            type_module,
            class_name,
            types.SimpleNamespace(sNew=lambda type_id=class_name: FakeType(type_id.replace("SDType", "").lower())),
        )
        sys.modules[module_name] = type_module

    for module_name, class_name in {
        "sd.api.sdvaluebool": "SDValueBool",
        "sd.api.sdvaluecolorrgba": "SDValueColorRGBA",
        "sd.api.sdvalueenum": "SDValueEnum",
        "sd.api.sdvaluefloat": "SDValueFloat",
        "sd.api.sdvaluefloat2": "SDValueFloat2",
        "sd.api.sdvaluefloat3": "SDValueFloat3",
        "sd.api.sdvaluefloat4": "SDValueFloat4",
        "sd.api.sdvalueint": "SDValueInt",
        "sd.api.sdvalueint2": "SDValueInt2",
        "sd.api.sdvalueint3": "SDValueInt3",
        "sd.api.sdvalueint4": "SDValueInt4",
        "sd.api.sdvaluestring": "SDValueString",
    }.items():
        value_module = types.ModuleType(module_name)
        setattr(value_module, class_name, FakeSDValue)
        sys.modules[module_name] = value_module


def _remove_fake_modules() -> None:
    for module_name in list(sys.modules):
        if (
            module_name == "sd"
            or module_name.startswith("sd.")
            or module_name == "plugin"
            or module_name.startswith("plugin.")
        ):
            sys.modules.pop(module_name, None)


def _fake_constructor(*values: object) -> tuple[object, ...]:
    return values
