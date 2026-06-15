"""Semantic enrichment helpers for Substance Designer graph inspection."""

from __future__ import annotations

from dcc_mcp_substancedesigner.json_types import JsonMap, JsonValue

OUTPUT_USAGE_BY_IDENTIFIER = {
    "basecolor": "baseColor",
    "base_color": "baseColor",
    "diffuse": "baseColor",
    "normal": "normal",
    "roughness": "roughness",
    "metallic": "metallic",
    "metalness": "metallic",
    "opacity": "opacity",
    "alpha": "opacity",
    "height": "height",
    "ambientocclusion": "ambientOcclusion",
    "ambient_occlusion": "ambientOcclusion",
    "ao": "ambientOcclusion",
    "emissive": "emissive",
}

PARAMETER_ROLES_BY_FILTER = {
    "uniform": {
        "outputcolor": "color",
        "colorswitch": "color_mode",
    },
    "blend": {
        "blendingmode": "blend_mode",
        "opacity": "opacity",
        "input1": "background",
        "input2": "foreground",
        "source": "background",
        "destination": "foreground",
    },
    "levels": {
        "levelinlow": "input_low",
        "levelinhigh": "input_high",
        "leveloutlow": "output_low",
        "levelouthigh": "output_high",
        "gamma": "gamma",
    },
    "blur": {
        "intensity": "intensity",
        "quality": "quality",
    },
    "blur_hq": {
        "intensity": "intensity",
        "quality": "quality",
    },
}


def enrich_node_detail(detail: JsonMap) -> JsonMap:
    """Add adapter-owned semantic fields to a normalized node detail."""
    annotations = _annotation_map(detail.get("annotations"))
    definition = _text(detail.get("definition")) or "unknown"
    node_id = _text(detail.get("node_id")) or _text(detail.get("identifier"))
    kind = node_kind(definition)
    identifier = _first_text(
        detail.get("identifier"),
        annotations.get("identifier"),
        annotations.get("identifierUrl"),
        node_id,
    )
    label = _first_text(detail.get("label"), annotations.get("label"), annotations.get("labelUrl"))
    usage, usage_source, usage_diagnostics = resolve_usage(
        _first_usage(detail.get("usage"), annotations.get("usage"), annotations.get("usages")),
        identifier,
        label,
    )
    diagnostics = _dedupe_diagnostics([*_list(detail.get("diagnostics")), *usage_diagnostics])
    enriched = {
        **detail,
        "kind": kind,
        "filter_type": filter_type(definition),
        "label": label,
        "identifier": identifier,
        "comment": _first_text(detail.get("comment"), annotations.get("comment"), annotations.get("description")),
        "parameters": normalize_parameters(detail.get("inputs"), filter_type(definition)),
        "exposed_inputs": normalize_exposed_inputs(detail.get("inputs")),
        "instance": normalize_instance_reference(detail),
        "output_binding": normalize_output_binding(node_id, identifier, label, usage, usage_source)
        if kind == "graph_output"
        else None,
        "diagnostics": diagnostics,
    }
    return enriched


def node_kind(definition: str | None) -> str:
    """Classify a Substance node definition into a stable adapter kind."""
    definition = definition or "unknown"
    if definition == "sbs::compositing::output":
        return "graph_output"
    if definition == "sbs::compositing::input":
        return "graph_input"
    if definition == "sbs::compositing::pixelprocessor":
        return "pixel_processor"
    if definition.startswith("sbs::compositing::"):
        return "filter"
    if definition.startswith("sbs::function::"):
        return "function"
    if definition.startswith("pkg://") or "?dependency=" in definition or definition == "unknown":
        return "instance"
    return "unknown"


def filter_type(definition: str | None) -> str | None:
    """Return the short filter type for built-in compositing nodes."""
    if not definition or not definition.startswith("sbs::compositing::"):
        return None
    return definition.rsplit("::", 1)[-1] or None


def normalize_parameters(inputs: JsonValue, node_filter_type: str | None = None) -> list[JsonMap]:
    """Convert valued input ports into semantic parameter entries."""
    parameters = []
    for item in _list(inputs):
        if "value" not in item:
            continue
        identifier = _text(item.get("id") or item.get("identifier"))
        if not identifier:
            continue
        value = item.get("value")
        parameters.append(
            {
                "identifier": identifier,
                "label": _text(item.get("label")),
                "value": value,
                "display_value": display_value(value),
                "value_type": infer_value_type(value),
                "semantic_role": semantic_parameter_role(node_filter_type, identifier),
                "raw": {"port": item},
                "diagnostics": [],
            }
        )
    return parameters


