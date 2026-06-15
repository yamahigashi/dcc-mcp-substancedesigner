# ADR-0011: Authoring Reference Resources and Node Introspection

## Status

Accepted

## Context

Substance Designer graph authoring needs two different kinds of information:

1. Discoverable static node definitions and authoring contracts that agents can
   read before choosing tools.
2. Live host evidence for cases where package resources, port ids, or parameter
   roles are uncertain in the connected Substance Designer session.

These should not be collapsed into one tool family. Large MCP tool surfaces make
tool choice less reliable, while hidden or template-only references can make
models assume important nodes do not exist. Static node definitions also should
not be overwritten from one live host observation because runtime data can vary
by Substance Designer version, loaded packages, and environment.

## Decision

The adapter exposes static authoring knowledge through MCP Resources:

- `substancedesigner://authoring/nodes`
- `substancedesigner://authoring/nodes/{kind}`
- `substancedesigner://authoring/node/{kind}/{slug}`
- `substancedesigner://authoring/node-definition/{definition_id}`
- `substancedesigner://authoring/contracts/{slug}`

The adapter also exposes `get_reference` as the public callable reader for
these URIs. `reference_uris` returned by workflow tools are not passive
metadata; they are next-step inputs for `get_reference`.

Function graph node definitions are split into `function-atomic` and
`function-library` catalogs. These definitions carry both `graph_scopes` and
`context_scopes`. `graph_scopes` says where a node can be placed, while
`context_scopes` says which property or execution context can evaluate it.
For example, SDF function-library nodes are `SDSBSFunctionGraph` nodes but are
marked as requiring the `3d_viewer` context.

`resources/list` must include every concrete node resource so node discovery is
complete without relying on resource templates alone. Resource templates remain
direct lookup helpers.

The adapter exposes one live node introspection tool:

- `get_node`

`get_node` accepts a live `node_id` and inspects an existing graph node. Static
authoring resources cover definition and package-resource information. Runtime
temporary-node probing is not part of the public `get_node` contract.

`get_node` returns:

- runtime observation,
- matched static authoring resource when available,
- best-effort id-level comparison between runtime and static definitions,
- evidence metadata.
- `reference_uris` that point back to relevant authoring resources.

The tool does not expose a separate comparison switch. Comparison is part of
the tool's shaped response whenever a static reference can be matched.

Inspection, validation, and graph-summary tools should include `reference_uris`
where they can, plus `next_tools` entries whose `tool` field is the concrete
callable action id for `get_reference`. This makes Resources usable from the
callable tool workflow because many MCP clients discover and use tools before
they browse resources.

Property-specific Function Graph context catalogs are intentionally deferred
until source data exists. When a caller supplies property-graph context through
`get_graph` with a node-property `GraphRef`, the response may only state that
property context resources are unavailable and that reserved variable names
require evidence from Resources, existing graphs, saved XML, or live API
introspection before editing.

PBR output authoring is not a separate resource contract. Output node usage
rules belong inside the outer compositing graph contract because they are part
of `SDSBSCompGraph` authoring rather than general PBR theory.

Build-time and deploy-time data processing belongs in repository scripts under
`tools/`. These scripts normalize, validate, and compare catalog artifacts before
packaging or release. They are not MCP runtime tools.

## Consequences

The MCP callable surface stays small: `get_reference` handles authoring
reference lookup, and a single runtime inspection tool handles live uncertainty.

Static packaged node definitions remain generated from trusted documentation
artifacts. Live introspection can report mismatches but does not automatically
update the packaged catalog.

Authoring prompts and validation errors can point agents to concrete resources
first, then to `get_node` when live host evidence is needed.
