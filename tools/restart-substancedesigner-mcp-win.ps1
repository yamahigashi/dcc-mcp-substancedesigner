param(
    [int]$Port = 0,
    [int]$GatewayPort = -1,
    [string]$StatePath = "",
    [int]$TimeoutSec = 30,
    [switch]$Force,
    [switch]$Debug
)

$ErrorActionPreference = "Stop"

if (-not $StatePath) {
    $StatePath = Join-Path (Join-Path $env:LOCALAPPDATA "dcc-mcp") "substancedesigner-server.json"
}
$env:DCC_MCP_ADMIN_UI_PREBUILT = "1"
if (-not $env:MCP_LOG_LEVEL) {
    $env:MCP_LOG_LEVEL = "INFO"
}

function Read-State {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "State file not found: $Path. Start the MCP server with tools/start-substancedesigner-mcp-win.ps1 first."
    }
    return Get-Content -Raw -Path $Path | ConvertFrom-Json
}

function Get-PortOwnerProcessIds {
    param([int]$LocalPort)
    if ($LocalPort -le 0) {
        return @()
    }
    try {
        $Connections = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction Stop
        return @($Connections | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
    }
    catch {
        $Netstat = & netstat -ano -p tcp
        $Suffix = ":$LocalPort"
        $Pids = @()
        foreach ($Line in $Netstat) {
            $Parts = $Line -split "\s+"
            if ($Parts.Count -lt 5) {
                continue
            }
            $LocalAddress = $Parts[1]
            $State = $Parts[3]
            $PidText = $Parts[4]
            if ($LocalAddress.EndsWith($Suffix) -and $State.ToUpperInvariant() -eq "LISTENING") {
                $Pids += [int]$PidText
            }
        }
        return @($Pids | Sort-Object -Unique)
    }
}

function Stop-ProcessTree {
    param(
        [int]$ProcessId,
        [switch]$ForceKill
    )
    if ($ProcessId -le 0) {
        return
    }
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $Process) {
        return
    }
    Write-Host "Stopping process $ProcessId..."
    try {
        Stop-Process -Id $ProcessId -ErrorAction Stop
        Wait-Process -Id $ProcessId -Timeout 5 -ErrorAction SilentlyContinue
    }
    catch {
        Write-Host "Graceful stop failed for ${ProcessId}: $($_.Exception.Message)"
    }
    $Process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -ne $Process -or $ForceKill) {
        Write-Host "Force-stopping process tree $ProcessId..."
        & taskkill /PID $ProcessId /T /F | Out-Host
    }
}

