# ADR-0004: MCP Tool and Graph Schema Strategy

## Status

Superseded by ADR-0007 and the MCP tool surface cleanup.

## Context

Substance Designer is graph-centric. MCP tools need to expose enough structure for agents to inspect graphs, reason about nodes, and eventually perform edits. Graph and node-oriented tool granularity is defined by this adapter's skills, command facade, schema normalization, and host plugin command surface.

## Decision

The initial read-only MCP tool scope includes:

- `get_scene`
- `list_graphs`
- `get_graph`
- node detail and parameter inspection

Graph responses should support both raw and normalized forms. Raw data is useful for debugging host API behavior. Normalized data is the stable MCP-facing contract and should use adapter-owned field names rather than leaking Substance Designer internals everywhere.

Mutation tools are allowed to execute directly once implemented. They should still validate inputs and return structured errors, but they do not require a mandatory dry-run phase or confirmation token by default.

The first mutation tool set covers package creation/saving, graph creation/opening/deletion, node creation/movement/duplication/deletion, explicit connections, disconnection, parameter setting, and graph output size changes.

For multi-step edits that depend on an existing source node, replace output
bindings, or need structural lineage requirements, direct mutation primitives
must be paired with stronger inspection and validation. ADR-0006 defines this
layered graph-editing model: inspect the graph as a node network first, use
typed mutation primitives for direct edits, and add targeted lineage validation
only when the workflow requires a selected source to reach a later output.

Nested graph authoring, such as Pixel Processor `perpixel` function graphs, is
handled separately by ADR-0005. ADR-0004 covers outer Substance graph inspection
and mutation primitives; ADR-0005 defines the declarative state model for
property-backed internal graphs.

## Consequences

Supporting both raw and normalized graph data keeps early development practical while preserving a stable contract for agents. The normalized schema becomes the long-term surface for MCP clients.

Direct mutation keeps workflows efficient, but it raises the importance of clear tool names, parameter validation, and tests around graph-editing behavior.

ADR-0006 keeps direct mutation as the right tool for simple edits, but requires
better graph observability and optional lineage validation for source-sensitive
workflows.
