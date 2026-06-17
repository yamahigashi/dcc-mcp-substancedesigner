# Installation

This guide is for users who want to run the Substance Designer MCP adapter from
release assets. For source checkout and development workflows, see
[`development.md`](development.md). For LLM agent setup notes, see
[`install-agent.md`](install-agent.md).

## Requirements

- Adobe Substance 3D Designer 16.0 or newer
- `uv` on Windows
- An MCP client such as Codex Desktop, Claude Desktop, or another client that
  can connect to a local HTTP MCP endpoint

The adapter is intended for trusted local sessions. The Substance Designer
plugin bridge and MCP endpoints listen on `127.0.0.1` by default.

Install `uv` first if it is not already available:

```powershell
winget install astral-sh.uv
```

## Download the User Bundle

Download the release assets from GitHub Releases:

- `dcc-mcp-substancedesigner-0.1.1-windows.zip`

Wheel, source distribution, and standalone plugin ZIP files are packaging
inputs. Normal users should use the Windows ZIP.

Extract the ZIP, then install the Python command:

```powershell
.\install.bat
```

## Install the Substance Designer Plugin

The ZIP contains a `plugin\dcc-mcp-substancedesigner` plugin folder. Copy that
folder into a Substance Designer plugin directory.

You can also pass the plugin directory to the installer:

```powershell
.\install.bat "C:\path\to\Substance Designer plugins"
```

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
