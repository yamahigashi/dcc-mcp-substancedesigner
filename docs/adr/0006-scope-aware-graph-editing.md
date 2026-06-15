# ADR-0006: Scope-Aware Graph Editing

## Status

Superseded by ADR-0013 for public MCP API design. The inspection and validation
concerns continue under `GraphRef`, `GraphKind`, `FunctionContract`, and
`GraphChange`.

## Context

ADR-0004 defined low-level outer graph inspection and mutation primitives.
ADR-0005 added declarative state authoring for nested property graphs such as
Pixel Processor `perpixel` function graphs.

That split is useful, but it leaves a practical gap for edits that must extend
or transform an existing graph artifact. A client can create new nodes and wire
final outputs while accidentally bypassing the existing node that the user or
recipe selected as the operation source. The final outputs may be connected and
visually plausible, while the graph structure no longer represents the intended
processing chain.

The root problem is not that the adapter lacks a tool to infer artistic roles
such as `feather_silhouette_raw`. Those names are recipe or user context, not
facts stored in the Substance graph. The adapter should not classify nodes by
artistic intent. It should expose enough graph facts for the caller to select a
source explicitly, then provide editing and validation operations that preserve
that selected source when the task requires it.

The adapter should use a conservative design instead of a large all-purpose
graph-state apply API. Operation targets need to be inspectable before mutation,
and routine mutation tools should stay close to Substance Designer's native
graph object model.

## Decision

Substance Designer graph editing will use a layered design:

1. Strengthen graph inspection.
2. Keep direct mutation primitives for single-step edits.
3. Add small chain-building helpers only when they match common workflows.
4. Add lineage validation only for workflows that explicitly require an existing
   source to reach a later output.
5. Treat a full scope-aware graph-state apply API as a future convergence path,
   not the immediate center of the design.

The immediate priority is a normalized graph inspection contract that can
describe operation targets before mutation. It should expose, at minimum:

- graph identity and output bindings;
- nodes with stable ids, definitions, labels where available, and positions;
- node inputs and outputs with index, identifier/name when available, and type
  when available;
- connections with source node, source output, destination node, and destination
  input;
- upstream and downstream consumers/producers or enough data for the caller to
  compute them;
- nested graph boundaries, including owner node, property name, graph type, and
  summary counts.

Mutation primitives from ADR-0004 remain valid. They should return enough
before/after information for callers to verify the result, especially when a
connection or output binding is replaced. Direct mutation is appropriate for
simple create, connect, disconnect, move, parameter, and delete operations.

For common multi-node operations, the adapter may provide a narrow chain helper.
Such a helper should accept existing node references as connection endpoints, not
only newly created nodes.
It should remain a convenience wrapper around create/connect/set/layout/cook
style primitives, not a recipe engine.

Example shape:

```json
{
  "parent_graph": "Substance_graph",
  "nodes": [
    {"ref": "warp", "definition": "sbs::compositing::directionalwarp"},
    {"ref": "blur", "definition": "sbs::compositing::blur"}
  ],
  "connections": [
    {
      "from": {"existing_node_id": "1572132059", "output": "unique_filter_output"},
      "to": {"ref": "warp", "input": "input1"}
    },
    {
      "from": {"ref": "warp", "output": "unique_filter_output"},
      "to": {"ref": "blur", "input": "input1"}
    }
  ]
}
```

Lineage validation is a separate capability, not something every mutation must
carry. It is used when the task has a structural requirement such as "the
selected source node must feed opacity." It must operate on graph facts, not
semantic role inference.

Example:

```json
{
  "graph": "Substance_graph",
  "source": {"node_id": "1572132059", "output": "unique_filter_output"},
  "target": {"output_identifier": "opacity"},
  "requirement": "source_reaches_target"
}
```

This validation may be exposed as a small read-only tool or as part of a broader
`validate_graph_edit` command. The important contract is that callers can ask
whether a selected source reaches a target output after an edit. The adapter
does not decide why that source matters.

A larger `get_graph` / `validate_graph_state` / `diff_graph_state` /
`apply_graph_state` family remains a possible future convergence path if the
project accumulates enough repeated multi-step edit workflows to justify it.
It should not be introduced as the first response to this problem. Introducing
that API too early risks hiding missing inspection and connection semantics
behind an overly broad abstraction.

## Consequences

The near-term MCP surface stays aligned with existing ADR-0004 primitives:
inspect first, mutate through typed operations, and use the scripting fallback
only when typed tools do not cover the case.

The adapter's first responsibility is to make Substance graphs observable as
node networks with ports, connections, output bindings, and nested graph
boundaries. Without that foundation, higher-level plan/apply abstractions will
be brittle.

Recipe meaning remains outside the adapter. A user or client can select a node
as the source for a workflow, but the adapter validates only structural facts
such as existence, connectability, connection replacement, and reachability.

The specific failure mode where outputs are connected from a recomputed branch
instead of the selected source is addressed by targeted lineage validation,
not by requiring every edit to use a heavyweight graph-state document.

If a future scope-aware graph-state API is added, it should build on the same
inspection schema and lineage validation semantics defined here. Existing direct
mutation tools should remain available as lower-level operations.
