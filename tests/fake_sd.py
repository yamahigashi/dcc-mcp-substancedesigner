"""Shared fake Substance Designer SDK modules for host-independent plugin tests."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterable
from typing import TypeAlias

ScalarValue: TypeAlias = bool | int | float | str
ConstructorValue: TypeAlias = ScalarValue | tuple[ScalarValue, ...]


class FakeSDPropertyCategory:
    """Fake SD property categories."""

    Input = 0
    Output = 1
    Annotation = 2


class FakeSDValue:
    """Fake SDValue wrapper used by test host objects."""

    def __init__(self, value: ConstructorValue) -> None:
        """Store the wrapped value."""
        self.value = value

    @staticmethod
    def sNew(value: ConstructorValue) -> "FakeSDValue":
        """Create a fake SDValue."""
        return FakeSDValue(value)

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        return repr(self.value)

    def __eq__(self, other: object) -> bool:
        """Compare wrapped values for test assertions."""
        if isinstance(other, FakeSDValue):
            return self.value == other.value
        return self.value == other

    def getType(self) -> FakeSDType:
        """Return a fake SDValue type."""
        return FakeSDType("unknown")


class FakeSDValueArray:
    """Fake SDValueArray wrapper."""

    def __init__(self, value_type: FakeSDType, size: int) -> None:
        """Store array type and items."""
        self.value_type = value_type
        self.items: list[object | None] = [None] * size

    @staticmethod
    def sNew(value_type: FakeSDType, size: int) -> "FakeSDValueArray":
        """Create a fake array."""
        return FakeSDValueArray(value_type, size)

    def setItem(self, index: int, value: object) -> None:
        """Set an item by index."""
        if self.value_type.getId() == "SDTypeUsage" and not isinstance(value, FakeSDValueUsage):
            raise TypeError("SDTypeUsage arrays only accept SDValueUsage items")
        self.items[index] = value


class FakeSDUsage:
    """Fake SDUsage wrapper."""

    def __init__(self, name: str, components: str, color_space: str) -> None:
        """Store usage metadata."""
        self.name = name
        self.components = components
        self.color_space = color_space

    @staticmethod
    def sNew(name: str, components: str, color_space: str) -> "FakeSDUsage":
        """Create a fake usage."""
        return FakeSDUsage(name, components, color_space)


class FakeSDValueUsage(FakeSDValue):
    """Fake SDValueUsage wrapper."""

    @staticmethod
    def sNew(value: object) -> "FakeSDValueUsage":
        """Create a fake usage value."""
        if not isinstance(value, FakeSDUsage):
            raise TypeError("SDValueUsage.sNew requires SDUsage")
        return FakeSDValueUsage(value)

    def getType(self) -> FakeSDType:
        """Return usage value type."""
        return FakeSDType("SDTypeUsage")


class FakeSDType:
    """Fake SDType value."""

    def __init__(self, type_id: str) -> None:
        """Store a type identifier."""
        self.type_id = type_id

    @staticmethod
    def sNew() -> "FakeSDType":
        """Create a generic fake SDType."""
        return FakeSDType("unknown")

    def getId(self) -> str:
        """Return the type identifier."""
        return self.type_id


def fake_constructor(*values: ScalarValue) -> tuple[ScalarValue, ...]:
    """Return constructor arguments as a tuple."""
    return values


def install_fake_sd_modules(extra_modules: Iterable[str] = ()) -> None:
    """Install fake ``sd`` SDK modules when the real host SDK is unavailable."""
    sd_module = sys.modules.setdefault("sd", types.ModuleType("sd"))
    api_module = sys.modules.setdefault("sd.api", types.ModuleType("sd.api"))
    sd_module.api = api_module

    base_types = types.ModuleType("sd.api.sdbasetypes")
    for name in ("ColorRGBA", "float2", "float3", "float4", "int2", "int3", "int4"):
        setattr(base_types, name, fake_constructor)
    sys.modules.setdefault("sd.api.sdbasetypes", base_types)

    property_module = types.ModuleType("sd.api.sdproperty")
    property_module.SDPropertyCategory = FakeSDPropertyCategory
    sys.modules.setdefault("sd.api.sdproperty", property_module)

    value_modules = {
        "sd.api.sdvalue": "SDValue",
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
    }
    for module_name, class_name in value_modules.items():
        value_module = types.ModuleType(module_name)
        setattr(value_module, class_name, FakeSDValue)
        sys.modules.setdefault(module_name, value_module)

    array_module = types.ModuleType("sd.api.sdvaluearray")
    array_module.SDValueArray = FakeSDValueArray
    sys.modules.setdefault("sd.api.sdvaluearray", array_module)

    usage_module = types.ModuleType("sd.api.sdusage")
    usage_module.SDUsage = FakeSDUsage
    sys.modules.setdefault("sd.api.sdusage", usage_module)

    value_usage_module = types.ModuleType("sd.api.sdvalueusage")
    value_usage_module.SDValueUsage = FakeSDValueUsage
    sys.modules.setdefault("sd.api.sdvalueusage", value_usage_module)

    type_modules = {
        "sd.api.sdtypefloat": ("SDTypeFloat", "float"),
        "sd.api.sdtypeint": ("SDTypeInt", "int"),
        "sd.api.sdtypebool": ("SDTypeBool", "bool"),
        "sd.api.sdtypestring": ("SDTypeString", "string"),
        "sd.api.sdtypefloat2": ("SDTypeFloat2", "float2"),
        "sd.api.sdtypefloat3": ("SDTypeFloat3", "float3"),
        "sd.api.sdtypefloat4": ("SDTypeFloat4", "float4"),
        "sd.api.sdtypeint2": ("SDTypeInt2", "int2"),
        "sd.api.sdtypeint3": ("SDTypeInt3", "int3"),
        "sd.api.sdtypeint4": ("SDTypeInt4", "int4"),
        "sd.api.sdtypecolorrgba": ("SDTypeColorRGBA", "colorrgba"),
    }
    for module_name, (class_name, type_id) in type_modules.items():
        type_module = types.ModuleType(module_name)
        setattr(type_module, class_name, _type_factory(type_id))
        sys.modules.setdefault(module_name, type_module)

    for module_name in extra_modules:
        sys.modules.setdefault(module_name, types.ModuleType(module_name))


def _type_factory(type_id: str) -> type[FakeSDType]:
    """Return a fake SDType class for one type id."""

    class TypedFakeSDType(FakeSDType):
        """Fake SDType with a stable type id."""

        @staticmethod
        def sNew() -> FakeSDType:
            """Create a fake SDType for this type id."""
            return FakeSDType(type_id)

    return TypedFakeSDType
