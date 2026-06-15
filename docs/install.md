# Installation

This guide is for users who want to run the Substance Designer MCP adapter from
release assets. For source checkout and development workflows, see
[`development.md`](development.md). For LLM agent setup notes, see
[`install-agent.md`](install-agent.md).

## Requirements

- Adobe Substance 3D Designer 16.0 or newer
- `uv`
- An MCP client such as Codex Desktop, Claude Desktop, or another client that
  can connect to a local HTTP MCP endpoint

The adapter is intended for trusted local sessions. The Substance Designer
plugin bridge and MCP endpoints listen on `127.0.0.1` by default.

## Download Release Assets

Download the release assets from GitHub Releases:

- the Python wheel or source distribution for `dcc-mcp-substancedesigner`
- the Substance Designer plugin ZIP

Install the Python package from the downloaded wheel:

```powershell
uv tool install C:\path\to\dcc_mcp_substancedesigner-0.1.1-py3-none-any.whl
```

If you installed a source distribution instead, use the equivalent local path in
the install command.

## Install the Substance Designer Plugin

Extract the plugin ZIP into a Substance Designer plugin directory. The archive
contains a `dcc-mcp-substancedesigner` plugin folder.

After extraction, the plugin directory should contain:

```text
Substance Designer plugins/
+-- dcc-mcp-substancedesigner/
    +-- __init__.py
    +-- bridge/
    +-- commands/
    +-- ...
```

Start Substance Designer, then enable or load the plugin from the application's
plugin management UI. Keep Substance Designer running while using the MCP
adapter.

## Start the MCP Server

Start the server after Substance Designer is running and the plugin is loaded:

```powershell
$env:DCC_MCP_ADMIN_UI_PREBUILT = "1"
dcc-mcp-substancedesigner --sd-port 9881
```

The default endpoints are:

- Gateway MCP for clients: `http://127.0.0.1:9765/mcp`
- Backend MCP for direct diagnostics: `http://127.0.0.1:8766/mcp`
- Substance Designer plugin bridge: `127.0.0.1:9881`

Most MCP clients should use the gateway endpoint.

## Configure Your MCP Client

Configure your MCP client, such as Codex Desktop or Claude Desktop, to connect
to:

```text
http://127.0.0.1:9765/mcp
```

For clients that launch the server process directly, use this shape and adjust
paths or ports as needed:

```json
{
  "mcpServers": {
    "substancedesigner": {
      "command": "dcc-mcp-substancedesigner",
      "args": ["--sd-port", "9881"],
      "env": {
        "DCC_MCP_ADMIN_UI_PREBUILT": "1",
        "DCC_MCP_SUBSTANCEDESIGNER_HOST": "127.0.0.1",
        "DCC_MCP_SUBSTANCEDESIGNER_PORT": "9881"
      }
    }
  }
}
```

## Verify the Connection

With Substance Designer running and the plugin loaded, run:

```powershell
dcc-mcp-substancedesigner --check-bridge --sd-port 9881
```

If the bridge check succeeds, start the server again and connect your MCP
client to `http://127.0.0.1:9765/mcp`.

## Troubleshooting

If the bridge check fails:

- confirm Substance Designer 16.0 or newer is running
- confirm the plugin is loaded
- confirm the bridge port is `9881`, or pass the configured port with
  `--sd-port`

If the MCP client cannot connect:

- confirm the server process is still running
- use `http://127.0.0.1:9765/mcp` for normal client access
- use `http://127.0.0.1:8766/mcp` only for direct backend diagnostics

If `uv` cannot install the Python package, confirm that it can resolve Python
3.13 or newer for this project.
