# ADR-0008: MCP Standard Tool Discovery Priority

## Status

Accepted

## Context

The Substance Designer adapter exposes many read-only and authoring tools
through dcc-mcp-core skills. The core runtime also supports progressive skill
and group discovery through `search_tools`, `search_skills`, `list_skills`,
`get_skill_info`, `load_skill`, and `activate_tool_group`.

Progressive discovery is useful, but it must not replace or weaken MCP's
standard tool contract. In MCP, `tools/list` is the standard operation for
listing currently available tools, and its pagination is expressed through
`nextCursor`.

## Decision

The adapter follows this priority order:

1. MCP standard semantics come first.
   `tools/list` is the authoritative callable tool surface, and clients must
   follow `nextCursor` until it is absent before treating a list operation as
   complete.
2. Tool-surface changes must be visible through the standard MCP path.
   Loading skills, unloading skills, activating groups, and deactivating groups
   must update the callable surface and emit `notifications/tools/list_changed`
   or a compatible delta notification through dcc-mcp-core.
3. Progressive discovery is a secondary catalog layer.
   `search_tools`, `search_skills`, `list_skills`, and `get_skill_info` may
   help select and inspect capabilities, but they are not substitutes for the
   callable `tools/list` surface.
4. Adapter-specific convenience tools may be added only after the standard
   surface is correct. Purpose-specific tools such as a future
   `inspect_current_scene` are allowed as ergonomic wrappers, not as a fix for
   broken standard discovery.

## Consequences

The adapter must not depend on non-callable `__skill__*` or `__group__*` entries
appearing in `tools/list`. Those entries are discovery hints and belong in
search or skill metadata surfaces.

When a tool is reported as registered by skill metadata, loading or activating
the owning skill/group must make that tool appear in standard `tools/list`.
If it does not, that is a server/tool-surface bug rather than an agent workflow
problem.

Substance-specific cleanup and convenience APIs can be considered after this
standard contract is satisfied.
