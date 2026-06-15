"""Tests for plugin-side explicit Python execution helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXECUTION_PATH = REPO_ROOT / "plugin" / "python_execution" / "execution.py"


class FakeUiManager:
    """Fake Substance Designer UI manager for execution tests."""

    def __init__(self) -> None:
        """Create an empty UI manager call log."""
        self.opened: list[FakeGraph] = []

    def openResourceInEditor(self, graph: FakeGraph) -> None:
        """Record a graph open request."""
        self.opened.append(graph)


class FakeApplication:
    """Fake Substance Designer application for execution tests."""

    def __init__(self) -> None:
        """Create fake host managers."""
        self.ui_mgr = FakeUiManager()
        self.package_mgr = FakePackageManager()
        self.graph = FakeGraph()

    def getPackageMgr(self) -> FakePackageManager:
        """Return the fake package manager."""
        return self.package_mgr

    def getUIMgr(self) -> FakeUiManager:
        """Return the fake UI manager."""
        return self.ui_mgr


class FakeContext:
    """Fake Substance Designer context for execution tests."""

    def __init__(self) -> None:
        """Create a fake application."""
        self.app = FakeApplication()

    def getSDApplication(self) -> FakeApplication:
        """Return the fake application."""
        return self.app


class FakeSDModule:
    """Fake Substance Designer module for execution tests."""

    def __init__(self) -> None:
        """Create a fake host context."""
        self.context = FakeContext()

    def getContext(self) -> FakeContext:
        """Return the fake context."""
        return self.context


class FakePackageManager:
    """Fake package manager marker."""


class FakeGraph:
    """Fake graph marker."""

    def __repr__(self) -> str:
        """Return a stable diagnostic representation."""
        return "<FakeGraph>"


def test_execute_python_code_returns_stdout_and_result() -> None:
    module = _load_python_execution_module()

    result = module.execute_python_code(FakeSDModule(), 'print("hello"); result = {"answer": 42}')

    assert result["status"] == "ok"
    assert result["executed"] is True
    assert result["result"] == {"answer": 42}
    assert result["stdout"] == "hello\n"
    assert result["stderr"] == ""


def test_execute_python_code_exposes_open_in_editor_helper() -> None:
    module = _load_python_execution_module()
    sd_module = FakeSDModule()

    result = module.execute_python_code(
        sd_module, "graph = app.graph; open_in_editor(graph); result = {'opened': True}"
    )

    assert result["status"] == "ok"
    assert sd_module.context.app.ui_mgr.opened == [sd_module.context.app.graph]


def test_execute_python_code_serializes_non_json_results_when_allowed() -> None:
    module = _load_python_execution_module()

    result = module.execute_python_code(FakeSDModule(), "result = {'graph': app.graph}", strict_json=False)

    assert result["status"] == "ok"
    assert result["result"] == {"graph": "<FakeGraph>"}


def test_execute_python_code_reports_strict_json_errors() -> None:
    module = _load_python_execution_module()

    result = module.execute_python_code(FakeSDModule(), "result = {'graph': app.graph}", strict_json=True)

    assert result["status"] == "error"
    assert result["executed"] is False
    assert result["result"] is None
    assert "TypeError" in result["message"]
    assert "Traceback" in result["stderr"]


def _load_python_execution_module():
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    previous_package = sys.modules.get("plugin")
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.python_execution.execution",
        "plugin.python_execution.python_execution_types",
    ]:
        sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location("plugin.python_execution.execution", PYTHON_EXECUTION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules["plugin.python_execution.execution"] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        for module_name in [
            "plugin.python_execution.execution",
            "plugin.python_execution.python_execution_types",
        ]:
            sys.modules.pop(module_name, None)
        if previous_package is None:
            sys.modules.pop("plugin", None)
        else:
            sys.modules["plugin"] = previous_package
    return module
