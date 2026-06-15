# ADR-0007: Semantic Graph Read Model

## Status

Partially superseded by ADR-0013 for public graph editing APIs. The semantic read
model remains valid, but nested-graph-specific public tool guidance is replaced
by capability-driven graph editing.

## Context

ADR-0004 established the initial MCP graph inspection and mutation surface.
ADR-0005 defined declarative state tools for property-backed nested graphs.
ADR-0006 added scope-aware editing guidance and lineage validation for
source-sensitive workflows.

That design is still useful, but production graph review has exposed a deeper
inspection gap. The current tools can show node ids, definitions, positions,
and simple connections, but they do not consistently expose the meaning needed
to review a Substance graph without reading the `.sbs` XML directly. In
particular, callers need node labels, identifiers, graph output usage, filter
parameters, exposed input mappings, instance references, multi-output
connection identity, and Pixel Processor function graph contents.

The root problem is not a missing convenience tool. It is that the adapter does
not yet own a complete read model for Substance graphs. Tool implementations
currently normalize each host response directly into MCP-facing dictionaries,
which makes it easy to lose raw information such as `connRefOutput` and hard to
share semantic interpretation between `get_graph`, `get_node`,
lineage validation, nested graph inspection, and future summary tools.

## Decision

The adapter will be refactored toward an adapter-owned semantic graph read
model. MCP inspection tools should become query views over that model instead
of each tool independently interpreting raw host responses.

The graph inspection pipeline will have explicit layers:

1. Raw extraction from the Substance Designer host plugin and, where necessary,
   `.sbs` package data.
2. Canonical graph modeling that preserves node, port, connection, parameter,
   output, package, and raw reference identity without lossy display-oriented
   normalization.
3. Semantic enrichment that resolves material output usage, filter parameter
   meaning, exposed mappings, instance references, nested graph boundaries, and
   graph analysis facts.
4. MCP tool views that return stable, documented shapes for graph state,
   node detail, output tracing, nested graph inspection, and summaries.

The canonical model should include at least these entities:

- `GraphModel`: graph identity, package identity, nodes, connections, graph
  inputs, graph outputs, exposed parameters, annotations, nested graph
  references, and diagnostics.
- `NodeModel`: stable node id, raw uid where available, definition, kind,
  filter type, label, identifier, GUI comment, inputs, outputs, parameters,
  exposed mappings, instance reference, output binding, nested graph
  references, raw references, and diagnostics.
- `PortModel`: uid, identifier, label, direction, type, index, value metadata,
  and raw references.
- `ConnectionModel`: source node, source output uid, source output identifier,
  destination node, destination input uid, destination input identifier,
  original host connection reference, and raw `connRefOutput` where available.
- `ParameterModel`: identifier, label, type, resolved value, display value,
  raw value, enum metadata, expression metadata, exposure state, and
  diagnostics.
- `GraphOutputModel`: output node id, uid, identifier, label, usage, group,
  source node, source output uid, source output identifier, upstream chain
  metadata, raw references, and diagnostics.
- `NestedGraphModel`: owner graph, owner node, owner property, graph type,
  nodes, connections, outputs, expressions, variables, exposed bindings, raw
  references, and diagnostics.

Semantic enrichment may infer missing values only when it records the fact in
diagnostics. For example, if `basecolor` usage is inferred from an output
identifier because the host API did not expose explicit usage metadata, the
returned model must make that inference visible. Clients must be able to
distinguish host facts, `.sbs` facts, adapter-normalized facts, and adapter
inferences.

Connections must preserve multi-output identity. `connRefOutput` and equivalent
source output uid data are first-class model fields. Display aliases such as
`unique_filter_output` may remain in compatibility views, but they must not be
the only canonical connection identity.

Graph outputs are semantic objects, not just output nodes. The adapter should
resolve and expose output identifiers, labels, usages, source bindings, and
upstream chains. Explicit `.sbs` or host metadata has priority over inference.
Identifier-based usage tables are allowed as fallback enrichment when
diagnostics report that fallback.

Pixel Processor inspection is a dedicated semantic concern. Pixel Processor
review should be served by `get_graph` with a node-property `GraphRef` and a
resolved `function_graph` `GraphKind` plus `pixel_processor` `FunctionContract`,
describing the internal function graph, expressions, parameters, input bindings,
output bindings, and unresolved parts. Passing owner node and property identity
through the bridge must be covered by tests because the graph reference is part
of the public contract.

The MCP inspection surface should converge on these views:

- `get_graph` for graph-level canonical and semantic state, with detail
  levels rather than only boolean expansion flags.
- `get_node` for one-node semantic inspection.
- `get_graph` with `GraphRef.kind=node_property_graph` for property-backed
  function graph inspection.
- `get_graph_outputs` or equivalent graph output inspection.
- `trace_output` for output-specific upstream traversal.
- `summarize_graph` for analysis-oriented reports over the same semantic
  model.

`summarize_graph` is not the source of truth. It should report derived facts
such as output chains, unused nodes, dead branches, disconnected inputs,
unreached outputs, parameter usage, Pixel Processor review points, and
diagnostics. The canonical and semantic graph models remain the source of truth
for other tools and tests.

## Consequences

This is a larger refactor than adding individual fields to existing response
normalizers. The project should avoid growing `schema.py` and `graph_state.py`
into a mixed extraction, normalization, enrichment, and analysis layer.
Dedicated modules are expected, for example:

- `raw_graph.py` or host/plugin extraction helpers;
- `canonical_graph.py` for adapter-owned model construction;
- `semantic_graph.py` for enrichment;
- `parameters.py` or `parameter_resolver.py` for parameter typing and value
  interpretation;
- `outputs.py` or `output_resolver.py` for graph output usage and source
  binding resolution;
- `pixel_processor.py` for Pixel Processor-specific function graph inspection;
- `graph_analysis.py` for upstream tracing, unused node detection, and summary
  reports.

Existing MCP tools should remain available while their internals migrate to the
new read model. Compatibility fields can remain for existing clients, but new
canonical fields should avoid lossy names and should carry diagnostics when
values are absent, unresolved, or inferred.

The implementation should progress in dependency order:

1. Define canonical model shapes and fixtures for representative raw host data.
2. Preserve connection output identity, including `connRefOutput` when
   available.
3. Normalize graph outputs as semantic objects.
4. Move node detail construction onto the canonical model.
5. Add parameter resolution for common filters such as uniform, blend, levels,
   blur, and output nodes.
6. Add Pixel Processor-specific inspection backed by nested graph target tests.
7. Rebuild `get_graph` as a graph model view with explicit detail levels.
8. Add output tracing and graph summary tools on top of the semantic model.

Tests should use fake bridge data for protocol and normalization behavior before
depending on a live host. Live integration tests remain opt-in and should focus
on validating host API assumptions, especially labels, annotations, output
usage, instance references, nested graph access, and multi-output connections.

The adapter still should not infer artistic intent such as "feather
silhouette" from arbitrary graph structure. It should expose graph facts and
well-labeled diagnostics so callers can make domain decisions with enough
evidence.
