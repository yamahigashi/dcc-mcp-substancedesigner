# ADR-0019: Get Authoring Plan Before Capabilities

## Status

Accepted

## Context

ADR-0018 moved the capped initial model-facing tool surface away from mutation
and file operations. The intended first phase was orientation: inspect scene and
graph state, read node details, read references, preview renderable state, and
only then move to validation and mutation.

Observed Codex-style usage still drifted into mutation-first work. The concrete
failure was a visual Substance Designer task where SDF, FX-Map, composition, and
output wiring were batched before previews were used as feedback. The user then
had to point out that `get_preview` and workflow guidance had already been
available.

This was not primarily a missing-tool problem. The current tools expose useful
facts, but they do not own the authoring protocol.

## Cause

The capped initial surface still looks like a workbench rather than a planning
protocol.

- `get_authoring_capabilities` returns `allowed_definitions`, node entries,
  `apply_supported_changes`, `apply_tool`, and mutation `next_tools`. Although
  read-only, it functions as a mutation funnel.
- `get_node` exposes concrete editable property graph refs and apply support,
  but does not give preview checkpoints equal or greater weight.
- The SDF workflow reference uses a linear `recommended_sequence` that places
  `get_preview` after `validate_graph_change` and `apply_graph_change`. This
  encourages "build, then inspect" instead of visual iteration.
- `diagnostic` still names validation and mutation tools as critical workflow
  tools, which weakens ADR-0018's later-phase distinction.
- `next_tools`, skills, and references are advisory metadata in Codex-style
  clients. The runtime does not schedule or enforce them. Treating stronger
  metadata as a gate repeats the ADR-0018 mistake.

## Result

Agents can satisfy syntactic and graph-authoring constraints while failing the
actual DCC task.

- `validate_graph_change` success is mistaken for visual progress.
- Renderable nodes are edited without immediate preview.
- SDF and FX-Map requirements degrade into "node exists" instead of "visible
  contribution is readable in previews and final outputs."
- Knowledge from MCP facts, inferred role, and visual judgement gets mixed in
  responses because no explicit evidence phase separates them.
- Initial exposure excludes mutation tools, but discovery responses still point
  directly at mutation before a production plan exists.

## Decision

Initial model-facing tools must establish an authoring protocol before they
expose authoring capability as an execution path.

Add `get_authoring_plan` as the planning tool for capped initial exposure.
`get_authoring_capabilities` remains useful, but it is not the correct first
authoring tool: its job is to answer "what can this concrete graph ref do?",
not "what should the agent do next?"

The adapter should distinguish three surfaces:

1. **Session protocol surface**: current state, evidence status, workflow
   references to read, preview targets to inspect, and the next authoring unit.
   This is owned by `get_authoring_plan`.
2. **Capability surface**: definitions, contracts, supported GraphChange shapes,
   and validation inputs for a specific unit. This is owned by
   `get_authoring_capabilities`.
3. **Execution surface**: validation, mutation, replacement, file, and lifecycle
   tools.

For capped initial exposure, `get_authoring_plan` should replace
`get_authoring_capabilities`. Capability details remain callable later, but they
must not be the initial authoring entrypoint.

## Implementation Plan

1. Add `get_authoring_plan`.
   - Make it read-only, idempotent, and part of the initial model-facing subset.
   - Inputs: `graph_ref`, optional `intent`, optional `context`, and optional
     `include_raw`.
   - Output: `phase`, `required_evidence`, `workflow_refs`, `preview_targets`,
     `visual_units`, `next_unit`, `mutation_unlocked`, and non-mutating
     `next_tools`.
   - For visual package-graph intents such as `sdf`, return
     `mutation_unlocked: false` and do not return validation or mutation tools.

2. Stop making capability discovery a mutation funnel.
   - Remove `get_authoring_capabilities` from the capped initial subset.
   - Keep `get_authoring_capabilities` in the public catalog for later-phase,
     concrete graph refs.
   - Return validation/mutation `next_tools` only from unit-scoped capability or
     validation responses, not from package-level planning.
   - Rename any "critical workflow tools" diagnostic grouping that includes
     mutation to "full workflow tools" or split it into `orientation_tools`,
     `planning_tools`, and `later_phase_tools`.

3. Make visual iteration first-class.
   - Replace SDF workflow `recommended_sequence` with `visual_iteration_units`.
   - Each unit must name its authoring surface, preview targets, pass condition,
     and the rule that another visual unit must not be batched before preview.
   - SDF units must cover at least `sdf_function`, `shape_splatter`,
     `fx_map`, and `material_composite`.

4. Promote preview targets into read models.
   - `get_graph` and `get_node` should expose `preview_targets` for renderable
     nodes and graph surfaces, not only `next_tools`.
   - For SDF, 3D Viewer and Shape Splatter v2 references should state which
     outputs prove shape readability and production contribution.

5. Protect the protocol with tests.
   - Tool catalog initial exposure expects `get_authoring_plan`, not
     `get_authoring_capabilities`.
   - Package-graph SDF plan returns `mutation_unlocked: false`.
   - SDF workflow exposes `visual_iteration_units` and no longer makes preview a
     final step after mutation.
   - Capability responses for concrete node-property graph refs may expose
     validation next tools, but planning responses must not.
   - Diagnostic separates orientation, planning, and later-phase mutation tools.
   - `get_node` for SDF surfaces exposes preview targets beside editable graph
     refs.

## Non-Goals

- Do not rely on stronger `next_tools` metadata as the primary fix.
- Do not add low-level mutation tools to the initial surface.
- Do not make `execute_python` the normal authoring path.
- Do not require Codex Desktop or another client to enforce MCP metadata.

## Consequences

The adapter will expose less immediate "what can I create?" energy in the
initial path and more "what evidence and preview checkpoint must I satisfy?"
structure. This is intentional.

The capability layer remains necessary, but it becomes a unit-scoped detail
instead of the first object a visual task can use to begin broad mutation.

Adding one public tool is acceptable because it replaces
`get_authoring_capabilities` in the capped initial subset. It does not increase
the initial exposure size.
