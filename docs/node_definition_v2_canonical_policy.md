# Node Definition v2 Canonical Policy

## Thesis

`node_definitions` is no longer an expanded legacy JSON shape. It is the MCP authoring domain contract database.

Adapters must move to the v2 schema. Builders must not emit compatibility aliases for old adapter assumptions.

## Compatibility Decision

Do not preserve legacy compatibility.

Remove these assumptions from the adapter target:

- Top-level `nodes`.
- List-style `ports.inputs` / `ports.outputs`.
- `graph_scopes` as the primary filtering surface.
- Single-result shallow lookup by `definition_id`.
- Adapter hardcoded function contracts.
- Empty FX-Map definitions.
- Legacy `context.kind` acceptance.
- Adapter-side special handling of top-level `inputs` / `outputs`.

Keep these public concepts:

- Public `GraphRef`.
- Public `get_authoring_capabilities`, `validate_graph_change`, and `apply_graph_change`.
- `GraphKind + FunctionContract`.
- Evidence-driven validation.
- Unsupported responses instead of guessing.

## Canonical v2 Node Definition Set

Node definition set files must use this shape:

```json
{
  "schema_version": "2.0",
  "resource_kind": "node_definition_set",
  "kind": "function-library",
  "node_definitions": {
    "3d_sdf_sphere": {
      "definition_id": "sbs::function-library::3d_sdf_sphere",
      "graph_kind": "function_graph",
      "graph_type": "SDSBSFunctionGraph",
      "category": "SDF function/Primitive",
      "families": ["sdf_function_library"],
      "context_scopes": [{"id": "3d_viewer", "required": true}],
      "availability": {"default": false, "requires_context": ["3d_viewer"]},
      "ports": {
        "inputs": {
          "radius": {"type": "float", "connectable": true}
        },
        "outputs": {
          "unique_filter_output": {"type": "float", "connectable": true}
        }
      },
      "ports_evidence": {
        "status": "complete",
        "sources": {
          "inputs": "adobe_docs",
          "outputs": "static_contract"
        }
      },
      "root": {
        "selectable": true,
        "default_output": "unique_filter_output",
        "output_type": "float",
        "allowed_contracts": ["sdf_function", "host_property_function"],
        "blocked_contracts": {
          "pixel_processor": "output_type_mismatch"
        },
        "evidence": {
          "source": "live_probe",
          "status": "complete"
        }
      }
    }
  }
}
```

Important:

- `ports.inputs` and `ports.outputs` are dictionaries, not lists.
- `families` is explicit on every node. Validators must not infer SDF/generic families from `category`, `display_name`, or source filename.
- Top-level node `inputs` / `outputs` are not canonical and must not be emitted.
- Top-level `nodes` is not emitted.
- `graph_kind` / `graph_type` live on each node.
- `graph_scopes` is not used as primary filtering metadata.

## Split Registries

Function contracts and FX-Map graph metadata are separate contract artifacts:

```text
substance_designer_function_contracts.json
substance_designer_fx_map_graph.json
substance_designer_function_live_probe_results.json
substance_designer_standard_library_resource_index.json
```

Node definition set files do not duplicate those registries.

## Built-in Library Creation Metadata

Built-in `sbs::library::*` nodes must carry explicit creation metadata generated
from a standard package scan. Runtime code must not infer package filenames from
`definition_id`, `display_name`, `resource_url`, or broad slug tokens.
Package references use `path`, not `file_name`, so subdirectories under the
standard package root are preserved.

Canonical creation shape:

```json
{
  "definition_id": "sbs::library::3d_texture_sdf",
  "creation": {
    "method": "create_instance_node",
    "resource_url": "pkg:///3d_texture_sdf",
    "package": {
      "kind": "builtin_standard_library",
      "path": "3d_texture_jump_flood.sbs",
      "evidence": {"source": "package_scan", "status": "complete"}
    },
    "standard_package_candidates": [
      {
        "path": "3d_texture_jump_flood.sbs",
        "resource_url": "pkg:///3d_texture_sdf",
        "evidence": {"source": "package_scan", "status": "complete"}
      }
    ]
  }
}
```

The separate standard library resource index is keyed by `resource_url` and
records all package candidates:

