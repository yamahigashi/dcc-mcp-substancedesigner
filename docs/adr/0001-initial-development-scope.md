# ADR-0001: Initial Development Scope

## Status

Accepted

## Context

This repository starts as a Substance Designer adapter in the DCC MCP ecosystem. It uses [`dcc-mcp-core`](https://github.com/loonghao/dcc-mcp-core) for shared MCP contracts and runtime boundaries; Substance Designer-specific bridge, graph, and host plugin behavior are owned in this repository.

The first development phase needs a narrow target so the project can establish server shape, bridge behavior, tests, and documentation before expanding into full graph editing.

## Decision

The first practical goal is a read-only MCP adapter for Substance Designer. Initial work should make package, graph, node, and parameter information available through MCP tools without requiring export, packaging, or full adapter feature parity.

Distribution remains clone-based during early development. Packaging, installer scripts, and release automation are deferred until the bridge and tool contracts stabilize.

Windows is the primary operational target. Linux and macOS support are best effort for tests and non-host-specific development tasks.

## Consequences

Read-only capability gives a safe vertical slice for validating the MCP server, TCP bridge, and graph schema. Mutation tools can still be designed early, but production readiness is measured first by reliable inspection of existing Substance Designer content.

The repository should prioritize fake-host integration tests so CI and local development do not require a running Substance Designer instance.
