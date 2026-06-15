# ADR-0013: Capability-Driven Graph Editing

## Status

Accepted

## Context

The previous public design separated ordinary package graphs from `nested_graph`
property graphs. That distinction describes where a graph is stored, but it does
not describe the rules an authoring client must obey. Substance Designer
function graphs can be evaluated in different contexts such as Pixel Processor,
generic functions, SDF functions, 3D viewer functions, value processors, and
FX-Map functions. Each context has its own usable nodes, built-in variables,
sampling rules, and output contract.

For LLM clients, exposing separate imperative tools such as `create_node`,
`connect_nodes`, `set_parameter`, and `apply_nested_graph_update` pushes too much
host-editing procedure into the model. The model still needs graph knowledge,
but that knowledge should be provided as context-specific capabilities rather
than guessed from tool names.

## Decision

The public MCP authoring surface is capability-driven and declarative:

- `GraphRef` identifies where the graph lives, such as a package graph or a node
  property graph.
- `GraphKind` identifies the execution surface: `substance_graph`,
  `function_graph`, or `fx_map_graph`.
- `FunctionContract` identifies node-property Function Graph IO and variable
  rules, such as `parameter_function`, `pixel_processor`, `value_processor`,
  `fx_map_dynamic_function`, `sdf_function`, or `host_property_function`.
- `GraphCapabilities` describes the weapons available in that context:
  allowable node definitions, built-ins, output contracts, supported change
  operations, diagnostics, and relevant authoring references.
- `GraphChange` describes the desired edit with logical node ids, connections,
  parameter values, and output selection.

The public workflow is:

1. `get_graph` returns graph state for a `GraphRef` and includes resolved
   graph-kind/contract information when possible.
2. `get_authoring_capabilities` returns the context-specific toolbelt, optionally
   narrowed by intent.
3. `validate_graph_change` checks a declarative change before host mutation.
4. `apply_graph_change` validates and applies the change through internal host
   operations.

Low-level host operations remain implementation details. The adapter may still
use node creation, connection, parameter, property-graph rebuild, and graph-input
operations internally, but these are no longer the primary public MCP editing
contract.

The old public terms `outer graph` and `nested graph` are replaced by
`GraphRef.kind`, `GraphKind`, and `FunctionContract`. `graph_type` is no longer
a standalone public decision; it is part of graph-kind and host-contract
resolution.

## Consequences

LLM clients have one editing mental model: inspect graph, request the applicable
capabilities, declare a graph change, validate, then apply. The adapter owns the
translation from declarative change to host operation order.

The adapter must invest in high-quality capability responses and validation
diagnostics. A smaller tool list is not enough; clients must be told which nodes,
variables, output shapes, and references are valid for the current context.

Unknown contexts are not authorable by default. If the adapter cannot resolve the
context, mutation should stop with diagnostics explaining what evidence is
missing.

ADR-0005, ADR-0006, and the nested-graph-specific portions of ADR-0007 are
superseded for public API design. Their implementation details may remain as
internal bridge mechanics while the new graph-change applier matures.