def semantic_parameter_role(node_filter_type: str | None, identifier: str) -> str | None:
    """Return a stable semantic role for known filter parameters."""
    if not node_filter_type:
        return None
    role_map = PARAMETER_ROLES_BY_FILTER.get(node_filter_type.lower())
    if not role_map:
        return None
    return role_map.get(identifier.lower())


def normalize_exposed_inputs(inputs: JsonValue) -> list[JsonMap]:
    """Return exposed input mappings when host data provides exposure metadata."""
    exposed = []
    for item in _list(inputs):
        exposure = item.get("exposed") or item.get("exposure") or item.get("exposed_as")
        if not exposure:
            continue
        exposed.append(
            {
                "input": _text(item.get("id") or item.get("identifier")),
                "exposed_as": exposure,
                "raw": item,
            }
        )
    return exposed


def normalize_instance_reference(detail: JsonMap) -> JsonMap | None:
    """Return package/graph reference metadata for instance-like nodes."""
    definition = _text(detail.get("definition"))
    raw_instance = detail.get("instance")
    if node_kind(definition) != "instance" and not isinstance(raw_instance, dict):
        return None
    raw_ref: JsonMap = raw_instance if isinstance(raw_instance, dict) else {}
    return {
        "definition": definition,
        "package": raw_ref.get("package"),
        "graph": raw_ref.get("graph"),
        "resource_url": raw_ref.get("resource_url") or raw_ref.get("resourceUrl"),
        "pattern_input": raw_ref.get("pattern_input"),
        "raw": raw_ref or {"definition": definition},
    }


def normalize_output_binding(
    node_id: str | None,
    identifier: str | None,
    label: str | None,
    usage: str | None,
    usage_source: str | None,
) -> JsonMap:
    """Build the node-local graph output binding semantic object."""
    return {
        "node_id": node_id,
        "identifier": identifier or node_id,
        "label": label,
        "usage": usage,
        "usage_source": usage_source,
    }


def resolve_usage(
    explicit_usage: str | None,
    identifier: str | None,
    label: str | None,
) -> tuple[str | None, str | None, list[JsonMap]]:
    """Resolve material output usage and record fallback inference."""
    if explicit_usage:
        return explicit_usage, "explicit", []
    key = _usage_key(identifier) or _usage_key(label)
    if key and key in OUTPUT_USAGE_BY_IDENTIFIER:
        usage = OUTPUT_USAGE_BY_IDENTIFIER[key]
        return (
            usage,
            "inferred_from_identifier",
            [
                {
                    "severity": "info",
                    "code": "usage_inferred_from_identifier",
                    "message": f"Output usage was inferred as '{usage}'.",
                    "source": "semantic_graph",
                }
            ],
        )
    return None, None, []


def infer_value_type(value: JsonValue) -> str:
    """Infer an MCP-friendly value type for serialized SD values."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        keys = set(value)
        if {"r", "g", "b"}.issubset(keys):
            return "color"
        if {"x", "y"}.issubset(keys):
            if "w" in keys:
                return "float4"
            if "z" in keys:
                return "float3"
            return "float2"
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def display_value(value: JsonValue) -> JsonValue:
    """Return a compact human-readable value without losing the raw value."""
    if isinstance(value, dict) and {"r", "g", "b"}.issubset(value):
        alpha = value.get("a", 1)
        return [value.get("r"), value.get("g"), value.get("b"), alpha]
    if isinstance(value, dict) and {"x", "y"}.issubset(value):
        result = [value.get("x"), value.get("y")]
        if "z" in value:
            result.append(value.get("z"))
        if "w" in value:
            result.append(value.get("w"))
        return result
    return value


def _annotation_map(annotations: JsonValue) -> JsonMap:
    return {str(item.get("id")): item.get("value") for item in _list(annotations) if item.get("id")}


def _dedupe_diagnostics(diagnostics: list[JsonMap]) -> list[JsonMap]:
    result = []
    seen = set()
    for item in diagnostics:
        key = (item.get("severity"), item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _usage_key(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "").replace("-", "_")


def _first_usage(*values: JsonValue) -> str | None:
    for value in values:
        usage = _usage_name(value)
        if usage:
            return usage
    return None


def _usage_name(value: JsonValue) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        return _first_text(value.get("name"), value.get("usage"), value.get("id"))
    if isinstance(value, list):
        for item in value:
            usage = _usage_name(item)
            if usage:
                return usage
    return None


def _first_text(*values: JsonValue) -> str | None:
    for value in values:
        text = _text(value)
        if text:
            return text
    return None


def _text(value: JsonValue) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _list(value: JsonValue) -> list[JsonMap]:
    if not isinstance(value, list):
        return []
    result: list[JsonMap] = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
    return result
