# ADR-0002: Runtime and Dependency Strategy

## Status

Accepted

## Context

Substance 3D Designer 16.0 and later are the target host versions. The project should align with VFX Reference Platform CY2026 where practical. CY2026 specifies Python 3.13.x as the common Python component.

[`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core) provides the shared MCP runtime, adapter contracts, and gateway integration used by this adapter. Published `dcc-mcp-core` packages are available for normal dependency resolution.

## Decision

The target Python runtime is Python 3.13. Development should use `uv` for environment creation, dependency resolution, and command execution.

`dcc-mcp-core` should use a package-first dependency strategy:

- For normal clone-based setup, CI, and release preparation, use the published package constraint from `pyproject.toml`.
- During active local development, developers may explicitly install a local `dcc-mcp-core` checkout when working across adapter/core contracts.

The repository should expose commands through `just`, but each recipe should delegate to `uv run` or `uv sync`.

## Consequences

Python 3.13 lets the adapter match the chosen Substance Designer and CY2026 target instead of carrying older compatibility requirements.

Local core development remains possible without vendoring shared code into this adapter or making sibling repositories a requirement for CI and fresh clones. Release builds stay aligned with packaged `dcc-mcp-core` versions.
