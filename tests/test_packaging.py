"""Tests for distributable package assembly."""

from __future__ import annotations

import importlib.util
import py_compile
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_packager_main() -> Callable[[list[str] | None], int]:
    """Load the packaging entry point without importing from a script package."""
    script_path = REPO_ROOT / "packaging" / "assemble_plugin_package.py"
    spec = importlib.util.spec_from_file_location("assemble_plugin_package", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


def _load_release_module():
    """Load the release build script."""
    script_path = REPO_ROOT / "tools" / "build_release.py"
    spec = importlib.util.spec_from_file_location("build_release", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_release_notes_module():
    """Load the release notes extraction script."""
    script_path = REPO_ROOT / "tools" / "extract_release_notes.py"
    spec = importlib.util.spec_from_file_location("extract_release_notes", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_release_runs_package_builds(monkeypatch, tmp_path: Path) -> None:
    """Release script builds Python, plugin, and user bundle artifacts."""
    module = _load_release_module()
    dist_dir = tmp_path / "dist"
    plugin_dir = tmp_path / "dist_plugin"
    user_dir = tmp_path / "dist_user"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> None:
        calls.append(command)
        if command[1:3] == ["-m", "build"]:
            dist_dir.mkdir()
            (dist_dir / "package.whl").write_text("", encoding="utf-8")
            (dist_dir / "package.tar.gz").write_text("", encoding="utf-8")
            return
        plugin_dir.mkdir()
        (plugin_dir / "plugin.zip").write_text("", encoding="utf-8")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert (
        module.main(
            ["--dist-dir", str(dist_dir), "--plugin-output-dir", str(plugin_dir), "--user-output-dir", str(user_dir)]
        )
        == 0
    )
    assert [command[1:3] for command in calls] == [
        ["-m", "build"],
        ["packaging/assemble_plugin_package.py", "--output-dir"],
    ]
    bundle_path = user_dir / "dcc-mcp-substancedesigner-0.1.1-windows.zip"
    assert bundle_path.is_file()
    with zipfile.ZipFile(bundle_path) as archive:
        names = set(archive.namelist())
    assert "README.txt" in names
    assert "INSTALL.txt" in names
    assert "install.bat" in names
    assert "install.ps1" in names
    assert "package.whl" in names
    assert "plugin/dcc-mcp-substancedesigner/__init__.py" in names
    with zipfile.ZipFile(bundle_path) as archive:
        readme = archive.read("README.txt").decode("utf-8")
        install_bat = archive.read("install.bat").decode("utf-8")
        install_script = archive.read("install.ps1").decode("utf-8")
    assert "Double-click install.bat" in readme
    assert "powershell.exe" in install_bat
    assert "winget install astral-sh.uv" in install_script
    assert "uv tool install --force $Wheel.FullName" in install_script
    assert "Remove-Item $Target -Recurse -Force" in install_script


def test_github_release_uploads_only_user_bundle() -> None:
    """GitHub Releases expose the user bundle, not intermediate package artifacts."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "dist_user/*" in workflow
    assert "dist/*" not in workflow
    assert "dist_plugin/*" not in workflow


def test_extract_release_notes_uses_matching_changelog_section(tmp_path: Path) -> None:
    """Release notes use the requested changelog section."""
    module = _load_release_notes_module()
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [0.2.0] - 2026-01-02\n\nnew\n\n## [0.1.1] - 2026-01-01\n\nold\n",
        encoding="utf-8",
    )

    assert module.extract_notes(changelog, "0.2.0") == "## [0.2.0] - 2026-01-02\n\nnew\n"


def test_assemble_plugin_package_contains_plugin_files(tmp_path: Path) -> None:
    """Plugin zip includes every host plugin source file."""
    output_dir = tmp_path / "dist_plugin"
    main = _load_packager_main()

    assert main(["--output-dir", str(output_dir)]) == 0

    archive_path = output_dir / "dcc-mcp-substancedesigner-plugin.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    expected_plugin_files = {
        "dcc-mcp-substancedesigner/{}".format(path.relative_to(REPO_ROOT / "plugin").as_posix())
        for path in (REPO_ROOT / "plugin").rglob("*.py")
    }
    packaged_plugin_files = {
        name for name in names if name.startswith("dcc-mcp-substancedesigner/") and name.endswith(".py")
    }

    assert packaged_plugin_files == expected_plugin_files
    assert not any("__pycache__" in name for name in names)


def test_plugin_tree_contains_no_generated_python_artifacts() -> None:
    """Plugin source tree does not include generated Python cache artifacts."""
    plugin_dir = REPO_ROOT / "plugin"
    generated = [
        path.relative_to(plugin_dir).as_posix()
        for path in plugin_dir.rglob("*")
        if "__pycache__" in path.parts or path.suffix == ".pyc"
    ]

    assert generated == []


def test_plugin_python_files_have_no_utf8_bom() -> None:
    """Plugin Python files are plain UTF-8 without a BOM."""
    plugin_dir = REPO_ROOT / "plugin"
    for path in plugin_dir.rglob("*.py"):
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def test_plugin_python_files_compile(tmp_path: Path) -> None:
    """Plugin Python files compile before packaging."""
    plugin_dir = REPO_ROOT / "plugin"
    for path in plugin_dir.rglob("*.py"):
        cache_name = "{}.pyc".format(path.relative_to(plugin_dir).as_posix().replace("/", "__"))
        py_compile.compile(path, cfile=tmp_path / cache_name, doraise=True)


def test_plugin_bridge_rejects_invalid_command_payloads() -> None:
    """Bridge command execution source validates malformed command payloads."""
    server_source = (REPO_ROOT / "plugin" / "bridge" / "bridge_server.py").read_text(encoding="utf-8")

    assert "Command must be a JSON object" in server_source
    assert "Command type must be a non-empty string" in server_source
    assert "Command params must be a JSON object" in server_source


def test_plugin_bridge_rejects_oversized_responses() -> None:
    """Bridge protocol source enforces the response size limit."""
    protocol_source = (REPO_ROOT / "plugin" / "bridge" / "bridge_protocol.py").read_text(encoding="utf-8")

    assert "def send_framed(sock: socket.socket, data: bytes) -> None:" in protocol_source
    assert "if len(data) > MAX_MSG_SIZE:" in protocol_source
    assert 'raise ValueError("Message too large: {} bytes".format(len(data)))' in protocol_source


def test_plugin_bridge_reports_http_clients_as_protocol_errors() -> None:
    """Bridge protocol source detects HTTP clients on the raw socket."""
    protocol_source = (REPO_ROOT / "plugin" / "bridge" / "bridge_protocol.py").read_text(encoding="utf-8")

    assert "def looks_like_http_request(header: bytes) -> bool:" in protocol_source
    assert (
        'HTTP_REQUEST_PREFIXES: tuple[bytes, ...] = (b"GET ", b"POST", b"HEAD", b"PUT ", b"PATC", b"DELE", b"OPTI")'
        in protocol_source
    )
    assert "Received an HTTP request on the raw Substance Designer MCP bridge" in protocol_source


def test_wheel_contains_bundled_skills(tmp_path: Path) -> None:
    """Built wheel includes bundled skill metadata."""
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel_path = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel_path) as archive:
        names = set(archive.namelist())

    assert "dcc_mcp_substancedesigner/skills/SKILLS_INDEX.md" in names
    assert "dcc_mcp_substancedesigner/skills/substance-designer/tools.yaml" in names


def test_sdist_contains_repo_support_files(tmp_path: Path) -> None:
    """Built sdist includes repository support files."""
    subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--outdir", str(tmp_path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    sdist_path = next(tmp_path.glob("*.tar.gz"))
    with tarfile.open(sdist_path) as archive:
        names = {Path(name).as_posix() for name in archive.getnames()}

    assert any(name.endswith("/plugin/__init__.py") for name in names)
    assert any(name.endswith("/docs/install.md") for name in names)
    assert any(name.endswith("/.env.example") for name in names)
