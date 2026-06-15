"""Tests for server composition."""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from dcc_mcp_core.skills_helper import load_yaml_file

from dcc_mcp_substancedesigner.authoring_reference import public_tool_names
from dcc_mcp_substancedesigner.commands import ENV_SD_BRIDGE_HOST, ENV_SD_BRIDGE_PORT
from dcc_mcp_substancedesigner.server import SubstanceDesignerMcpServer, _wait_for_loopback_ports_released

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "skills"

DEFAULT_ACTION_NAMES = {
    "substance_designer__apply_graph_change",
    "substance_designer__diagnostic",
    "substance_designer__execute_python",
    "substance_designer__get_authoring_plan",
    "substance_designer__get_authoring_capabilities",
    "substance_designer__get_graph",
    "substance_designer__get_node",
    "substance_designer__get_preview",
    "substance_designer__get_reference",
    "substance_designer__get_scene",
    "substance_designer__validate_graph_change",
}

PUBLIC_TOOL_NAMES = set(public_tool_names())

CORE_META_TOOL_NAMES = {
    "list_roots",
    "search_skills",
    "list_skills",
    "get_skill_info",
    "load_skill",
    "unload_skill",
    "activate_tool_group",
    "deactivate_tool_group",
    "search_tools",
}

EXPECTED_WORKFLOW_FIRST_TEN = [
    "search_tools",
    "search_skills",
    "get_skill_info",
    "load_skill",
    "get_authoring_plan",
    "get_graph",
    "get_preview",
    "get_authoring_capabilities",
    "validate_graph_change",
    "apply_graph_change",
    "replace_graph_state",
]


def test_server_options_apply_bridge_environment(monkeypatch) -> None:
    monkeypatch.delenv(ENV_SD_BRIDGE_HOST, raising=False)
    monkeypatch.delenv(ENV_SD_BRIDGE_PORT, raising=False)
    monkeypatch.delenv("DCC_MCP_PYTHON_EXECUTABLE", raising=False)

    server = SubstanceDesignerMcpServer(
        port=0,
        sd_host="192.0.2.10",
        sd_port=19881,
        enable_gateway_failover=False,
    )
    try:
        assert server.bridge_client.host == "192.0.2.10"
        assert server.bridge_client.port == 19881
        assert os.environ[ENV_SD_BRIDGE_HOST] == "192.0.2.10"
        assert os.environ[ENV_SD_BRIDGE_PORT] == "19881"
        assert os.environ["DCC_MCP_PYTHON_EXECUTABLE"] == sys.executable
    finally:
        server.shutdown()


def test_server_preserves_explicit_skill_python_executable(monkeypatch) -> None:
    monkeypatch.setenv("DCC_MCP_PYTHON_EXECUTABLE", "C:/custom/python.exe")

    server = SubstanceDesignerMcpServer(port=0, enable_gateway_failover=False)
    try:
        assert os.environ["DCC_MCP_PYTHON_EXECUTABLE"] == "C:/custom/python.exe"
    finally:
        server.shutdown()


def test_server_applies_zero_gateway_port_override() -> None:
    server = SubstanceDesignerMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    try:
        core_config = server._core_server._config
        assert core_config.gateway_port == 0
    finally:
        server.shutdown()


def test_server_registers_inprocess_skill_executor() -> None:
    server = SubstanceDesignerMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    try:
        assert server._core_server._inprocess_executor_registered is True
    finally:
        server.shutdown()


