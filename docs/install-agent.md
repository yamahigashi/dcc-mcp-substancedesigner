# LLM Agent Installation Notes

This guide is for LLM coding agents and other automated assistants setting up or
checking this repository. User-facing installation steps live in
[`install.md`](install.md). Contributor workflows live in
[`development.md`](development.md).

## Agent Responsibilities

- Keep normal user instructions separate from source checkout workflows.
- Prefer `docs/install.md` when explaining how to use release assets.
- Prefer `docs/development.md` when running tests, builds, or local source
  commands.

## Setup From WSL

Install development dependencies:

```bash
uv sync --extra dev
```

Run the default checks:

```bash
uv run --extra dev pytest tests/ -v --tb=short
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev ty check src/dcc_mcp_substancedesigner/bridge.py plugin/bridge/bridge_server.py --ignore unresolved-import
```

Build release artifacts:

```bash
uv run --extra dev python -m build
uv run --extra dev python packaging/assemble_plugin_package.py
```

## Host Plugin Boundary

Substance Designer runs on Windows. The repository may be edited from WSL, but
the host plugin is loaded by the Windows application.

For development, link the repository-owned plugin into a Windows Substance
Designer plugin directory:

```bash
just substancedesigner-link-win "C:/path/to/Substance Designer/plugins"
```

For user-facing instructions, prefer the release ZIP extraction flow in
[`install.md`](install.md) instead of this development link command.

## Runtime Startup Order

Use this order when diagnosing a local session:

1. Start Substance Designer 16.0 or newer.
2. Load the `dcc-mcp-substancedesigner` plugin.
3. Check the plugin bridge.
4. Start the MCP server.
5. Point the MCP client at the gateway endpoint.

Bridge check from WSL:

```bash
uv run --extra dev dcc-mcp-substancedesigner --check-bridge --sd-port 9881
```

Server start from WSL:

```bash
uv run --extra dev dcc-mcp-substancedesigner --sd-port 9881
```

Windows launcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1
```

## Endpoint Defaults

- Gateway MCP for clients: `http://127.0.0.1:9765/mcp`
- Backend MCP for diagnostics: `http://127.0.0.1:8766/mcp`
- Substance Designer plugin bridge: `127.0.0.1:9881`

Most agents and MCP clients should use the gateway endpoint. Use the backend
endpoint only when diagnosing the adapter directly.

## Direct MCP Client Config

For clients that launch the source checkout directly, use this shape and adjust
the repository path:

```json
{
  "mcpServers": {
    "substancedesigner": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "C:/path/to/dcc-mcp-substancedesigner",
        "dcc-mcp-substancedesigner"
      ],
      "env": {
        "DCC_MCP_ADMIN_UI_PREBUILT": "1",
        "DCC_MCP_SUBSTANCEDESIGNER_HOST": "127.0.0.1",
        "DCC_MCP_SUBSTANCEDESIGNER_PORT": "9881"
      }
    }
  }
}
```

If the server is already running, configure the client to connect to:

```text
http://127.0.0.1:9765/mcp
```

## Live Checks

Live tests require a running host session and are opt in. Mutation tests can edit
the connected Substance Designer session. See
[`integration-testing.md`](integration-testing.md) before enabling them.
