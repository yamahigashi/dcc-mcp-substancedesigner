param(
    [Parameter(Mandatory = $true)]
    [string]$TargetDir
)

$ErrorActionPreference = "Stop"
$LinkPath = Join-Path $TargetDir "dcc-mcp-substancedesigner"

if (-not (Test-Path $LinkPath)) {
    Write-Host "No plugin link found: $LinkPath"
    exit 0
}

$item = Get-Item $LinkPath
if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "Refusing to remove non-junction path: $LinkPath"
}

Remove-Item $LinkPath -Force
Write-Host "Removed plugin link: $LinkPath"

