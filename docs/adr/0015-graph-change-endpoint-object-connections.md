# ADR-0015: GraphChange Endpoint Object Connections

## Status

Accepted

## Context

ADR-0013 defines `GraphChange` as the declarative authoring surface. The first
connection shape used flat fields:

```json
{
  "from": "shape",
  "from_output": "output",
  "to": "blur",
  "to_input": "input1"
}
```

That shape is compact but ambiguous for LLM clients. `from` and `to` look like
complete endpoints, but they actually hold only logical node ids. This led
clients to try several incompatible forms such as `node.port`, `source/target`,
and mixed flat fields before discovering the implementation contract.

## Decision

The canonical `GraphChange.connections[]` shape is an endpoint object:

```json
{
  "from": {
    "node": "shape",
    "output": "output"
  },
  "to": {
    "node": "blur",
    "input": "input1"
  }
}
```

`from.node` and `to.node` reference either logical node ids declared in the same
`GraphChange.nodes[]` payload or existing host node ids already present in the
target graph. `from.output` and `to.input` reference explicit host port ids from
node definitions or live node inspection. Function graph built-ins are expressed
as endpoint objects too:

```json
{
  "from": {
    "builtin": "$pos"
  },
  "to": {
    "node": "sample",
    "input": "pos"
  }
}
```

The public contract does not use `node.port` endpoint strings. They are short,
but they require escaping and make validation errors less precise.

The adapter may accept older flat fields internally while callers migrate, but
all returned references, examples, and authoring guidance should use endpoint
objects.

`nodes[].id` follows the same desired-change model: an id that resolves to an
existing host node updates that node, while any other id is a logical alias for a
new node. This avoids forcing callers to switch to a separate operations model
for the common case of connecting or updating existing graph nodes.

## Consequences

LLM clients can model a connection as "source endpoint to target endpoint"
without remembering that `from` and `to` are only partial endpoint fields.

Validation can produce better error paths, such as
`change.connections[0].from.output`, and the lowering layer can canonicalize port
aliases before host mutation.

Existing low-level host operations still use flat arguments such as
`from_node_id`, `from_output`, `to_node_id`, and `to_input`. That shape remains
an internal bridge detail rather than the public declarative GraphChange model.
