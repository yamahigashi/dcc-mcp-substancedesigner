# ADR-0014: Transactional Property Graph Replace

## Status

Accepted

## Context

ADR-0013 makes `GraphChange` the public authoring model. For node-property
Function Graphs, applying a `GraphChange` currently lowers to an internal
property-graph replace operation.

Substance Designer property graphs are owned by node properties such as
`sdf_scene`, `perpixel`, or `function`. Replacing one by deleting the current
property graph before applying the new desired state is destructive. A failed
node creation, parameter write, connection, output selection, or resource lookup
must not leave the owner property without its previous graph.

This is not only a validation quality issue. Validation can miss host-specific
facts such as runtime port identifiers, package resource availability, read-only
state, or API behavior. The mutation boundary must remain safe even when
validation is incomplete.

## Decision

Declarative replacement of an existing node-property graph must be restore-safe.

Before a destructive replace:

- read the existing property graph, if one exists;
- serialize it into an internal state that can be reapplied;
- reject the mutation before touching the host if the current graph cannot be
  restored;
- apply the requested replacement only after that restore state is available.

If replacement fails after mutation begins:

- if no previous graph existed, remove the partially-created property graph;
- if a previous graph existed, rebuild it from the saved state;
- report `rolled_back=true` and `partial_changes=false` only when restoration
  succeeds;
- report rollback failure as a high-severity mutation error with
  `partial_changes=true`.

Package-backed Function Graph instance nodes are restorable only when their
referenced resource URL is captured in the saved state and replayed as
`host_creation.kind=function_graph_resource_instance`.

Preflight validation remains valuable, but it is not the safety boundary.
Runtime rollback is required because host facts can still diverge from static
node definitions.

## Consequences

LLM clients can trust that a failed declarative property-graph replace will not
silently erase an existing graph.

The plugin bridge owns the destructive mutation transaction. Public MCP clients
continue to send declarative `GraphChange`; they do not need to know about host
delete/create ordering.

Some existing property graphs may be rejected before mutation if they contain
nodes that cannot be serialized into a restorable state. That is preferable to
destroying user state.

Future work can improve the restorable snapshot with richer host metadata, but
the invariant remains: no existing property graph may be destroyed by a failed
declarative replace.
