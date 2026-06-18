# dcc-mcp-substancedesigner development commands
# Requires: https://github.com/casey/just

set shell := ["sh", "-cu"]
set windows-shell := ["pwsh.exe", "-NoProfile", "-Command"]

sd_bridge_host := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_HOST", "127.0.0.1")
sd_bridge_port := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_PORT", "9881")
mcp_host := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_MCP_HOST", "127.0.0.1")
mcp_port := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_MCP_PORT", "8766")
gateway_port := env_var_or_default("DCC_MCP_GATEWAY_PORT", "9765")
refresh_mcp_host := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_REFRESH_HOST", mcp_host)
refresh_mcp_port := env_var_or_default("DCC_MCP_SUBSTANCEDESIGNER_REFRESH_PORT", "38766")
refresh_mcp_endpoint := "http://" + refresh_mcp_host + ":" + refresh_mcp_port + "/mcp"

@default:
    just --list

dev:
    uv sync --extra dev

serve:
    uv run --extra dev python -m dcc_mcp_substancedesigner

test:
    uv run --extra dev pytest tests/ -v --tb=short

test-cov:
    uv run --extra dev pytest tests/ -v --tb=short --cov=src/dcc_mcp_substancedesigner --cov-report=term-missing

lint:
    uv run --extra dev ruff check .

lint-plugin:
    uv run --extra dev ruff check plugin

lint-format:
    uv run --extra dev ruff format --check .

fix:
    uv run --extra dev ruff check --fix .

format:
    uv run --extra dev ruff format .

type-check:
    uv run --extra dev ty check src/dcc_mcp_substancedesigner/bridge.py plugin/bridge/bridge_server.py --ignore unresolved-import

lint-all: lint lint-plugin lint-format

build:
    uv run --extra dev python -m build

release:
    uv run --extra dev python tools/build_release.py

check-bridge:
    uv run --extra dev dcc-mcp-substancedesigner --check-bridge --sd-host {{sd_bridge_host}} --sd-port {{sd_bridge_port}}

start-win:
    cmd.exe /c powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1 -Port {{mcp_port}} -GatewayPort {{gateway_port}} -SdHost {{sd_bridge_host}} -SdPort {{sd_bridge_port}}

substancedesigner-restart-win port=mcp_port gateway_port=gateway_port:
    cmd.exe /c powershell -NoProfile -ExecutionPolicy Bypass -File tools/restart-substancedesigner-mcp-win.ps1 -Port {{port}} -GatewayPort {{gateway_port}}

check-bridge-win:
    cmd.exe /c powershell -NoProfile -ExecutionPolicy Bypass -File tools/start-substancedesigner-mcp-win.ps1 -CheckBridge -SdHost {{sd_bridge_host}} -SdPort {{sd_bridge_port}}

test-live:
    DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 uv run --extra dev pytest tests/ -m integration -v

test-live-mutation:
    DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 DCC_MCP_SUBSTANCEDESIGNER_MUTATION=1 uv run --extra dev pytest tests/test_live_mutation.py -v

verify-live:
    uv run --extra dev python tools/live_verify.py

verify-live-mutation:
    uv run --extra dev python tools/live_verify.py --mutation

dev-core:
    uv pip install -e ../dcc-mcp-core

substancedesigner-sync-plugin target:
    rsync -a --delete --exclude '__pycache__/' --exclude '*.pyc' plugin/ "{{target}}"

substancedesigner-refresh-plugin endpoint=refresh_mcp_endpoint:
    cmd.exe /c curl.exe -s -X POST "{{endpoint}}" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"refresh_plugin\",\"arguments\":{}}}"

substancedesigner-sync-and-refresh target endpoint=refresh_mcp_endpoint:
    just substancedesigner-sync-plugin "{{target}}"
    cmd.exe /c curl.exe -s -X POST "{{endpoint}}" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"refresh_plugin\",\"arguments\":{}}}"

substancedesigner-link-win target:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/substancedesigner-link-win.ps1 -TargetDir "{{target}}"

substancedesigner-unlink-win target:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/substancedesigner-unlink-win.ps1 -TargetDir "{{target}}"

substancedesigner-status-win target:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/substancedesigner-status-win.ps1 -TargetDir "{{target}}"

clean:
    uv run --extra dev python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'build', 'src/dcc_mcp_substancedesigner.egg-info']]"

ci: lint-all test release
    @echo "All CI checks passed"
