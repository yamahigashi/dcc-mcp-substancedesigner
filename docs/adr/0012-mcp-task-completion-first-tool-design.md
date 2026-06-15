# ADR-0012: MCP Task-Completion-First Tool Design

## Status

Accepted

## Context

The adapter is used through MCP tools selected by an LLM or a client from a
tool surface. A technically precise tool boundary is not enough when the model
naturally chooses a nearby tool and then concludes that the workflow cannot be
completed.

One observed failure path was graph input exposure. The model found narrow
graph-input and control primitives, rejected them as too specific, failed to
discover the graph-input binding path, and moved toward direct `.sbs` XML editing.
The missing capability was not primarily a host implementation gap. The tool
surface did not guide the model to a successful typed MCP path.

ADR-0008 keeps MCP `tools/list` as the authoritative callable surface. ADR-0010
keeps the tool catalog under a size budget. Together, those decisions favor
improving natural existing entry points before adding fine-grained tools.

## Decision

MCP tools in this adapter are an agent-facing product surface, not a mirror of
internal bridge commands. Tool design should prioritize task completion and
usable entry points over strict low-level responsibility separation.

When a user or LLM naturally reaches a tool that can safely complete the
workflow, the adapter should make that tool succeed or move the caller toward a
typed MCP continuation. It should not require the caller to infer the exact
internal primitive first.

For graph input creation, hardcoded parameter exposure, and dynamicValue
parameter binding, typed MCP tools must be the normal path. Tool descriptions,
skill instructions, and operation responses should not route those workflows to
direct `.sbs` XML edits.

Existing high-reach tools should absorb common adjacent intent before new tools
are added. For example, `apply_graph_change` should validate context-specific
capabilities, create needed graph nodes, connect them, and set parameters behind
one declarative graph-change request instead of exposing separate public
mutation primitives for each internal bridge step.

## Consequences

Tool descriptions should include user-goal vocabulary, not only internal API
terms. Examples include "expose hardcoded value", "make parameter
controllable", "graph input", "dynamicValue", and "Function Graph".

Failure responses should identify completed changes, the failing phase, the
unfinished work, and the next typed MCP tool where practical.

New MCP tools still need an explicit design reason under the ADR-0010 tool
surface budget. Prefer consolidating task-completion behavior into an existing
natural entry point when doing so is clear and safe.
