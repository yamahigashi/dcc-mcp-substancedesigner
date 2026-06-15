# ADR-0010: MCP Tool Surface Size Budget

## Status

Accepted. Amended by ADR-0018 and ADR-0019 for capped initial model-facing
exposure.

## Context

MCP tools are model-controlled operations. The model chooses them from the
currently visible `tools/list` surface by interpreting names, descriptions, and
schemas. Large tool manifests consume context, increase latency, and make tool
selection less reliable, especially when tools overlap in name or purpose.

The adapter previously separated tools into `default` and `advanced` policy
groups. That still made the public surface too close to the implementation
catalog and too large for Codex-style tool exposure. ADR-0008 keeps standard MCP
`tools/list` as the authoritative callable surface, while progressive discovery
remains a secondary catalog layer. The public callable surface should therefore
be the workflow surface clients should actually use, not a dump of internal
bridge commands.

## Decision

The adapter-owned workflow tool catalog is governed by these budgets:

1. The adapter `public` group must stay at or below 14 callable tools.
   Public tools must represent complete user workflows across a session: scene
   inspection, reference lookup, graph reads, node details, preview,
   context-specific authoring capabilities, declarative graph-change
   validation/apply, diagnostics, and explicit trusted Python execution. The
   capped initial model-facing subset is narrower; see ADR-0018.
2. Tools that exceed this budget need an explicit design reason and should
   first be considered for consolidation into an existing user-goal tool, a
   `detail_level` or mode parameter, structured diagnostics on an existing read
   model, or a non-callable skill/reference document.
3. Internal API wrappers, one-field read helpers, derived diagnostic views, and
   recipe-specific operations should not become public tools. They should be
   kept as internal command-facade/plugin operations or folded into workflow
   tools.
4. The adapter should prefer structured outputs with `outputSchema` where
   practical, clear input schemas, and MCP tool annotations that state
   read-only and idempotency behavior. These improve tool selection without
   hiding specialized tools behind client-side confirmation policy.
5. For capped initial model-facing exposure, ADR-0018 and ADR-0019 supersede the
   older first-page guidance in this ADR. Initial exposure should prefer
   read/discovery/preview/debug and authoring-plan tools; concrete capability,
   validation, mutation, file, and lifecycle tools are later-phase tools.

## Consequences

Adding a new public tool now requires removing or consolidating another public
tool unless the group remains within the 14-tool budget.

The preferred consolidation direction is:

- fold lightweight listing helpers into `get_graph` or another stable read
  model;
- fold validation/apply chains into task-complete workflow tools such as
  `validate_graph_change` and `apply_graph_change`;
- keep authoring reference lookup in `get_reference` so `reference_uris` are
  actionable without reading local implementation files;
- keep exact low-level mutations internal unless they are the only practical
  operation for a common workflow;
- keep arbitrary host execution explicit and risk-labeled rather than using it
  as a substitute for typed tools.

This ADR does not require every host bridge command to be callable as an MCP
tool. The callable MCP surface is an agent-facing product surface, not a mirror
of the plugin command API.
