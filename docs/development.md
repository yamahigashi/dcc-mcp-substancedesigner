# Development

This guide is for contributors working from a source checkout. User installation
steps live in [`install.md`](install.md), and LLM agent setup notes live in
[`install-agent.md`](install-agent.md).

## Source Checkout

Use Python 3.13 and `uv` for local development:

```bash
uv sync --extra dev
```

For active local `dcc-mcp-core` development:

```bash
just dev-core
uv run --no-sync pytest tests/test_server.py -q
```

Use `--no-sync` after `just dev-core`; `uv run --extra dev` follows
`uv.lock` and reinstalls the published `dcc-mcp-core`. Run `just dev` when you
want to restore the locked dependency set.

After a required `dcc-mcp-core` change is released, update the adapter's
`pyproject.toml` dependency floor and `uv.lock` in the adapter PR.

## Local Commands

Run the default test suite:

```bash
uv run --extra dev pytest tests/ -v --tb=short
```

Run linting and formatting checks:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev ty check src/dcc_mcp_substancedesigner/bridge.py plugin/bridge/bridge_server.py --ignore unresolved-import
```

Build the Python distributions:

```bash
uv run --extra dev python -m build
```

Build all release artifacts for the release workflow or GitHub Releases:

```bash
uv run --extra dev python tools/build_release.py
```

Outputs:

- `dist/`: wheel and sdist for package workflows
- `dist_plugin/`: standalone Substance Designer plugin ZIP
- `dist_user/`: user-facing Windows bundle

The `justfile` exposes the same commands as shorter recipes:

```bash
just test
just lint-all
just build
```

## Plugin Linking for Development

The maintained Substance Designer plugin lives in `plugin/`. On Windows, link
it into a Substance Designer plugin directory:

```bash
just substancedesigner-link-win "C:/path/to/Substance Designer/plugins"
```

Check or remove the link:

```bash
just substancedesigner-status-win "C:/path/to/Substance Designer/plugins"
just substancedesigner-unlink-win "C:/path/to/Substance Designer/plugins"
```

Create a plugin ZIP archive for manual installation or release packaging:

```bash
just package-plugin
```

## Local Server

Start Substance Designer 16.0+, load the plugin, then check the bridge:

```bash
just check-bridge
```

Equivalent direct command:

```bash
uv run --extra dev dcc-mcp-substancedesigner --check-bridge --sd-port 9881
```

Start the MCP server from the source checkout:

```bash
uv run --extra dev dcc-mcp-substancedesigner --sd-port 9881
```

Default endpoints:

- Gateway MCP for client access: `http://127.0.0.1:9765/mcp`
- Backend MCP for direct diagnostics: `http://127.0.0.1:8766/mcp`
- Substance Designer plugin bridge: `127.0.0.1:9881`

## Windows Launcher

On a Windows host, use the PowerShell launcher:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1
```

The launcher runs `uv sync --extra dev` once, then starts with `uv run
--no-sync` so the environment it prepared is reused. It intentionally uses
Windows uv's default `.venv`, and sets `DCC_MCP_ADMIN_UI_PREBUILT=1` so the
bundled gateway admin UI can be reused without requiring Node/npm.

Start only the backend MCP endpoint:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1 -NoGateway
```

Check the plugin bridge from Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1 -CheckBridge
```

## Local Type Stubs

Generated Adobe Substance Designer and PySide stubs are local development
artifacts and are not committed. Generate them only for editor completion or
local plugin type checking:

```bash
uv run python tools/generate_stubs.py
```

## Integration Testing

Normal tests do not require a running Substance Designer instance. Live host
checks are opt in and are documented in
[`integration-testing.md`](integration-testing.md).
