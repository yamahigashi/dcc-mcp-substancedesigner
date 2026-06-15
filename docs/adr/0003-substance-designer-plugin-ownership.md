# ADR-0003: Substance Designer Plugin Ownership

## Status

Accepted

## Context

This adapter needs the Substance Designer plugin and MCP server to evolve together, especially around command names, payload shapes, error reporting, and host lifecycle behavior.

## Decision

The Substance Designer plugin should be developed as part of this adapter. This repository is the ownership boundary for the maintained plugin/server pair.

The plugin bridge protocol is a local TCP protocol using 4-byte big-endian length-prefixed JSON messages. The MCP server talks to the plugin through an adapter-owned bridge client.

## Consequences

Keeping the plugin in the same repository makes protocol changes reviewable and testable with the MCP server. It also avoids hidden coupling to an external checkout during normal development.

The project should add fake TCP bridge tests before relying on a live Substance Designer instance. Real Substance Designer tests should be integration-marked or documented as manual checks.
