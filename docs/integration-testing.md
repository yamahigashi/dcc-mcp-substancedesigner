# Integration Testing

Unit and fake-bridge tests do not require Substance Designer:

```bash
uv run --extra dev pytest tests/ -v
```

Local CI-equivalent checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev ty check src/dcc_mcp_substancedesigner/bridge.py plugin/bridge/bridge_server.py --ignore unresolved-import
uv run --extra dev pytest tests/ -v --tb=short
uv run --extra dev python -m build
uv run --extra dev python packaging/assemble_plugin_package.py
```

With `just`, the same local gate is:

```bash
just ci
```

The normal test suite also verifies:

- every `tools.yaml` source script exists
- bundled skill names are unique
- bundled skill tools use only the `public` startup visibility group
- the public workflow catalog exposes the Codex-first workflow tools, including `execute_python`
- plugin command handlers match the adapter-owned allowlist
- plugin helper modules pass Ruff docstring and annotation rules
- `execute_python` is exposed through the plugin, facade, and MCP skill layers
- legacy `execute_code` is absent from the plugin and MCP skill layers
- plugin Python files compile
- plugin archive contents are valid
- bundled skills are present in the wheel
- support files such as `plugin/`, `docs/`, and `.env.example` are present in the sdist
- the installed `dcc-mcp-substancedesigner --check-bridge` console script can reach a bridge
- `--check-bridge` rejects Substance Designer versions older than 16.0

Live integration tests require:

- Substance 3D Designer 16.0+
- Python 3.13-compatible host runtime
- `plugin/` loaded in Substance Designer
- bridge listening on `127.0.0.1:9881`

Before running live tests, confirm bridge readiness:

```bash
uv run --extra dev dcc-mcp-substancedesigner --check-bridge --sd-port 9881
```

To run bridge readiness and read-only live tests as one gate:

```bash
uv run --extra dev python tools/live_verify.py
```

Run live tests explicitly:

```bash
DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 uv run --extra dev pytest tests/ -m integration -v
```

Or:

```bash
just test-live
```

Mutation tests use the same live-host opt-in:

```bash
DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 uv run --extra dev pytest tests/test_live_mutation.py -v
```

Or:

```bash
just test-live-mutation
```

The combined verification command can include mutation checks:

```bash
uv run --extra dev python tools/live_verify.py --mutation
```

Mutation tests create disposable graphs and clean up after themselves where the host API supports it.
They also create an unsaved disposable package for each test, so an existing `.sbs` package does not need to be open.

## Refresh and Restart Boundaries

There are two live processes in a development session:

- the Windows Substance Designer host plugin under `plugin/`
- the MCP adapter server under `src/dcc_mcp_substancedesigner/`

`refresh_plugin` reloads only the host plugin inside Substance Designer. It does
not reload the MCP adapter process, bundled skill scripts, schemas, validation
logic, or command dispatch code. Restart the MCP server whenever files under
`src/`, bundled skill scripts, schemas, or adapter dependencies change.

Use this rule before live mutation testing:

- plugin-only change: `just substancedesigner-sync-and-refresh <plugin-target>`
- adapter or skill change: restart the MCP server, then run `refresh_plugin` if
  plugin files also changed

`<plugin-target>` is the local `sd_mcp_plugin/` directory under your Substance
Designer user plugins folder. Keep machine-specific install paths out of the
repository.

The just recipes read local endpoint defaults from environment variables:

- `DCC_MCP_SUBSTANCEDESIGNER_HOST`: Substance Designer bridge host, default `127.0.0.1`
- `DCC_MCP_SUBSTANCEDESIGNER_PORT`: Substance Designer bridge port, default `9881`
- `DCC_MCP_SUBSTANCEDESIGNER_MCP_HOST`: backend MCP host for generated URLs, default `127.0.0.1`
- `DCC_MCP_SUBSTANCEDESIGNER_MCP_PORT`: backend MCP port, default `8766`
- `DCC_MCP_GATEWAY_PORT`: gateway MCP port, default `9765`
- `DCC_MCP_SUBSTANCEDESIGNER_REFRESH_HOST`: refresh target host, default follows `DCC_MCP_SUBSTANCEDESIGNER_MCP_HOST`
- `DCC_MCP_SUBSTANCEDESIGNER_REFRESH_PORT`: refresh target port, default `38766`

Do not rely on `refresh_plugin` to pick up new `apply_graph_change` behavior.
An old adapter can still transform a new payload incorrectly before it reaches
the refreshed host plugin.

Graceful restart is implemented at the launcher layer, not as an MCP tool that
kills its own request handler. Use:

```bash
just substancedesigner-restart-win
```

The restart flow:

1. record the MCP server PID, backend port, gateway port, bridge host/port, and
   working directory when the server starts
2. ask the current process to stop or terminate the PID owning the backend port
3. wait until the backend port is released
4. start a new server with the same arguments
5. health-check the new `/mcp` endpoint and bridge diagnostic before mutation
   tests continue

The launcher state lives at
`%LOCALAPPDATA%\dcc-mcp\substancedesigner-server.json` by default. If you start
the server with a custom port, set the matching environment variables or pass
the same ports to the restart recipe:

```bash
just substancedesigner-restart-win 38767 0
```

The second argument is the gateway port. Use `0` when the server was started
without a gateway.

## WSL and Windows Endpoint Checks

Substance Designer and the host plugin run on Windows, while this repository is
often edited from WSL. Check which side owns the MCP server before choosing a
probe command.

If the MCP server was started by the Windows launcher, probe it from Windows:

```bash
cmd.exe /c curl.exe -s -X POST http://127.0.0.1:8766/mcp ^
  -H "Content-Type: application/json" ^
  -H "Accept: application/json, text/event-stream" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"diagnostic\",\"arguments\":{}}}"
```

Do not assume WSL `curl http://127.0.0.1:<port>/mcp` can reach a Windows-owned
server. A WSL-side `connection refused` can be a namespace or forwarding issue,
not proof that the Windows server is down.

For scripted live checks from WSL against a Windows-owned server, call
`cmd.exe /c curl.exe` from the script. Avoid `cmd.exe /c powershell -Command -`
for stdin-fed scripts; in this environment it can exit without executing the
stdin payload. Prefer a checked-in PowerShell file, an explicit `-File`, or
Windows `curl.exe` invoked from a WSL script.