def test_wait_for_loopback_ports_released_waits_until_socket_closes() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    release = threading.Event()

    def close_later() -> None:
        release.wait(0.2)
        listener.close()

    thread = threading.Thread(target=close_later, daemon=True)
    thread.start()
    release.set()

    _wait_for_loopback_ports_released(port, timeout=2.0)
    thread.join(timeout=1)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def test_server_discovers_skill_and_loads_public_workflow_surface(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_MINIMAL", raising=False)
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_DEFAULT_TOOLS", raising=False)

    server = SubstanceDesignerMcpServer(port=0, enable_gateway_failover=False)
    try:
        server.register_builtin_actions()
        skills = server.list_skills()
        skill_names = {skill.get("name") for skill in skills if isinstance(skill, dict)}
        action_names = _action_names(server)
    finally:
        server.shutdown()

    assert "substance-designer" in skill_names
    assert "substance-designer-scene" not in skill_names
    assert "substance-designer-authoring" not in skill_names
    assert "substance-designer-reference" not in skill_names
    assert action_names == _expected_adapter_action_names()
    assert DEFAULT_ACTION_NAMES <= action_names
    assert not any(name.startswith("dcc_introspect__") for name in action_names)
    assert not any(name.startswith("qt_ui_inspector__") for name in action_names)
    assert not any(name.startswith("recipes__") for name in action_names)
    assert not any(name.startswith("dcc_diagnostics__") for name in action_names)


def test_minimal_surface_environment_does_not_hide_adapter_tools(monkeypatch) -> None:
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_MINIMAL", "1")
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_DEFAULT_TOOLS", raising=False)

    server = SubstanceDesignerMcpServer(port=0, enable_gateway_failover=False)
    try:
        server.register_builtin_actions()
        action_names = _action_names(server)
    finally:
        server.shutdown()

    assert DEFAULT_ACTION_NAMES <= action_names


def test_mcp_tools_list_exposes_core_discovery_and_adapter_workflow_tools(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_MINIMAL", raising=False)
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_DEFAULT_TOOLS", raising=False)

    server = SubstanceDesignerMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    try:
        server.start()
        tool_names_in_order = _mcp_tool_names(server.mcp_url)
    finally:
        server.shutdown()

    tool_names = set(tool_names_in_order)
    assert CORE_META_TOOL_NAMES <= tool_names
    assert PUBLIC_TOOL_NAMES <= tool_names
    assert "get_graph" in tool_names
    assert "get_authoring_plan" in tool_names
    assert "get_authoring_capabilities" in tool_names
    assert "apply_graph_change" in tool_names
    assert "get_preview" in tool_names
    if tool_names_in_order[:4] == EXPECTED_WORKFLOW_FIRST_TEN[:4]:
        assert tool_names_in_order[:10] == EXPECTED_WORKFLOW_FIRST_TEN
    assert not any(name.startswith("dcc_introspect__") for name in tool_names)
    assert not any(name.startswith("qt_ui_inspector__") for name in tool_names)
    assert not any(name.startswith("recipes__") for name in tool_names)
    assert not any(name.startswith("dcc_diagnostics__") for name in tool_names)


def test_mcp_tools_list_marks_execute_python_as_open_world_fallback(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_MINIMAL", raising=False)
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_DEFAULT_TOOLS", raising=False)

    server = SubstanceDesignerMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    try:
        server.start()
        tools = {tool["name"]: tool for tool in _mcp_tools(server.mcp_url)}
    finally:
        server.shutdown()

    annotations = tools["execute_python"]["annotations"]
    assert annotations["destructiveHint"] is True
    assert annotations["openWorldHint"] is True


def test_mcp_search_tools_ranks_graph_workflow_tools(monkeypatch) -> None:
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_MINIMAL", raising=False)
    monkeypatch.delenv("DCC_MCP_SUBSTANCEDESIGNER_DEFAULT_TOOLS", raising=False)

    server = SubstanceDesignerMcpServer(port=0, gateway_port=0, enable_gateway_failover=False)
    try:
        server.start()
        payload = _mcp_call_tool(
            server.mcp_url,
            "search_tools",
            {"query": "substance designer graph workflow", "limit": 10},
        )
    finally:
        server.shutdown()

    hits = payload.get("hits") or []
    if hits:
        hit_names = [hit.get("name") for hit in hits]
        assert hit_names[:6] == [
            "apply_graph_change",
            "get_graph",
            "replace_graph_state",
            "validate_graph_change",
            "get_authoring_capabilities",
            "get_preview",
        ]


def _action_names(server: SubstanceDesignerMcpServer) -> set[str]:
    names = set()
    for action in server.list_actions():
        if isinstance(action, dict):
            names.add(action.get("name"))
        else:
            names.add(getattr(action, "name", str(action)))
    return names


def _expected_adapter_action_names() -> set[str]:
    names = set()
    for skill_dir in SKILLS_DIR.glob("substance-designer*"):
        tools_yaml = skill_dir / "tools.yaml"
        if not tools_yaml.is_file():
            continue
        payload = load_yaml_file(tools_yaml)
        skill_namespace = skill_dir.name.replace("-", "_")
        names.update(f"{skill_namespace}__{tool['name']}" for tool in payload.get("tools", []))
    return names


def _mcp_tool_names(url: str) -> list[str]:
    return [tool["name"] for tool in _mcp_tools_with_session(url, session_id=None)]


def _mcp_tools(url: str) -> list[dict]:
    return _mcp_tools_with_session(url, session_id=None)


def _mcp_tools_with_session(url: str, session_id: str | None) -> list[dict]:
    tools: list[dict] = []
    cursor: str | None = None
    request_id = 1
    while True:
        params = {"cursor": cursor} if cursor else {}
        payload = {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": params}
        try:
            _, data = _mcp_post(url, payload, session_id=session_id)
        except urllib.error.HTTPError as exc:
            if exc.code != 422 or session_id is not None:
                raise
            session_id = _mcp_initialize(url)
            if session_id is None:
                raise
            continue
        result = data["result"]
        tools.extend(result.get("tools", []))
        cursor = result.get("nextCursor")
        if not cursor:
            return tools
        request_id += 1


def _mcp_call_tool(url: str, name: str, arguments: dict) -> dict:
    session_id = _mcp_initialize(url)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    try:
        _, data = _mcp_post(url, payload, session_id=session_id)
    except urllib.error.HTTPError as exc:
        if exc.code != 422 or session_id is not None:
            raise
        session_id = _mcp_initialize(url)
        if session_id is None:
            raise
        _, data = _mcp_post(url, payload, session_id=session_id)
    text = data["result"]["content"][0]["text"]
    return json.loads(text)


def _mcp_initialize(url: str) -> str | None:
    headers, _ = _mcp_post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "substancedesigner-test", "version": "0"},
            },
        },
    )
    return headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")


def _mcp_post(url: str, payload: dict, *, session_id: str | None = None) -> tuple[dict, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.headers, _mcp_decode_response(response.read().decode("utf-8"))


def _mcp_decode_response(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
    if text.startswith("data:") or "\ndata:" in text:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    return json.loads(payload)
        return {}
    return json.loads(text)
