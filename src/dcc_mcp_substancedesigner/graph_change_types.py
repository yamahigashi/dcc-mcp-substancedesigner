"""Types for public GraphChange JSON payloads.

These are adapter-side JSON contract types. Host SDK values such as
SDValueArray<SDTypeUsage> belong in the plugin package, not here.
"""

from __future__ import annotations

from typing import Literal, TypeAlias, TypedDict

from dcc_mcp_substancedesigner.json_types import JsonMap, JsonValue


class GraphChangeParameterObject(TypedDict, total=False):
    """Object form accepted by GraphChange parameter values."""

    value: JsonValue
    type: str
    value_type: str


class OutputUsageObject(TypedDict, total=False):
    """Public output usage metadata object."""

    name: str
    usage: str
    id: str
    components: str
    component: str
    color_space: str
    colorSpace: str


class LoweredGraphChangeParameter(TypedDict, total=False):
    """Host-facing parameter payload sent to the bridge set_parameter command."""

    value: JsonValue
    type: str
    value_type: Literal["string", "usage_array"]


class GraphChangeConnectionEndpoint(TypedDict, total=False):
    """Canonical endpoint object for GraphChange connections."""

    node: str
    id: str
    input: str
    output: str
    port: str
    from_output: str
    to_input: str


GraphChangeNode: TypeAlias = JsonMap
GraphChangeParameterValue: TypeAlias = JsonValue | GraphChangeParameterObject
GraphChangeLoweredParameterValue: TypeAlias = GraphChangeParameterValue | LoweredGraphChangeParameter
GraphChangeParameterItems: TypeAlias = list[tuple[str, GraphChangeLoweredParameterValue]]

# Public output usage is authored as a string, optionally wrapped in a parameter
# object. The host-facing lowered payload uses value_type="usage_array".
OutputUsageParameterValue: TypeAlias = str | OutputUsageObject | GraphChangeParameterObject

GraphChangeConnection = TypedDict(
    "GraphChangeConnection",
    {
        "from": str | GraphChangeConnectionEndpoint,
        "to": str | GraphChangeConnectionEndpoint,
        "input": str,
        "output": str,
        "from_output": str,
        "to_input": str,
    },
    total=False,
)
