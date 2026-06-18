"""Build release artifacts for CI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

INSTALL_SCRIPT = r"""param(
    [string]$SubstanceDesignerPluginDir
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it with: winget install astral-sh.uv"
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Internal = Join-Path $Root "_internal"
$Wheel = Get-ChildItem $Root -Filter "dcc_mcp_substancedesigner-*.whl" | Select-Object -First 1
if (-not $Wheel) {
    $Wheel = Get-ChildItem $Internal -Filter "dcc_mcp_substancedesigner-*.whl" | Select-Object -First 1
}
if (-not $Wheel) {
    throw "Wheel file not found in the _internal folder"
}

uv tool install --force $Wheel.FullName

if ($SubstanceDesignerPluginDir) {
    $Source = Join-Path $Root "plugin\dcc-mcp-substancedesigner"
    $Target = Join-Path $SubstanceDesignerPluginDir "dcc-mcp-substancedesigner"
    if (Test-Path $Target) {
        Remove-Item $Target -Recurse -Force
    }
    Copy-Item -Path $Source -Destination $Target -Recurse
    Write-Host "Installed Substance Designer plugin to $Target"
}

Write-Host "Installed dcc-mcp-substancedesigner. Run: dcc-mcp-substancedesigner --check-bridge"
"""

INSTALL_BAT = r"""@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0_internal\install.ps1" %*
if errorlevel 1 (
  echo.
  echo Installation failed. See the message above.
  pause
  exit /b 1
)
echo.
echo Installation finished.
pause
"""

RUN_SERVER_BAT = r"""@echo off
setlocal
set MCP_LOG_LEVEL=INFO
dcc-mcp-substancedesigner --sd-port 9881
if errorlevel 1 (
  echo.
  echo Server stopped with an error. See the message above.
  pause
  exit /b 1
)
"""

README_TXT = """dcc-mcp-substancedesigner

Requirements:
- Windows
- Adobe Substance 3D Designer 16.0 or newer
- uv

Files:
- README.txt: this file
- install.bat: installs the MCP server command
- run-server.bat: starts the MCP server
- plugin\\dcc-mcp-substancedesigner: Substance Designer plugin folder

Install:
1. Install uv if needed:
   winget install astral-sh.uv

2. Double-click install.bat.

3. Copy plugin\\dcc-mcp-substancedesigner into your Substance Designer plugins folder.

Run:
1. Start Substance Designer.
2. Enable or load the dcc-mcp-substancedesigner plugin.
3. Double-click run-server.bat.

MCP clients should connect to:
http://127.0.0.1:9765/mcp

Optional diagnostic command:
dcc-mcp-substancedesigner --check-bridge --sd-port 9881
"""


def _project_version(repo_root: Path) -> str:
    with (repo_root / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def _write_user_bundle(repo_root: Path, dist_dir: Path, output_dir: Path) -> Path:
    version = _project_version(repo_root)
    wheel = next(dist_dir.glob("*.whl"), None)
    if wheel is None:
        raise SystemExit(f"No wheel found in {dist_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"dcc-mcp-substancedesigner-{version}-windows.zip"
    if archive_path.exists():
        archive_path.unlink()

    plugin_dir = repo_root / "plugin"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", README_TXT)
        archive.writestr("install.bat", INSTALL_BAT)
        archive.writestr("run-server.bat", RUN_SERVER_BAT)
        archive.writestr("_internal/install.ps1", INSTALL_SCRIPT)
        archive.write(wheel, Path("_internal") / wheel.name)
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            archive.write(path, Path("plugin/dcc-mcp-substancedesigner") / path.relative_to(plugin_dir))

    return archive_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Python and user release artifacts")
    parser.add_argument("--dist-dir", default="dist", help="Python package artifact directory")
    parser.add_argument("--user-output-dir", default="dist_user", help="User-facing release bundle directory")
    parser.add_argument("--no-clean", action="store_true", help="Keep existing artifact directories")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / args.dist_dir
    user_output_dir = repo_root / args.user_output_dir

    if not args.no_clean:
        shutil.rmtree(dist_dir, ignore_errors=True)
        shutil.rmtree(user_output_dir, ignore_errors=True)

    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist_dir)],
        cwd=repo_root,
        check=True,
    )
    user_bundle = _write_user_bundle(repo_root, dist_dir, user_output_dir)

    artifacts = sorted(dist_dir.glob("*.whl")) + sorted(dist_dir.glob("*.tar.gz")) + [user_bundle]
    if not artifacts:
        raise SystemExit("No release artifacts were produced.")

    print("Built artifacts:")
    for artifact in artifacts:
        try:
            display_path = artifact.relative_to(repo_root)
        except ValueError:
            display_path = artifact
        print(f"- {display_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
