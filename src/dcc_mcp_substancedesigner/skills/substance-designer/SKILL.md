---
name: substance-designer
description: Codex-first Substance Designer workflow tools for scene inspection, reference lookup, capability-driven graph authoring, declarative graph-change validation/apply, diagnostics, and trusted local Python execution.
license: MIT
compatibility: "dcc-mcp-substancedesigner 0.1+, Substance 3D Designer 16.0+, dcc-mcp-core 0.17+"
allowed-tools: Bash Read
metadata:
  dcc-mcp:
    dcc: substancedesigner
    layer: domain
    stage: workflow
    version: "1.0.0"
    tags: [substance-designer, codex, workflow, graph, node, capabilities, diagnostics]
    search-hint: "scene, graph, node, preview, reference, graph capabilities, graph kind, function contract, validate graph change, apply graph change, execute python"
    tools: tools.yaml
---

# Substance Designer

Use these workflow tools as the public MCP surface. Tool names are the logical
workflow contract. Tool responses may include namespaced callable action ids in
`next_tools.tool`; use those action ids directly when following a returned
workflow hint, and use `public_name` only as the human-readable label.

Prefer typed workflow tools before `execute_python`. Keep `execute_python` for
trusted local diagnostics, recovery, and host API gaps.

The initial visible tool set is for orientation and planning: scene, graph,
node, authoring plan, reference, preview, diagnostics, and explicit Python. Use
concrete capabilities, mutation, and file tools only after the authoring plan
identifies the next bounded unit, required evidence, and preview checkpoints.

Do not treat the first visible MCP tool list as complete. If `diagnostic`,
`get_scene`, or any startup response mentions workflow tools such as
`get_authoring_plan`, `get_authoring_capabilities`, `get_graph`, `validate_graph_change`,
`apply_graph_change`, `replace_graph_state`, `search_tools`, or
`search_skills`, discover and use those typed tools before writing host Python.
Do not conclude that a workflow is unsupported from `InvalidArgument` after a
guessed `graph.newNode(...)` definition id. Definition ids, ports, parameters,
enum integers, and package resources must come from references, capabilities,
live node evidence, or user-supplied package/XML evidence.

For graph edits:

1. Inspect with `get_graph`.
2. Ask `get_authoring_plan` for the next bounded authoring unit, required evidence, references, and preview checkpoints.
3. Read returned `reference_uris` with `get_reference`.
4. Ask `get_authoring_capabilities` for GraphKind/FunctionContract-specific nodes, builtins, output contracts, and constraints only for that concrete unit.
5. Preflight the declarative `GraphChange` with `validate_graph_change`.
6. Apply with the `apply_graph_change` action returned by validation.
7. Check the result with `get_graph` and, when visual output matters, `get_preview` before starting another visual unit.

`GraphChange` is a desired-change model. `nodes[].id` may refer to an existing
host node id or to a new logical alias, and `connections[]` may connect existing
host nodes as well as nodes declared in the same payload. Use endpoint objects:
`{"from": {"node": "...", "output": "..."}, "to": {"node": "...", "input": "..."}}`.
Function graph builtins such as `$pos` use `{"from": {"builtin": "$pos"}, ...}`.
New-node aliases are scoped to one payload; `apply_graph_change` returns compact
`created` and `created_nodes` mappings from each alias to the host node id.
Do not switch to low-level operation names for ordinary existing-node
connections or parameter updates.
Parameter edits can be written either inside `nodes[].parameters` or as
top-level `change.parameters[]` entries with `node`, `parameter`, and `value`;
the latter is the preferred compact form for existing-node parameter updates.

For Function Graph entry points, prefer `get_node` first. Its
`editable_property_graphs` entries include the ready-to-use `graph_ref`,
contract kind, output contract, and builtins even when the child graph has not
been created yet. `validate_graph_change` reports `operation_plan`; callers
do not choose low-level host modes. Successful validation is compact and omits
bulk capabilities. `apply_graph_change` reports
`apply_strategy` and `parameter_results.applied/skipped/errors`.
When opening a node property graph, callers may either pass the returned
`graph_ref` or call `get_graph` with `owner_node_id` and `property_id`; they do
not need to spell GraphRef internals such as `owner_node_id` vs. `node_id`
inside a nested object.
Ordinary `nodes`/`connections`/`output` GraphChange payloads are lowered to
patch/merge operations for nested graphs and FX-Map graphs. Unmentioned nodes,
connections, outputs, and nested graphs are preserved. Full graph rebuilds are
not part of `apply_graph_change`; use `replace_graph_state` only with a complete
state and the current `state_hash` returned by `get_graph`.
For package graphs, `apply_graph_change` can patch existing nodes, move nodes,
remove input connections, and rewire existing inputs. The adapter snapshots the
affected input, parameter, or position before mutation and restores it if a
later operation fails.

For SDF requests in Substance Designer 16.0+, do not choose nodes from name
search alone. First read
`substancedesigner://authoring/workflows/sdf-function`, then use the workflow
entry nodes: `3D Viewer.sdf_scene` for authoring/debug preview and
`Shape Splatter v2.pattern_sdf_function` for production scattering. Treat
`3d_texture_sdf` as the separate 3D texture/volume workflow, not the SDF
Function workflow. The SDF Function workflow reference is the source of truth
for this distinction. If `get_authoring_capabilities` returns
`workflow_suggestions`, read those references before drafting a graph change.

Do not treat diagnostic bridge command names or execution trace operation names
as callable MCP tools. They are implementation evidence only.