```json
{
  "schema_version": "2.0",
  "resource_kind": "standard_library_resource_index",
  "resources": {
    "pkg:///3d_texture_sdf": {
      "status": "complete",
      "candidates": []
    }
  }
}
```

If multiple scanned package resources share the same `resource_url`, the index
entry must be `status: "ambiguous"`. Adapter/plugin code must use explicit
`creation.package` / `standard_package_candidates` supplied by node definitions
and must treat missing package evidence as unsupported for built-in automatic
loading.

Function-library nodes follow the same rule, but their `resource_url` often
includes a standard package folder path and dependency query. The folder path is
generated from the `.sbs` group hierarchy, not inferred from the node slug or
docs category:

```json
{
  "definition_id": "sbs::function-library::3d_sdf_sphere",
  "creation": {
    "method": "create_instance_node",
    "status": "complete",
    "resource_url": "pkg:///3d_sdf_primitives/3d_sdf_sphere?dependency=1566899378",
    "package": {
      "kind": "builtin_standard_library",
      "path": "3d_functions.sbs",
      "evidence": {"source": "package_scan", "status": "complete"}
    }
  }
}
```

For example, `sbs::function-library::set_color` resolves to
`pkg:///materials/set_color?dependency=1566899378` from package scan evidence.
If a function-library node cannot be matched to a scanned standard package
function, its `creation.status` must be `unknown` and it must not receive a
guessed `pkg:///{slug}` URL.

When package scan input ports are available, node definition `ports.inputs` must
use the host/package input identifiers as canonical port ids. Adobe docs names
may be retained only as aliases:

```json
{
  "definition_id": "sbs::function-library::set_color",
  "ports": {
    "inputs": {
      "scene": {
        "type": "float",
        "display_name": "SDF scene",
        "aliases": ["sdf_scene"]
      },
      "basecolor": {
        "type": "float3",
        "display_name": "Base color",
        "aliases": ["base_color"]
      }
    }
  },
  "ports_evidence": {
    "status": "complete",
    "sources": {
      "inputs": "package_scan",
      "outputs": "static_contract"
    }
  }
}
```

Validators may accept aliases as user-facing conveniences only if they rewrite
them to canonical host port ids before apply. A GraphChange that validates with
docs-derived aliases but applies those aliases directly is invalid contract
behavior.

## Contract Registry Shape

```json
{
  "schema_version": "2.0",
  "resource_kind": "function_contract_registry",
  "function_contracts": {
    "sbs::library::shape_splatter_v2.pattern_sdf_function": {
      "owner_definition_id": "sbs::library::shape_splatter_v2",
      "property_id": "pattern_sdf_function",
      "builtins": {
        "shape.id": {"type": "int", "readable": true},
        "shape.amount": {"type": "int", "readable": true}
      }
    }
  },
  "host_property_contract_candidates": {}
}
```

Contract keys remain stable identifiers, but each entry must also carry structured
`owner_definition_id` and `property_id`. `builtins` is an id-keyed dictionary, not
a list. State-bound contracts such as `value_processor` must also carry
`type_binding` and a live-probed `type_matrix` or partial evidence that states
what still needs probing.

Unregistered candidates must be actionable:

```json
{
  "id": "sbs::library::mask_to_paths_2.order_func",
  "output": {"type": "float"},
  "missing": ["builtins", "allowed_context_scopes", "output_contract_evidence"],
  "reason": "Function-like host property found but contract semantics are not confirmed."
}
```

## FX-Map Graph Shape

```json
{
  "schema_version": "2.0",
  "resource_kind": "fx_map_graph_definition",
  "fx_map_graph": {
    "graph_kind": "fx_map_graph",
    "graph_type": "SDSBSFxMapGraph",
    "nodes": {}
  }
}
```

FX-Map node definitions use the same `ports.inputs` / `ports.outputs` dict convention.

## Builder Requirements

Builders must:

