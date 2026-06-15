# ADR-0018: Initial MCP Tool Exposure

## Status

Accepted. Amended by ADR-0019: the capped initial surface must expose
`get_authoring_plan` before concrete authoring capabilities.

## Context

Some MCP clients expose only a small subset of a server's callable tools to the
model after tool discovery. In observed Codex-style usage, the exposed
`mcp__substance_designer` surface was capped at 10 tools and selected by the
client/LLM layer, not by the adapter's `tools/list` order alone.

The first interaction with a Substance Designer graph is normally not a
mutation. A useful agent first checks the connected scene, reads the graph and
node details, asks for context-specific authoring capabilities, reads returned
authoring references, and previews results. File operations and graph mutations
are later-phase actions.

ADR-0010 set a 14-tool public budget and treated validation/mutation as part of
the first visible authoring path. That is too broad for clients that cap initial
tool exposure.

## Decision

The initial model-facing Substance Designer MCP exposure should be a compact
read/discovery/preview/debug surface:

1. `get_scene`
2. `get_graph`
3. `get_node`
4. `get_authoring_plan`
5. `get_reference`
6. `get_preview`
7. `diagnostic`
8. `execute_python`

These tools cover connection checks, graph and node evidence, authoring plan
selection, reference lookup, visual verification, diagnostics, and an explicit
trusted escape hatch.

The following tools should not compete for initial exposure:

- `validate_graph_change`
- `apply_graph_change`
- `replace_graph_state`
- `get_authoring_capabilities`
- `export_output`
- `save_package`
- `refresh_plugin`

Concrete capability, validation, and mutation tools remain part of the adapter
workflow contract, but they are later-phase tools. File and lifecycle tools are
also later-phase tools. They should be exposed through an on-demand mechanism, a
secondary/debug surface, or direct backend/developer operation rather than
displacing evidence, planning, and discovery tools in the initial model-visible
set.

`execute_python` remains intentionally exposed in the initial set. It is not the
preferred authoring interface, but it is the required escape hatch for host API
inspection, recovery, and gaps in typed tooling.

## Consequences

Initial exposure is optimized for safe orientation and evidence gathering, not
for immediate mutation.

ADR-0019 tightens this consequence: `get_authoring_plan` owns bounded authoring
unit selection, required evidence, and preview checkpoints. Concrete capability
discovery must not be the initial authoring entrypoint.

Tool descriptions and aliases should bias client-side selection toward the
eight initial tools when the client caps visible tools.

Typed mutation tools still need clear `next_tools`, validation contracts, and
references, but they should not force `get_reference`, `get_node`, or diagnostic
tools out of the initial callable set.

ADR-0010's size budget remains useful as an upper bound for the adapter-owned
workflow catalog, but its recommendation to put validation and mutation tools on
the first visible page is superseded by this ADR.
