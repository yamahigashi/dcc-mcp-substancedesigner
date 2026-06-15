"""Shared input type aliases for adapter commands and bundled skills."""

from __future__ import annotations

from typing import Any, TypeAlias

from dcc_mcp_substancedesigner.json_types import JsonValue

JsonSequenceInput: TypeAlias = list[JsonValue] | tuple[JsonValue, ...]
NodeIdInput: TypeAlias = str | int
OptionalNodeIdInput: TypeAlias = NodeIdInput | None
NodeIdListInput: TypeAlias = list[NodeIdInput]
OptionalNodeIdListInput: TypeAlias = NodeIdListInput | None
GraphIdentifierInput: TypeAlias = str
OptionalGraphIdentifierInput: TypeAlias = GraphIdentifierInput | None
PropertyIdInput: TypeAlias = str
OptionalPropertyIdInput: TypeAlias = PropertyIdInput | None
PythonCodeInput: TypeAlias = str
OptionalPythonCodeInput: TypeAlias = PythonCodeInput | None
PositionInput: TypeAlias = JsonSequenceInput | dict[str, JsonValue]
OptionalPositionInput: TypeAlias = PositionInput | None
ColorInput: TypeAlias = JsonSequenceInput | dict[str, JsonValue]
OptionalColorInput: TypeAlias = ColorInput | None
ReferenceInput: TypeAlias = str | int | dict[str, JsonValue]
OptionalReferenceInput: TypeAlias = ReferenceInput | None
ResolutionDimensionInput: TypeAlias = str | int
OptionalResolutionDimensionInput: TypeAlias = ResolutionDimensionInput | None
ResolutionInput: TypeAlias = ResolutionDimensionInput | dict[str, JsonValue]
OptionalResolutionInput: TypeAlias = ResolutionInput | None
ControlTargetInput: TypeAlias = dict[str, JsonValue]
OptionalControlTargetInput: TypeAlias = ControlTargetInput | None
ControlUpdatesInput: TypeAlias = dict[str, JsonValue] | list[dict[str, JsonValue]]
OptionalControlUpdatesInput: TypeAlias = ControlUpdatesInput | None
SkillObjectInput: TypeAlias = dict[str, Any]
OptionalSkillObjectInput: TypeAlias = SkillObjectInput | None
SkillObjectListInput: TypeAlias = list[SkillObjectInput]
OptionalSkillObjectListInput: TypeAlias = SkillObjectListInput | None
NestedGraphStateInput: TypeAlias = SkillObjectInput
OptionalNestedGraphStateInput: TypeAlias = NestedGraphStateInput | None