- Emit v2 schema only.
- Add `schema_version: "2.0"`.
- Add `resource_kind` and `kind` to node definition sets.
- Move node `inputs` / `outputs` into `ports.inputs` / `ports.outputs`.
- Add `graph_kind: "function_graph"` and `graph_type: "SDSBSFunctionGraph"` to function nodes.
- Add `families: ["generic_function"]` or `families: ["sdf_function_library"]` to every function node.
- Emit `root.selectable`, not `root.can_be_root`.
- Keep generic Function Graph root selectability separate from host property contract compatibility.
- Emit `root.allowed_contracts`, `root.blocked_contracts`, and `root.evidence`.
- Do not collapse state-bound contracts such as `value_processor` into node-level allowed/blocked lists.
- Emit complete SDF `ports_evidence` with split sources when validation is possible:
  - `inputs: "adobe_docs"`
  - `outputs: "static_contract"`
- Emit `unknown` only when validation must stop.
- Split `function_contracts`, `fx_map_graph`, and `host_property_contract_candidates` out of node definition set files.
- For built-in `sbs::library::*` nodes, emit `creation.resource_url`,
  `creation.package`, and `creation.standard_package_candidates` from package
  scan evidence.
- For `sbs::function-library::*` nodes, emit folder-aware
  `creation.resource_url` from `.sbs` function group hierarchy when package scan
  evidence is complete.
- Prefer package scan input port identifiers over Adobe docs slugs. Preserve
  docs-derived input ids only in `aliases`.
- Emit `substance_designer_standard_library_resource_index.json` so runtime
  code can report complete / ambiguous / missing package evidence without slug
  guessing.

## Tests

Schema tests must verify:

- v2 files have `schema_version == "2.0"`.
- Node definition set files have `resource_kind == "node_definition_set"`.
- Node definition set files do not have top-level `nodes`.
- Node definitions do not have top-level `inputs` or `outputs`.
- Node `ports.inputs` and `ports.outputs` are dictionaries.
- Every node has `definition_id`, `graph_kind`, `graph_type`, `ports`, `ports_evidence`, and `root`.
- Every node has non-empty `families`.
- Every node root has `selectable`, `allowed_contracts`, `blocked_contracts`, and `evidence`.
- Every `root.default_output` exists in `ports.outputs` when `root.selectable` is true.
- Every `root.output_type` matches that output port type when `root.selectable` is true.
- `const_string` / `get_string` are selectable in generic Function Graph output when live probe evidence confirms it.
- Function contracts refer to known graph kinds.
- Function contracts include `owner_definition_id`, `property_id`, and dict-style `builtins`.
- State-bound function contracts include `type_binding` and `type_matrix`.
- Every `allowed_node_families` value appears in node `families`.
- FX-Map graph nodes have complete ports evidence.
- Old nodes-only fixtures are rejected by the future adapter store.
- Every built-in library node has `creation.method == "create_instance_node"`,
  `creation.resource_url`, and package scan evidence.
- `sbs::library::3d_texture_sdf` resolves to `3d_texture_jump_flood.sbs` from
  package scan metadata.
- `sbs::function-library::3d_sdf_sphere` resolves to
  `pkg:///3d_sdf_primitives/3d_sdf_sphere?dependency=1566899378` from package
  scan metadata.
- `sbs::function-library::set_color` resolves to
  `pkg:///materials/set_color?dependency=1566899378` from package scan metadata.
- `sbs::function-library::set_color` input ports are canonicalized to
  `scene` and `basecolor`, with docs aliases `sdf_scene` and `base_color`.
- The standard library resource index marks duplicate `resource_url` candidates
  as `ambiguous`.

## First Proof Point

The first adapter proof point should be:

```python
store = load_node_definition_store()
contract = store.function_contract(
    "sbs::library::shape_splatter_v2",
    "pattern_sdf_function",
)
capabilities = authoring_capabilities(graph_ref=...)
```

Expected:

- `graph_kind == "function_graph"`.
- `contract.kind == "sdf_function"`.
- SDF nodes are allowed.
- `const_float1` is allowed.
- `sbs::compositing::uniform` is rejected.
- `const_float1` output satisfies `float`.
- Unknown port evidence fails.

## Falsifiers

This policy should be revisited if:

- v2 schema alone cannot represent package graph, function graph, and FX-Map graph availability.
- Host property `FunctionContract` cannot be resolved without runtime state in common cases.
- FX-Map graph metadata cannot validate safely without live host evidence.
- Adobe docs / SDK dump evidence proves too unstable for a maintained contract database.
