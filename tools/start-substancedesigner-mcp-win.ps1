param(
    [int]$Port = 8766,
    [int]$GatewayPort = 9765,
    [switch]$NoGateway,
    [string]$SdHost = "127.0.0.1",
    [int]$SdPort = 9881,
    [switch]$SkipSync,
    [switch]$CheckBridge,
    [switch]$Debug,
    [string]$StatePath = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $StatePath) {
    $StatePath = Join-Path (Join-Path $env:LOCALAPPDATA "dcc-mcp") "substancedesigner-server.json"
}
$env:DCC_MCP_ADMIN_UI_PREBUILT = "1"
if (-not $env:MCP_LOG_LEVEL) {
    $env:MCP_LOG_LEVEL = "INFO"
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv was not found on PATH. Install uv or run this script from a shell where uv is available."
}

Push-Location $RepoRoot
try {
    if (-not $SkipSync) {
        Write-Host "Syncing Windows environment..."
        Write-Host "  DCC_MCP_ADMIN_UI_PREBUILT=1"
        & uv sync --extra dev
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    if ($CheckBridge) {
        $CheckArgs = @(
            "run",
            "--no-sync",
            "dcc-mcp-substancedesigner",
            "--check-bridge",
            "--sd-host",
            $SdHost,
            "--sd-port",
            "$SdPort"
        )
        & uv @CheckArgs
        exit $LASTEXITCODE
    }

    $McpUrl = "http://127.0.0.1:$Port/mcp"
    Write-Host "Starting Substance Designer MCP server for Windows..."
    Write-Host "  Backend MCP: $McpUrl"
    Write-Host "  Substance Designer bridge: ${SdHost}:$SdPort"

    $RunArgs = @(
        "run",
        "--no-sync",
        "dcc-mcp-substancedesigner",
        "--port",
        "$Port",
        "--sd-host",
        $SdHost,
        "--sd-port",
        "$SdPort"
    )

    if ($NoGateway) {
        $RunArgs += @("--gateway-port", "0")
    }
    else {
        $GatewayUrl = "http://127.0.0.1:$GatewayPort/mcp"
        Write-Host "  Gateway MCP: $GatewayUrl"
        $RunArgs += @("--gateway-port", "$GatewayPort")
    }

    if ($Debug) {
        $RunArgs += "--debug"
    }

    $StateDir = Split-Path -Parent $StatePath
    if ($StateDir) {
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    }

    $Process = Start-Process -FilePath "uv" -ArgumentList $RunArgs -NoNewWindow -PassThru
    try {
        $State = [ordered]@{
            process_id = $Process.Id
            executable = "uv"
            argv = @("uv") + $RunArgs
            repo_root = $RepoRoot.Path
            port = $Port
            gateway_port = $(if ($NoGateway) { 0 } else { $GatewayPort })
            mcp_url = $McpUrl
            gateway_url = $(if ($NoGateway) { "" } else { $GatewayUrl })
            sd_host = $SdHost
            sd_port = $SdPort
            debug = [bool]$Debug
            no_gateway = [bool]$NoGateway
            state_path = $StatePath
            started_at = (Get-Date).ToString("o")
        }
        $State | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $StatePath
    }
    catch {
        if ($Process -and -not $Process.HasExited) {
            & taskkill /PID $Process.Id /T /F | Out-Host
        }
        throw
    }
    Write-Host "  State file: $StatePath"
    Write-Host "  Server process: $($Process.Id)"

    $Process.WaitForExit()
    exit $Process.ExitCode
}
finally {
    Pop-Location
}