function Wait-ForPortRelease {
    param(
        [int]$LocalPort,
        [int]$TimeoutSeconds
    )
    if ($LocalPort -le 0) {
        return
    }
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if ((Get-PortOwnerProcessIds -LocalPort $LocalPort).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    $Owners = Get-PortOwnerProcessIds -LocalPort $LocalPort
    throw "Timed out waiting for port $LocalPort to be released. Owners: $($Owners -join ', ')"
}

function Wait-ForMcpDiagnostic {
    param(
        [string]$McpUrl,
        [int]$TimeoutSeconds
    )
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $Body = @{
        jsonrpc = "2.0"
        id = 1
        method = "tools/call"
        params = @{
            name = "diagnostic"
            arguments = @{}
        }
    } | ConvertTo-Json -Depth 8 -Compress
    $BodyPath = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($BodyPath, $Body, [System.Text.UTF8Encoding]::new($false))
    $LastError = ""
    try {
        while ((Get-Date) -lt $Deadline) {
            try {
                $ReadyText = & curl.exe -s -m 5 "$($McpUrl -replace '/mcp$', '/v1/readyz')"
                if ($LASTEXITCODE -ne 0 -or -not $ReadyText -or -not $ReadyText.Contains('"process":true')) {
                    $LastError = "readyz not ready: $ReadyText"
                    Start-Sleep -Milliseconds 500
                    continue
                }
                $ResponseText = & curl.exe -s -m 5 -X POST $McpUrl -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" --data-binary "@$BodyPath"
                if ($LASTEXITCODE -ne 0 -or -not $ResponseText) {
                    $LastError = "curl.exe exited with $LASTEXITCODE"
                    Start-Sleep -Milliseconds 500
                    continue
                }
                if (-not $ResponseText.TrimStart().StartsWith("{")) {
                    $LastError = "MCP returned non-JSON response: $ResponseText"
                    Start-Sleep -Milliseconds 500
                    continue
                }
                $Response = $ResponseText | ConvertFrom-Json
                $Context = $Response.result.structuredContent.context
                if ($Context.ok -eq $true -and $Context.result.sd_running -ne $false) {
                    return $Context
                }
            }
            catch {
                $LastError = $_.Exception.Message
                Start-Sleep -Milliseconds 500
                continue
            }
            Start-Sleep -Milliseconds 500
        }
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue -Path $BodyPath
    }
    throw "Timed out waiting for MCP diagnostic at $McpUrl. Last error: $LastError"
}

function ConvertTo-CmdLiteral {
    param([string]$Value)
    return '"' + ($Value -replace '"', '""') + '"'
}

$State = Read-State -Path $StatePath
$RepoRoot = [string]$State.repo_root
if (-not $RepoRoot) {
    throw "State file does not contain repo_root: $StatePath"
}

$ResolvedPort = $(if ($Port -gt 0) { $Port } else { [int]$State.port })
$ResolvedGatewayPort = $(if ($GatewayPort -ge 0) { $GatewayPort } else { [int]$State.gateway_port })
$McpUrl = "http://127.0.0.1:$ResolvedPort/mcp"
$Executable = [string]$State.executable
if (-not $Executable) {
    $Executable = "uv"
}

$RunArgs = @(
    "run",
    "--no-sync",
    "dcc-mcp-substancedesigner",
    "--port",
    "$ResolvedPort",
    "--sd-host",
    "$($State.sd_host)",
    "--sd-port",
    "$($State.sd_port)"
)

if ($ResolvedGatewayPort -gt 0) {
    $RunArgs += @("--gateway-port", "$ResolvedGatewayPort")
}
else {
    $RunArgs += @("--gateway-port", "0")
}
if ([bool]$State.debug -or $Debug) {
    $RunArgs += "--debug"
}

$CandidatePids = @()
if ($State.process_id) {
    $CandidatePids += [int]$State.process_id
}
$CandidatePids += Get-PortOwnerProcessIds -LocalPort $ResolvedPort
if ($ResolvedGatewayPort -gt 0) {
    $CandidatePids += Get-PortOwnerProcessIds -LocalPort $ResolvedGatewayPort
}
$CandidatePids = @($CandidatePids | Sort-Object -Unique)

foreach ($CandidatePid in $CandidatePids) {
    Stop-ProcessTree -ProcessId $CandidatePid -ForceKill:$Force
}

Wait-ForPortRelease -LocalPort $ResolvedPort -TimeoutSeconds $TimeoutSec
if ($ResolvedGatewayPort -gt 0) {
    Wait-ForPortRelease -LocalPort $ResolvedGatewayPort -TimeoutSeconds $TimeoutSec
}

Write-Host "Starting Substance Designer MCP server..."
Write-Host "  Backend MCP: $McpUrl"
Write-Host "  Repository: $RepoRoot"
$LogDir = Join-Path (Join-Path $env:LOCALAPPDATA "dcc-mcp") "log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$StdoutLog = Join-Path $LogDir "dcc-mcp-substancedesigner-restart-$LogStamp.out.log"
$StderrLog = Join-Path $LogDir "dcc-mcp-substancedesigner-restart-$LogStamp.err.log"
$LaunchScript = Join-Path $LogDir "dcc-mcp-substancedesigner-restart-$LogStamp.cmd"
$LaunchCommand = (@($Executable) + $RunArgs | ForEach-Object { ConvertTo-CmdLiteral -Value ([string]$_) }) -join " "
$LaunchLines = @(
    "@echo off",
    "cd /d $(ConvertTo-CmdLiteral -Value $RepoRoot)",
    "$LaunchCommand > $(ConvertTo-CmdLiteral -Value $StdoutLog) 2> $(ConvertTo-CmdLiteral -Value $StderrLog)"
)
$LaunchLines | Set-Content -Encoding ASCII -Path $LaunchScript
$StartArgs = "/c start `"`" /min $(ConvertTo-CmdLiteral -Value $LaunchScript)"
$LauncherProcess = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList $StartArgs `
    -WindowStyle Hidden `
    -PassThru

$NewState = [ordered]@{
    process_id = $LauncherProcess.Id
    launcher_process_id = $LauncherProcess.Id
    executable = $Executable
    argv = @($Executable) + $RunArgs
    repo_root = $RepoRoot
    port = $ResolvedPort
    gateway_port = $ResolvedGatewayPort
    mcp_url = $McpUrl
    gateway_url = $(if ($ResolvedGatewayPort -gt 0) { "http://127.0.0.1:$ResolvedGatewayPort/mcp" } else { "" })
    sd_host = [string]$State.sd_host
    sd_port = [int]$State.sd_port
    debug = [bool]$State.debug -or [bool]$Debug
    no_gateway = $ResolvedGatewayPort -le 0
    state_path = $StatePath
    stdout_log = $StdoutLog
    stderr_log = $StderrLog
    launch_script = $LaunchScript
    started_at = (Get-Date).ToString("o")
    restarted_at = (Get-Date).ToString("o")
}
$NewState | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $StatePath

$Diagnostic = Wait-ForMcpDiagnostic -McpUrl $McpUrl -TimeoutSeconds $TimeoutSec
$ServerPids = @(Get-PortOwnerProcessIds -LocalPort $ResolvedPort)
if ($ServerPids.Count -gt 0) {
    $NewState.process_id = [int]$ServerPids[0]
    $NewState | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -Path $StatePath
}
Write-Host "Restarted Substance Designer MCP server."
Write-Host "  Process: $($NewState.process_id)"
Write-Host "  State file: $StatePath"
Write-Host "  Stdout log: $StdoutLog"
Write-Host "  Stderr log: $StderrLog"
Write-Host "  Diagnostic sd_running: $($Diagnostic.result.sd_running)"
