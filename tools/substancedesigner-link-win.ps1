param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$PluginSource = Join-Path $RepoRoot "plugin"
$LinkPath = Join-Path $TargetDir "dcc-mcp-substancedesigner"

if (-not (Test-Path $PluginSource)) {
    throw "Plugin source not found: $PluginSource"
}

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
}

if (Test-Path $LinkPath) {
    $item = Get-Item $LinkPath
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Target already exists and is not a junction: $LinkPath"
    }
    Remove-Item $LinkPath -Force
}

New-Item -ItemType Junction -Path $LinkPath -Target $PluginSource | Out-Null
Write-Host "Linked Substance Designer MCP plugin:"
Write-Host "  $LinkPath -> $PluginSource"

