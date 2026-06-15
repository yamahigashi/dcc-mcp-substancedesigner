"""Tests for skill script entry points against a fake bridge."""

from __future__ import annotations

import importlib.util
import json
import socket
import struct
import sys
import threading
from pathlib import Path
from typing import Any, Dict

from dcc_mcp_substancedesigner.commands import ENV_SD_BRIDGE_PORT
from dcc_mcp_substancedesigner.server import _run_substance_skill_script

SKILL_SCRIPT_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "dcc_mcp_substancedesigner"
    / "skills"
    / "substance-designer"
    / "scripts"
)


def test_get_scene_skill_uses_environment_bridge(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "sd_version": "16.0.0",
                "plugin_version": "3.3.0",
                "current_graph": "GraphA",
                "current_graph_node_count": 1,
                "packages": [{"file_path": "E:/mat/test.sbs", "graphs": []}],
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("get_scene.py")
    result = module.main()
    thread.join(timeout=2)

    assert result["success"] is True
    assert result["context"]["application"]["version"] == "16.0.0"
    assert result["context"]["package_count"] == 1


def test_get_preview_skill_uses_environment_bridge(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "image_path": "E:/tmp/preview.png",
                "width": 256,
                "height": 256,
                "graph_id": "GraphA",
                "graph_identifier": "GraphA",
                "node_id": "node_1",
                "node_output_id": "unique_filter_output",
                "channel": "rgba",
                "resolution": "small",
                "render_ms": 184,
                "cached": False,
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("get_preview.py")
    result = module.main(node_id="node_1")
    thread.join(timeout=2)

    assert result["success"] is True
    assert result["context"]["operation"] == "get_preview"
    assert result["context"]["result"]["image_path"] == "E:/tmp/preview.png"


def test_get_preview_skill_accepts_inprocess_params(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "image_path": "E:/tmp/preview.png",
                "width": 256,
                "height": 256,
                "graph_id": "GraphA",
                "graph_identifier": "GraphA",
                "node_id": "node_1",
                "node_output_id": "unique_filter_output",
                "channel": "rgba",
                "resolution": "small",
                "render_ms": 184,
                "cached": False,
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    result = _run_substance_skill_script(str(SKILL_SCRIPT_DIR / "get_preview.py"), {"node_id": "node_1"})
    thread.join(timeout=2)

    assert result["success"] is True
    assert result["context"]["operation"] == "get_preview"
    assert result["context"]["result"]["node_id"] == "node_1"


def test_get_preview_skill_reports_node_dimensions_as_input_error() -> None:
    module = _load_skill_script("get_preview.py")

    result = module.main(node_id="node_1", width=640)

    assert result["success"] is False
    assert result["message"] == "Invalid Substance Designer tool input"
    assert "3D View" in result["error"]
    assert "main() missing" not in result["error"]


def test_get_node_skill_reports_graph_lookup_hint_for_node_not_found(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "error",
            "message": "Node '1573191775' not found in graph ''.",
            "details": {
                "node_id": "1573191775",
                "requested_graph_identifier": None,
                "resolved_graph_identifier": "",
                "current_graph": "Substance_graph",
                "candidate_graphs": ["Substance_graph"],
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("get_node.py")
    result = module.main(node_id="1573191775")
    thread.join(timeout=2)

    assert result["success"] is False
    assert result["message"] == "Substance Designer node lookup failed"
    assert "Retry with graph_identifier" in result["context"]["possible_solutions"][0]
    assert result["context"]["bridge_error_details"]["current_graph"] == "Substance_graph"


def test_apply_graph_change_skill_uses_environment_bridge(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "status": "applied",
                "nodes_created": 1,
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("apply_graph_change.py")
    result = module.main(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change={
            "nodes": [{"id": "value", "definition": "sbs::function::const_float1"}],
            "connections": [],
            "output": "value",
        },
    )
    thread.join(timeout=2)

    assert result["success"] is True
    assert result["context"]["operation"] == "apply_graph_change"
    assert result["context"]["result"]["applied"] is True


def test_apply_graph_change_skill_reports_rolled_back_failure(monkeypatch) -> None:
    class FailedCommands:
        def apply_graph_change(self, **_kwargs: object) -> dict[str, object]:
            return {
                "operation": "apply_graph_change",
                "result": {
                    "applied": False,
                    "rolled_back": True,
                    "error": "Property 'component' not found.",
                },
            }

    module = _load_skill_script("apply_graph_change.py")
    monkeypatch.setattr(module, "commands", lambda: FailedCommands())

    result = module.main(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={"nodes": []},
    )

    assert result["success"] is False
    assert result["message"] == "Graph change failed and was rolled back"
    assert result["context"]["result"]["applied"] is False
    assert result["context"]["result"]["rolled_back"] is True


def test_execute_python_skill_exposes_python_result_at_top_level(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "status": "ok",
                "executed": True,
                "result": {"answer": 42},
                "stdout": "hello\n",
                "stderr": "",
                "message": "",
                "traceback": "",
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("execute_python.py")
    result = module.main(code='print("hello"); result = {"answer": 42}')
    thread.join(timeout=2)

    assert result["success"] is True
    assert result["context"]["operation"] == "execute_python"
    assert result["context"]["python_result"] == {"answer": 42}
    assert result["context"]["stdout"] == "hello\n"


def test_get_reference_skill_reads_authoring_resource_without_bridge() -> None:
    module = _load_skill_script("get_reference.py")

    result = module.main(uri="substancedesigner://authoring/contracts/graph-change")

    assert result["success"] is True
    assert result["context"]["operation"] == "get_reference"
    assert result["context"]["kind"] == "authoring_contract"
    assert result["context"]["content"]["resource_kind"] == "authoring_contract"
    assert {
        "tool": "substance_designer__get_reference",
        "public_name": "get_reference",
        "args": {"uri": "substancedesigner://authoring/contracts/reference-first-policy"},
    } in result["context"]["next_tools"]


def test_get_reference_skill_rejects_non_authoring_uri() -> None:
    module = _load_skill_script("get_reference.py")

    result = module.main(uri="file:///tmp/function_atomic.json")

    assert result["success"] is False
    assert result["message"] == "Invalid Substance Designer tool input"
    assert "Unsupported Substance Designer authoring reference URI" in result["error"]


def test_workflow_skill_validation_error_does_not_contact_bridge() -> None:
    module = _load_skill_script("apply_graph_change.py")

    result = module.main(change={})

    assert result["success"] is False
    assert result["message"] == "Invalid Substance Designer tool input"
    assert "graph_ref" in result["error"]


def test_validate_graph_change_validation_error_does_not_contact_bridge() -> None:
    module = _load_skill_script("validate_graph_change.py")

    result = module.main(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "node_1",
            "owner_definition": "sbs::library::unknown",
            "property_id": "mystery_function",
        },
        change={},
    )

    assert result["success"] is True
    assert result["context"]["operation"] == "validate_graph_change"
    assert result["context"]["result"]["valid"] is False


def test_validate_graph_change_skill_exposes_namespaced_apply_next_tool() -> None:
    module = _load_skill_script("validate_graph_change.py")
    graph_ref = {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "pixel_1",
        "property_id": "perpixel",
    }
    normalized_graph_ref = {**graph_ref, "graph_type": "SDSBSFunctionGraph"}
    change = {
        "nodes": [{"id": "value", "definition": "sbs::function::const_float4"}],
        "connections": [],
        "output": "value",
    }

    result = module.main(
        graph_ref=graph_ref,
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change=change,
    )

    assert result["success"] is True
    assert {
        "tool": "substance_designer__apply_graph_change",
        "public_name": "apply_graph_change",
        "args": {
            "graph_ref": normalized_graph_ref,
            "context": result["context"]["result"]["graph_context"],
            "change": change,
        },
    } in result["context"]["next_tools"]


def test_execute_python_skill_reports_python_execution_error(monkeypatch) -> None:
    port, thread = _run_fake_bridge(
        {
            "status": "success",
            "result": {
                "status": "error",
                "executed": False,
                "result": None,
                "stdout": "",
                "stderr": "boom",
                "message": "Python execution failed",
                "traceback": "Traceback...",
            },
        }
    )
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, str(port))

    module = _load_skill_script("execute_python.py")
    result = module.main(code="raise RuntimeError('boom')")
    thread.join(timeout=2)

    assert result["success"] is False
    assert result["message"] == "Substance Designer Python execution failed"
    assert result["context"]["operation"] == "execute_python"
    assert result["context"]["ok"] is False


def _load_skill_script(filename: str):
    return _load_script(SKILL_SCRIPT_DIR, filename)


def _load_script(script_dir: Path, filename: str):
    sys.path.insert(0, str(script_dir))
    try:
        spec = importlib.util.spec_from_file_location("skill_under_test", script_dir / filename)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(script_dir))
        except ValueError:
            pass


def _run_fake_bridge(response: Dict[str, Any]) -> tuple[int, threading.Thread]:
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    def handle_once() -> None:
        conn, _addr = server_sock.accept()
        with conn:
            header = conn.recv(4)
            message_length = struct.unpack(">I", header)[0]
            conn.recv(message_length)
            response_bytes = json.dumps(response).encode("utf-8")
            conn.sendall(struct.pack(">I", len(response_bytes)) + response_bytes)
        server_sock.close()

    thread = threading.Thread(target=handle_once)
    thread.start()
    return port, thread
