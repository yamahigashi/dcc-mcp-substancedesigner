# Architecture Notes

This adapter uses [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core) for MCP server composition, skill loading, gateway integration, and shared adapter contracts.

The Substance Designer host boundary is a local TCP bridge owned by this repository. The bridge protocol uses a 4-byte big-endian payload length followed by a JSON command object.

Graph and node workflows are exposed as stable MCP tools first, then mapped to Substance Designer plugin commands behind the adapter boundary. The public MCP surface is intentionally smaller than the plugin command catalog and is defined by this repository's workflow skill, command facade, schema normalization, and ADRs.

The bundled public skill is:

- `substance-designer`: Codex-first workflow tools for scene inspection, authoring plans, reference lookup, graph inspection, node inspection, previews, context-specific authoring capabilities, declarative graph-change validation/apply, diagnostics, and explicit Python execution.

The public tool group is:

- `public`: the complete adapter-owned callable workflow catalog. It is kept small so Codex-style tool exposure can keep the workflow and reference tools directly callable. Clients that cap initial model-facing tools should prefer the read/discovery/preview/debug planning subset described in ADR-0018 and ADR-0019.

Bridge responses can be returned as raw plugin payloads for debugging, but MCP-facing tools normalize common inspection data into adapter-owned schemas.

Graph authoring uses a plan-first, capability-driven public model:

- `GraphRef` identifies the graph location, such as a package graph or node property graph;
- `GraphKind` identifies the execution surface, such as a Substance graph, Function graph, or FX-Map graph;
- `FunctionContract` identifies node-property Function Graph rules, such as parameter, Pixel Processor, Value Processor, SDF, or host-property function IO;
- `AuthoringPlan` identifies the bounded authoring unit, required evidence, workflow references, and preview checkpoints before concrete capability or mutation tools are treated as actionable;
- `GraphCapabilities` describes allowed nodes, built-ins, output contracts, supported change operations, diagnostics, and references;
- `GraphChange` declares the intended edit while the adapter owns host operation ordering.

Names have three separate layers:

- plugin command names, such as `apply_nested_graph_state`, are host bridge commands;
- logical public tool names, such as `apply_graph_change`, define the adapter workflow contract;
- registered action ids, such as `substance_designer__apply_graph_change`, are the concrete callable ids returned in `next_tools.tool`;
- diagnostic bridge command names and execution trace operations are not callable MCP tools.

See `docs/tool-policy.md` for the command exposure boundary.
