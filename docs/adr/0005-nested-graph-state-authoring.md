# ADR-0005: Nested Graph State Authoring

## Status

Superseded by ADR-0013 for public MCP API design. The implementation details may
remain as internal host bridge mechanics.

## Context

Substance Designer nodes can own nested graphs through node properties. Pixel
Processor `perpixel` function graphs are the immediate use case, but the same
problem shape can appear in other property-backed graph types such as function
graphs and, later, FX-Map style graphs.

The project needs an MCP-facing design that lets agents author these internal
graphs without relying on arbitrary Python execution as the normal workflow and
without creating one MCP tool per node type or per artistic recipe.

The adapter needs a declarative graph-state contract rather than a large set of
recipe-specific MCP tools. The public contract should make nested graph changes
inspectable, validatable, and repeatable without relying on arbitrary Python
execution as the normal authoring path.

## Decision

Nested graph authoring will use a declarative state model. MCP tools should
describe, validate, diff, and apply the desired state of a nested graph rather
than requiring clients to issue many small imperative editing calls.

The core MCP surface should focus on:

- `get_nested_graph`
- `plan_nested_graph_update`
- `apply_nested_graph_update`
- parameter-only update support for known generated states

ADR-0006 applies the same "inspect before mutate" principle to outer graph
editing, but does not require outer graph edits to immediately adopt a full
read, validate, diff, and apply state API. The nested graph tools remain the
accepted interface for property-backed internal graphs.

The state schema should identify:

- the target package, graph, node, and property;
- the nested graph type, such as `SDSBSFunctionGraph`;
- logical node ids, node definitions, values, positions, and connections;
- output node selection;
- optional provenance metadata for generated state, including generator name,
  generator version, owned logical nodes, and exposed parameter bindings.

The default authoring modes are:

- `sync`: compare the current nested graph with the desired state and apply the
  smallest safe operation the adapter understands;
- `param_update`: only update declared parameters in a previously generated
  compatible state, rejecting structural changes;
- `replace`: rebuild the nested graph from the desired state, requiring explicit
  caller intent.

Arbitrary patching is not part of the initial public contract. Limited patch
operations can be considered later if there is a clear recurring need and the
adapter can validate them transactionally.

For outer graph edits, ADR-0006 prioritizes stronger node-network inspection,
typed mutation primitives, and targeted lineage validation. This does not
change the conservative stance for arbitrary nested graph patching.

Recipe and template generation is not part of the required MCP server core.
For example, a feather mask generator should live first in a skill, prompt,
client-side helper, or documentation example that produces a nested graph state.
The MCP server then validates, diffs, and applies that state. A server-side
template registry can be added later as a convenience layer, but it must not be
required for the core nested graph authoring path.

`execute_python` remains an explicit investigation, development, and emergency
fallback. It is not the normal authoring contract for nested graphs once typed
state tools exist.

## Consequences

The MCP tool surface stays small and general. Pixel Processor function graphs,
future function-backed nodes, and other property-backed graph types can share
the same inspection and apply pipeline.

Agents and clients can generate graph state outside the server, then use the
server as the safety boundary for validation, diffing, conflict detection, and
application. This keeps artistic recipes from becoming adapter API surface area
too early.

Parameter tuning remains efficient. When a generated nested graph carries
provenance and parameter binding metadata, the adapter can update values without
rebuilding the whole graph.

Manual edits are treated conservatively. If the current nested graph no longer
matches the stored provenance or desired-state assumptions, the adapter should
return a structured conflict instead of silently overwriting user work. Callers
can then inspect or explicitly request `replace`.

The implementation needs stronger schema tests and live-host tests around graph
type validation, function node definitions, connection typing, output selection,
and conflict behavior.

If a future outer graph-state API is added and later unified with nested graph
state tools, the existing nested tool names should remain as compatibility
wrappers until clients have a migration path.
