param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$ErrorActionPreference = "Stop"
$LinkPath = Join-Path $TargetDir "dcc-mcp-substancedesigner"

if (-not (Test-Path $LinkPath)) {
    Write-Host "Plugin link missing: $LinkPath"
    exit 1
}

$item = Get-Item $LinkPath
if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    Write-Host "Plugin link exists: $LinkPath"
    exit 0
}

Write-Host "Path exists but is not a junction: $LinkPath"
exit 2
