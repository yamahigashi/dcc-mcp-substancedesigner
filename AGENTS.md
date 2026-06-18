# Repository Guidelines

## Project Structure & Module Organization

This repository implements a DCC MCP adapter for Adobe Substance 3D Designer 16.0+.

- `src/dcc_mcp_substancedesigner/`: Python adapter runtime, bridge client, command facade, schema normalization, MCP server, and bundled skills.
- `src/dcc_mcp_substancedesigner/skills/`: MCP skill packages grouped by scene inspection, authoring, recipes, and reference tools.
- `plugin/`: repository-owned Substance Designer host plugin and embedded recipe/documentation data.
- `tests/`: pytest suite. Live host checks are opt-in integration tests.
- `docs/`: architecture, installation, integration testing, tool policy, and ADRs.
- `tools/`: Windows plugin helpers, release assembly, live verification, and local development utilities.

Use [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core) for shared MCP contracts, server composition, skills runtime, gateway integration, and adapter boundaries. Treat this repository's `src/`, `plugin/`, `tests/`, and ADRs as the source of truth for Substance Designer bridge behavior and graph/node tooling.

## Build, Test, and Development Commands

Use `uv` for local development.

- `uv sync --extra dev`: install runtime and development dependencies.
- `uv run pytest tests/ -v --tb=short`: run the default suite, excluding live integration tests.
- `uv run ruff check src/ tests/ tools/`: lint Python sources.
- `uv run ruff format src/ tests/ tools/`: format Python sources.
- `uv run python -m build`: build the wheel and sdist.
- `uv run python tools/build_release.py`: build the user-facing release bundle.
- `uv run dcc-mcp-substancedesigner --check-bridge`: verify a running plugin bridge.

## Coding Style & Naming Conventions

Target Python 3.13. Ruff controls formatting: spaces, double quotes, 120-character line length, and import sorting. Keep package/module names lowercase with underscores. Keep MCP skill names stable and descriptive, for example `get_graph_state` or `create_instance_node`.

Prefer shared abstractions from `dcc-mcp-core`. Substance Designer-specific behavior belongs behind `bridge.py`, `commands.py`, and `schema.py`.

## Testing Guidelines

Keep normal tests independent from a running Substance Designer instance. Mark host-dependent tests with `integration`; run them only with `DCC_MCP_SUBSTANCEDESIGNER_LIVE=1`. Mutation tests additionally require `DCC_MCP_SUBSTANCEDESIGNER_MUTATION=1`.

Add fake-bridge tests for protocol, command normalization, validation, skill script behavior, packaging, and tool catalog coverage before relying on live host checks.

## Commit & Pull Request Guidelines

This repository currently has no established Git history. Use short imperative commit messages, such as `Add bridge validation tests`. Pull requests should describe behavior changes, list validation commands, link related issues, and include sample MCP output when tool responses change.

## Security & Configuration Tips

Do not commit credentials, license data, local install paths, generated archives, or machine-specific Substance Designer configuration. Document safe placeholders in `.env.example` and keep live bridge access limited to local trusted sessions.
