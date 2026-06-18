# dcc-mcp-substancedesigner

[![CI](https://github.com/yamahigashi/dcc-mcp-substancedesigner/actions/workflows/ci.yml/badge.svg)](https://github.com/yamahigashi/dcc-mcp-substancedesigner/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](pyproject.toml)
[![Release](https://img.shields.io/github/v/release/yamahigashi/dcc-mcp-substancedesigner?label=github%20release)](https://github.com/yamahigashi/dcc-mcp-substancedesigner/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](pyproject.toml)

Substance Designer adapter for the DCC Model Context Protocol (MCP) ecosystem.

This repository provides a Python MCP adapter and a maintained Adobe Substance
3D Designer host plugin. It uses
[`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core) for shared MCP server
contracts, skill loading, and gateway integration, while Substance
Designer-specific bridge behavior, graph tooling, and plugin commands are owned
here.

## Features

- Repository-owned Substance Designer plugin under `plugin/`
- Local length-prefixed JSON TCP bridge on `127.0.0.1:9881`
- MCP backend endpoint on `127.0.0.1:8766/mcp`
- Gateway endpoint on `127.0.0.1:9765/mcp`
- Bundled skills for scene inspection, graph authoring, and reference lookup
- Fake-host tests for normal CI without a running Substance Designer instance
- Opt-in live integration and mutation tests for a real host session
- Local stub generator for editor assistance without redistributing Adobe or PySide API stubs

## Status

This project is an early `0.1.x` adapter. Normal CI uses fake-host tests and
does not require Substance Designer. Live host checks are opt-in and require
Substance 3D Designer 16.0+ with this repository's plugin loaded. Mutation tests
are gated separately because they intentionally edit the connected host session.

## Installation

GitHub Releases are the distribution channel. Normal users should download the
single Windows bundle:

```text
dcc-mcp-substancedesigner-<version>-windows.zip
```

The bundle assumes Windows, Substance Designer 16.0+, and `uv`. It contains the
Python wheel, the Substance Designer plugin folder, `install.bat`, `README.txt`,
and local installation notes. Wheel, sdist, and standalone plugin ZIP artifacts
are built as internal packaging inputs, but the GitHub Release should expose
only the Windows bundle.

For user installation steps, see [`docs/install.md`](docs/install.md). For
source checkout workflows, see [`docs/development.md`](docs/development.md).
For LLM agent setup notes, see [`docs/install-agent.md`](docs/install-agent.md).

MCP clients should connect to the gateway endpoint:

```text
http://127.0.0.1:9765/mcp
```

## Usage

The default endpoints are:

- Gateway MCP for clients: `http://127.0.0.1:9765/mcp`
- Backend MCP for direct diagnostics: `http://127.0.0.1:8766/mcp`
- Substance Designer plugin bridge: `127.0.0.1:9881`

Check bridge readiness directly:

```powershell
dcc-mcp-substancedesigner --check-bridge --sd-port 9881
```

Source checkout commands, plugin archive builds, and local type stub generation
are documented in [`docs/development.md`](docs/development.md).

## Security

The adapter is intended for trusted local sessions. The plugin bridge listens on
loopback by default, and MCP tools can mutate the open Substance Designer
session. The `execute_python` tool is an explicit diagnostic and recovery escape
hatch that runs arbitrary Python in the host process; prefer typed inspection
and mutation tools for repeatable workflows. See
[`docs/tool-policy.md`](docs/tool-policy.md).

## Bundled Skills

| Skill | Scope | Tools |
|-------|-------|-------|
| `substance-designer` | workflow | scene, graph, node, preview, authoring capabilities, authoring reference lookup, declarative graph-change validation/apply, diagnostics, trusted local Python execution |

## Documentation

- [`docs/install.md`](docs/install.md): user-facing release installation and MCP client setup
- [`docs/development.md`](docs/development.md): source checkout, local commands, plugin linking, and release builds
- [`docs/install-agent.md`](docs/install-agent.md): LLM agent setup notes, WSL rules, and runtime startup order
- [`docs/architecture.md`](docs/architecture.md): adapter boundary, bridge protocol, skill groups, and schema ownership
- [`docs/tool-policy.md`](docs/tool-policy.md): MCP command exposure policy and trusted Python execution boundary
- [`docs/integration-testing.md`](docs/integration-testing.md): live Substance Designer verification and mutation test gates
- [`docs/adr/`](docs/adr/): accepted architecture decisions for runtime, plugin ownership, graph schema, and editing strategy

## CI and Live Testing

Normal CI does not require Substance Designer. It runs linting, fake-host tests,
wheel/sdist build, and the user-facing Windows release bundle build.

Live checks require Substance Designer 16.0+ with the plugin loaded:

```bash
uv run --extra dev python tools/live_verify.py
```

Mutation checks are explicit:

```bash
uv run --extra dev python tools/live_verify.py --mutation
```

See [`docs/integration-testing.md`](docs/integration-testing.md) before running
live mutation tests against a host session.

## Project Structure

```text
dcc-mcp-substancedesigner/
├── src/dcc_mcp_substancedesigner/  # Python adapter, commands, schemas, and bundled skills
├── plugin/                         # Substance Designer host plugin and bridge commands
├── tests/                          # Unit, fake-host, packaging, and opt-in live tests
├── tools/                          # Local helper scripts and stub generation
├── docs/                           # Install, architecture, policy, integration, and ADR docs
├── justfile                        # Task runner
└── pyproject.toml                  # Build and dependency metadata
```

## Requirements

- Substance 3D Designer 16.0+
- Python 3.13
- `uv`
- `dcc-mcp-core >= 0.17.43`

## Development Boundaries

- [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core): shared MCP contracts, server composition, skills runtime, gateway integration, and adapter boundaries
- `src/`, `plugin/`, `tests/`, and `docs/adr/`: source of truth for Substance Designer bridge behavior, graph/node tooling, and host integration decisions

## License

MIT
