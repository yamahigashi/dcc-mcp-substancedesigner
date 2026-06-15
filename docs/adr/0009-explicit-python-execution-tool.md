# ADR-0009: Explicit Python Execution Tool

## Status

Accepted

## Context

The adapter has a typed MCP surface for common Substance Designer inspection and
authoring workflows. That surface is preferable for repeatable operations
because the adapter can validate inputs, normalize responses, and constrain
behavior.

Substance Designer host development still needs a direct diagnostic escape hatch
for advanced inspection, live repair, and unmodeled `sd.api` behavior. The
previous plugin kept a legacy `execute_code` alias while the MCP skill exposed
`execute_python`, which made the policy unclear and left an unneeded command
name in the host bridge.

## Decision

`execute_python` is an intentionally exposed MCP tool. It executes arbitrary
Python in the connected Substance Designer process on the host main thread.
The tool is marked as non-read-only, destructive, and non-idempotent in the skill
metadata. It remains explicitly exposed because the adapter relies on explicit
tool naming, trusted-local configuration, and typed alternatives rather than
client-side suppression for discovery.

The legacy `execute_code` command is removed from the plugin command registry
and is not exposed through the adapter or MCP skills.

Typed tools remain the normal authoring contract. `execute_python` is reserved
for trusted local sessions, diagnostics, emergency recovery, and functionality
that has not yet earned a typed adapter command.

## Consequences

The public surface is explicit about the risk instead of hiding arbitrary Python
behind an undocumented compatibility alias.

Clients that need arbitrary host scripting must call `execute_python` by name.
Clients that need repeatable graph edits should continue to use typed
inspection, authoring, and nested graph tools.

Tests should enforce that plugin command handlers stay on an allowlist, that
`execute_python` exists across the plugin, facade, and skill layers, and that
`execute_code` does not reappear.
