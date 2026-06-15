"""Protocols and aliases for parameter and SDValue helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Protocol, TypeAlias

from sd.api.sdbasetypes import ColorRGBA, float2, float3, float4, int2, int3, int4
from sd.api.sdproperty import SDPropertyCategory
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

__all__ = [
    "MappedValue",
    "ParameterNode",
    "ParameterProperty",
    "ParameterStatus",
    "ParameterType",
    "PrimitiveSDValue",
    "PropertySetter",
    "PropertyTypeMap",
    "ReprFallback",
    "SDPropertyCategory",
    "SDValue",
    "SDValueFactory",
    "ScalarValue",
    "SetterResult",
    "SettableSDValue",
    "UsageSDValue",
    "ValueInput",
    "VectorValue",
]

ParameterStatus: TypeAlias = dict[str, str]
PropertyTypeMap: TypeAlias = dict[str, str]
SetterResult: TypeAlias = tuple[bool, BaseException | None]
ScalarValue: TypeAlias = bool | int | float | str
VectorValue: TypeAlias = list[ScalarValue] | tuple[ScalarValue, ...]
MappedValue: TypeAlias = Mapping[str, ScalarValue]
ValueInput: TypeAlias = ScalarValue | VectorValue | MappedValue
PrimitiveSDValue: TypeAlias = (
    SDValueBool
    | SDValueColorRGBA
    | SDValueFloat
    | SDValueFloat2
    | SDValueFloat3
    | SDValueFloat4
    | SDValueEnum
    | SDValueInt
    | SDValueInt2
    | SDValueInt3
    | SDValueInt4
    | SDValueString
)
UsageSDValue: TypeAlias = SDValueUsage | SDValueArray
SettableSDValue: TypeAlias = PrimitiveSDValue | UsageSDValue
SDValue: TypeAlias = SettableSDValue
type HostConstructorValue = ScalarValue | float2 | float3 | float4 | int2 | int3 | int4 | ColorRGBA


class SDValueFactory(Protocol):
    """Factory protocol implemented by Substance Designer SDValue classes."""

    @staticmethod
    def sNew(value: HostConstructorValue) -> PrimitiveSDValue:
        """Create an SDValue from a host API value."""
        ...


class ReprFallback(Protocol):
    """Protocol for values that support diagnostic representation."""

    def __repr__(self) -> str:
        """Return a diagnostic representation."""
        ...


class ParameterType(Protocol):
    """Protocol for Substance Designer property type handles."""

    def getId(self) -> str:
        """Return the property type identifier."""
        ...


class ParameterProperty(Protocol):
    """Protocol for node input and annotation properties."""

    def getId(self) -> str:
        """Return the property identifier."""
        ...

    def getType(self) -> ParameterType | None:
        """Return the property type."""
        ...


class ParameterNode(Protocol):
    """Protocol for nodes that expose settable parameters."""

    def getProperties(self, category: int) -> Iterable[ParameterProperty]:
        """Return properties for a category."""
        ...

    def setInputPropertyValueFromId(self, parameter_id: str, value: SettableSDValue) -> None:
        """Set an input property value by identifier."""
        ...

    def setAnnotationPropertyValueFromId(self, parameter_id: str, value: SettableSDValue) -> None:
        """Set an annotation property value by identifier."""
        ...


PropertySetter: TypeAlias = Callable[[str, SettableSDValue], None]
