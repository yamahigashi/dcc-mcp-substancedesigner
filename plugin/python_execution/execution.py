"""Execution entry point for trusted Python snippets."""

from __future__ import annotations

import io
import json
import traceback
from contextlib import redirect_stderr, redirect_stdout

from ..json_types import JsonValue
from .python_execution_types import (
    ExecutionResult,
    NamespaceValue,
    ReprFallback,
    SDApplication,
    SDModule,
)


def make_json_safe(value: ReprFallback) -> JsonValue:
    """Convert an arbitrary execution result into JSON-safe data."""
    try:
        json.dumps(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [make_json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): make_json_safe(item) for key, item in value.items()}
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def execution_namespace(sd_module: SDModule, app: SDApplication) -> dict[str, NamespaceValue]:
    """Return the trusted execution namespace for diagnostic Python snippets."""

    def open_in_editor_safe(graph: ReprFallback) -> None:
        """Open a graph in the editor while keeping diagnostics non-fatal."""
        try:
            app.getUIMgr().openResourceInEditor(graph)
        except Exception as exc:
            print("[MCP] open_in_editor warning: {}".format(exc))

    return {
        "sd": sd_module,
        "app": app,
        "pkg_mgr": app.getPackageMgr(),
        "ui_mgr": app.getUIMgr(),
        "open_in_editor": open_in_editor_safe,
        "result": {},
        "__name__": "__mcp_execute_python__",
    }


def execute_python_code(sd_module: SDModule, code: str, strict_json: bool = False) -> ExecutionResult:
    """Execute trusted Python code in a Substance Designer diagnostic namespace."""
    stdout_cap = io.StringIO()
    stderr_cap = io.StringIO()
    app = sd_module.getContext().getSDApplication()
    namespace: dict[str, NamespaceValue] = execution_namespace(sd_module, app)
    error: str | None = None
    tb = ""
    result: JsonValue = None
    try:
        with redirect_stdout(stdout_cap), redirect_stderr(stderr_cap):
            exec(compile(code, "<mcp_execute_python>", "exec"), namespace)
        raw_result = namespace.get("result", {})
        if strict_json:
            json.dumps(raw_result)
        result = make_json_safe(raw_result)
    except BaseException as exc:
        error = "{}: {}".format(type(exc).__name__, exc)
        tb = traceback.format_exc()
        stderr_cap.write(tb)

    return {
        "status": "ok" if error is None else "error",
        "executed": error is None,
        "result": result,
        "stdout": stdout_cap.getvalue(),
        "stderr": stderr_cap.getvalue(),
        "message": error or "",
        "traceback": tb,
    }
