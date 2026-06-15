# ADR-0016: GraphChange Readable Contract Safety

## Status

Accepted

## Context

`GraphChange` is the public declarative authoring model used by LLM callers.
Recent live tests showed three contract mismatches:

- package graph output nodes accepted `usage` during validation, but the host
  property is named `usages`, so invalid shapes could fail only during apply;
- public documentation exposed both `usage` and `usages`, forcing callers to
  choose between an LLM-natural name and a host implementation name;
- `GraphChange.connections[]` now uses endpoint objects, but `get_graph`
  returned only flat connection fields, making read-modify-write workflows
  require avoidable translation.

Separately, graph summaries emitted a warning for every output whose material
usage was unset and not inferable from the identifier. That is too noisy for
normal authoring, where an output can be valid before usage policy is chosen.

## Decision

The public GraphChange output metadata key is `usage`.

The adapter lowers `usage` to the Substance Designer host property `usages`
during package graph apply. Callers should not declare `usages` directly in new
GraphChange payloads. Validation rejects ambiguous payloads that contain both
`usage` and `usages`, and rejects array/list `usages` before mutation. If the
host eventually needs true multi-usage arrays, that must be introduced as a new
explicit public contract rather than smuggling host shape into `GraphChange`.

`get_graph` keeps the existing flat `connections` array for compatibility, but
also returns `canonical_connections` in endpoint object form:

```json
{
  "from": {"node": "shape", "output": "output"},
  "to": {"node": "blur", "input": "input1"}
}
```

This mirrors the canonical `GraphChange.connections[]` shape and gives LLM
callers a direct copy/edit/apply loop.

Unresolved output usage is no longer a warning when identifier or label metadata
exists. It is reported as an informational `output_usage_unset` diagnostic.
Only outputs with no usage and no naming metadata remain warning-worthy.

MCP-side behavior changes must bump the adapter and plugin-visible version so
live testers can correlate behavior with installed code.

## Consequences

- LLM callers have one natural public key for output usage: `usage`.
- Invalid output usage shapes fail in `validate_graph_change`, before any host
  mutation or rollback path is needed.
- Read and write connection shapes now align through `canonical_connections`.
- Existing flat connection readers continue to work while new callers can avoid
  flat-to-endpoint conversion.
- `usages` remains an internal host detail and a legacy alias only where
  existing compatibility requires reading it.
