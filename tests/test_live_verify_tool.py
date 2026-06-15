"""Tests for the live verification helper."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_live_verify():
    script_path = REPO_ROOT / "tools" / "live_verify.py"
    spec = importlib.util.spec_from_file_location("live_verify", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_verify_runs_bridge_and_read_only_tests_with_shared_bridge_env() -> None:
    module = _load_live_verify()
    calls: list[tuple[list[str], dict[str, str]]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[object]:
        calls.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0)

    assert module.main(["--host", "localhost", "--port", "9999", "--pytest-args=-q"], runner=runner) == 0

    assert len(calls) == 2
    assert calls[0][0][-4:] == ["--sd-host", "localhost", "--sd-port", "9999"]
    assert calls[1][0][-4:] == ["tests/test_live_integration.py", "-m", "integration", "-q"]
    assert calls[1][1]["DCC_MCP_SUBSTANCEDESIGNER_HOST"] == "localhost"
    assert calls[1][1]["DCC_MCP_SUBSTANCEDESIGNER_PORT"] == "9999"
    assert calls[1][1]["DCC_MCP_SUBSTANCEDESIGNER_LIVE"] == "1"


def test_live_verify_mutation_uses_live_bridge_env() -> None:
    module = _load_live_verify()
    calls: list[tuple[list[str], dict[str, str]]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[object]:
        calls.append((command, kwargs["env"]))
        return subprocess.CompletedProcess(command, 0)

    assert module.main(["--mutation"], runner=runner) == 0

    assert len(calls) == 3
    assert calls[2][0][-4:] == ["tests/test_live_mutation.py", "-m", "integration", "-v"]
    assert calls[2][1]["DCC_MCP_SUBSTANCEDESIGNER_LIVE"] == "1"
    assert "DCC_MCP_SUBSTANCEDESIGNER_MUTATION" not in calls[2][1]


def test_live_verify_stops_after_bridge_failure() -> None:
    module = _load_live_verify()
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[object]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1)

    assert module.main([], runner=runner) == 1

    assert len(calls) == 1
