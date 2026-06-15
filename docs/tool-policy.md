# Tool Exposure Policy

The adapter exposes stable MCP tools over the repository-owned Substance Designer plugin bridge.

## Exposed

The public MCP surface is a Codex-first workflow surface. It covers:

- scene/package/graph/node inspection
- authoring reference lookup through `get_reference`
- graph previews
- GraphKind and FunctionContract-specific graph authoring capabilities
- declarative graph-change validation and apply workflows
- diagnostics and static authoring reference resources
- explicit Python execution through `execute_python`

## Startup Surface

Adapter-owned tools use a single `public` group. That group is the complete
Substance Designer workflow surface owned by this adapter. The adapter no
longer exposes separate scene, authoring, and reference skill surfaces as
public MCP tools.

The `public` group has a size budget of 14 callable tools. New tools should
first be evaluated against user-goal fit, overlap with existing workflow tools,
and whether a mode/detail parameter would serve the workflow with less
tool-selection noise.

All public adapter tools are enabled at startup. Low-level adapter helper tools
are disabled for this adapter's startup surface. Generic `dcc-mcp-core`
management tools such as skill search/loading, jobs, and dynamic tool
registration may still appear in standard MCP `tools/list`; they are not part
of the Substance Designer workflow surface or budget.

Some clients expose only a capped initial subset of callable tools to the
model. That initial model-facing subset should prefer read/discovery/preview
and debug tools:

- `get_scene`
- `get_graph`
- `get_node`
- `get_authoring_plan`
- `get_reference`
- `get_preview`
- `diagnostic`
- `execute_python`

This initial subset is a session protocol surface, not permission to begin broad
authoring. `get_authoring_plan` should establish current evidence, relevant
references, preview targets, and the next bounded authoring unit before concrete
capability or mutation tools are treated as actionable. See ADR-0019.

Concrete capability tools (`get_authoring_capabilities`), mutation tools
(`validate_graph_change`, `apply_graph_change`, `replace_graph_state`), file
tools (`export_output`, `save_package`), and lifecycle tools (`refresh_plugin`)
are later-phase tools and should not displace graph evidence, authoring plans,
reference lookup, diagnostics, or explicit Python from the initial model-visible
set.

Low-level plugin commands and command-facade methods remain implementation
details. The public MCP callable surface is not a mirror of the plugin command
registry.

`reference_uris` returned by inspection, validation, and planning tools are
actionable. Callers should read them with `get_reference`; workflow responses
include `next_tools` entries whose `tool` value is the concrete callable action
id, such as `substance_designer__get_reference`, and whose `public_name` is the
logical workflow name. Local skill paths, script paths, generated JSON files,
and command implementation files are not public authoring contracts.

Diagnostic bridge command registries, execution trace operation names, and
internal host primitive names are evidence about what the adapter did. They are
not callable MCP tools and should not be used for tool selection.

## Python Execution

`execute_python` is intentionally exposed as an MCP tool. It runs arbitrary Python in the connected Substance Designer process on the host main thread, so callers must treat it as a trusted-local diagnostic and recovery tool rather than a routine authoring primitive.

Typed inspection, capability, validation, and graph-change apply tools remain the preferred interface for repeatable workflows because they validate inputs and normalize responses. `execute_python` exists for advanced host inspection, emergency repair, and gaps in the typed surface where direct `sd.api` access is required.

`execute_python` is part of the public startup surface by policy.

The legacy `execute_code` alias is not part of the plugin or MCP surface. `tests/test_skill_catalog.py` enforces the plugin command allowlist and verifies that `execute_python` is present while `execute_code` is absent.
