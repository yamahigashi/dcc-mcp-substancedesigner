# ADR-0017: Parameter Enum Contract Evidence

## Status

Accepted

## Context

`node reference` resources are the authoring contract callers read before
creating or editing Substance Designer nodes. They are generated from packaged
static JSON catalogs, not from the live host at request time.

Live testing against Substance Designer 16.0.3 showed that this static contract
is incomplete for parameter authoring:

- `validate_graph_change` can accept parameter ids that are not settable on the
  target node definition, leaving `Property not found` failures for apply time;
- enum parameters can be exposed as raw integers without the valid option list;
- UI labels, parameter ids, and enum integer values can diverge;
- static node descriptions can mention concepts without giving a machine-readable
  set of values that callers can safely pass.

The specific failure was Shape Splatter v2: callers guessed parameters such as
`distribution` and `pattern_type`, and guessed `shape_type: 5`. The host contract
instead exposed parameter ids such as `position_distribution_mode` and enum
values such as `SDF Function = 1`.

This is not a Shape Splatter-specific problem. It is a contract evidence problem:
GraphChange validation and authoring references need the same machine-readable
parameter and enum facts.

## Decision

Parameter enum data belongs to the node parameter contract.

Each node definition parameter may include:

```json
{
  "id": "shape_type",
  "display_name": "Shape type",
  "type": ["int"],
  "host_type": "sbs::compositing::shape_type",
  "default": 2,
  "enum": {
    "value_type": "int",
    "default_value": 2,
    "default_label": "Cube",
    "options": [
      {"value": 1, "id": "sdf_function", "label": "SDF Function"},
      {"value": 2, "id": "cube", "label": "Cube"}
    ],
    "evidence": {
      "source": "live_probe",
      "sd_version": "16.0.3",
      "method": "SDProperty.getType/getEnumerators/getDefaultValue",
      "confidence": "high"
    }
  }
}
```

The node reference remains the primary location for complete static authoring
contracts. `get_authoring_capabilities` should point to or summarize those
contracts in the current graph context. `get_node` should add live current values
and may include live enum observations. `validate_graph_change` should use
high-confidence parameter contracts to fail before mutation and return focused
repair candidates.

Enum data must not be maintained as ad hoc code tables. It is generated or
merged into packaged node definition JSON from versioned evidence.

## Evidence Source

The preferred evidence source is a live probe run against a known Substance
Designer version. Probe output is a library node live probe results document.
Enum data is part of parameter results, not a standalone evidence type:

```json
{
  "schema_version": "1.0",
  "resource_kind": "library_node_live_probe_results",
  "sd_version": "16.0.3",
  "catalogs": ["library.json"],
  "nodes": {
    "sbs::library::shape_splatter_v2": {
      "catalog": "library.json",
      "slug": "shape_splatter_v2",
      "create": {
        "resource_url": "pkg:///shape_splatter_v2",
        "package": {
          "kind": "builtin_standard_library",
          "file_name": "shape_splatter_v2.sbs"
        }
      },
      "parameters": {
        "shape_type": {
          "direction": "input",
          "label": "Shape type",
          "type": "sbs::compositing::shape_type",
          "value": 2,
          "enum": {
            "value_type": "int",
            "default_value": 2,
            "default_label": "Cube",
            "options": [
              {"value": 1, "id": "sdf_function", "label": "SDF Function"}
            ]
          }
        }
      },
      "ports": {}
    }
  },
  "summary": {
    "target_total": 1,
    "success": 1,
    "failure": 0,
    "parameter_total": 1,
    "enum_parameter_total": 1
  }
}
```

The node key is the Substance Designer `definition_id`. A future probe may also
emit slug keys, but merge tooling must resolve all updates through the canonical
definition id before modifying packaged catalogs.

The repository provides scripts for this pipeline:

- `tools/probe_node_live_result.py` connects to the live plugin bridge,
  creates a temporary node, inspects host properties, ports, and enum
  enumerators, deletes the temporary node, and provides the raw live observation
  used by batch probe tooling.
- `tools/probe_library_node_live_results.py` scans packaged node definition catalogs,
  probes each creatable node through the live bridge, and writes a
  `library_node_live_probe_results` JSON file to the caller-provided `--output` path.
- `tools/merge_library_node_live_results.py` validates library node live probe results and
  merges only `parameters[].enum` into packaged node definition catalogs.

## Merge Rules

- Merge enum contracts from live probe results into `parameters[].enum`, not into a standalone registry
  only.
- Preserve existing description, display name, type, ports, and creation data.
- Do not overwrite the parameter `default` field unless a separate catalog
  regeneration step intentionally changes it.
- Store enum options directly under `parameters[].enum`; do not add a separate
  per-parameter evidence wrapper in the live probe output.
- Detect duplicate enum values, duplicate enum ids, missing labels, and unknown
  target parameters before writing.
- If static default and live enum default disagree, record diagnostics rather
  than silently rewriting unrelated fields.

## Consequences

- Authoring references become suitable as machine-readable operation contracts,
  not only discovery text.
- Callers can discover valid enum values before deciding input syntax.
- Validation can reject unknown parameters and enum values before host mutation.
- Version differences are explicit evidence, not hidden code behavior.
- Any later support for enum label or symbolic-id input has a stable contract to
  resolve against.
