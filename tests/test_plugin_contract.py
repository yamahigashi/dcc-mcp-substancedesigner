"""Contract tests between the adapter bridge and the Substance Designer plugin."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TypeAlias, cast

from dcc_mcp_substancedesigner.bridge import DEFAULT_SD_BRIDGE_PORT, HEADER_SIZE, MAX_MESSAGE_BYTES

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = REPO_ROOT / "plugin" / "__init__.py"
COMMAND_HANDLER_PATH = REPO_ROOT / "plugin" / "commands" / "command_handler.py"
NODE_INSPECTION_COMMAND_PATH = REPO_ROOT / "plugin" / "commands" / "node_command_query_mixin.py"
NODE_NESTED_COMMAND_PATH = REPO_ROOT / "plugin" / "commands" / "node_command_nested_mixin.py"
PLUGIN_CONSTANTS_PATH = REPO_ROOT / "plugin" / "plugin_constants.py"
BRIDGE_PROTOCOL_PATH = REPO_ROOT / "plugin" / "bridge" / "bridge_protocol.py"
BRIDGE_SERVER_PATH = REPO_ROOT / "plugin" / "bridge" / "bridge_server.py"
PYTHON_EXECUTION_PATH = REPO_ROOT / "plugin" / "python_execution" / "execution.py"

LiteralValue: TypeAlias = None | bool | int | float | str | list["LiteralValue"] | tuple["LiteralValue", ...]


def test_plugin_protocol_constants_match_adapter_bridge() -> None:
    """Verify plugin protocol constants match the adapter bridge contract."""
    plugin_constants = _plugin_constants()
    protocol_constants = _bridge_protocol_constants()

    assert plugin_constants["DEFAULT_PORTS"] == [DEFAULT_SD_BRIDGE_PORT]
    assert protocol_constants["HEADER_SIZE"] == HEADER_SIZE
    assert protocol_constants["MAX_MSG_SIZE"] == MAX_MESSAGE_BYTES


def test_plugin_bridge_does_not_convert_missing_command_results_to_success() -> None:
    """Verify missing command results remain bridge protocol errors."""
    server_source = BRIDGE_SERVER_PATH.read_text(encoding="utf-8")

    assert "raise RuntimeError(\"Command '{}' returned no result.\".format(cmd_type))" in server_source
    assert 'return {"status": "success", "result": result}' in server_source
    assert "result if result is not None else {}" not in server_source


def test_plugin_bridge_listens_on_ipv4_loopback() -> None:
    """Verify the host bridge binds the same loopback address used by adapter clients."""
    server_source = BRIDGE_SERVER_PATH.read_text(encoding="utf-8")

    assert 'self.host = "127.0.0.1"' in server_source
    assert 'self.host = "localhost"' not in server_source


def test_plugin_bridge_dispatches_clients_outside_accept_loop() -> None:
    """Verify one idle client cannot block accepting later bridge connections."""
    server_source = BRIDGE_SERVER_PATH.read_text(encoding="utf-8")

    assert "threading.Thread(" in server_source
    assert "target=self._handle_client" in server_source
    assert 'name="SD-MCP-Client-' in server_source
    assert "client_thread.start()" in server_source


def test_plugin_preview_serialization_tolerates_substance_api_value_errors() -> None:
    """Verify preview serialization is isolated and tolerant of host API value errors."""
    inspection_command_source = NODE_INSPECTION_COMMAND_PATH.read_text(encoding="utf-8")
    nested_command_source = NODE_NESTED_COMMAND_PATH.read_text(encoding="utf-8")
    preview_render_io_source = (REPO_ROOT / "plugin" / "preview" / "preview_render.py").read_text(encoding="utf-8")
    serialization_source = (REPO_ROOT / "plugin" / "sd_serialization.py").read_text(encoding="utf-8")

    assert "serialize_sd_value" in inspection_command_source
    assert "serialize_sd_value" in nested_command_source
    assert "def serialize_sd_value(value: ReprFallback | None) -> JsonValue:" in serialization_source
    assert "except BaseException:" in serialization_source
    assert "Node preview PNG was not created" in preview_render_io_source


def test_plugin_node_preview_does_not_mutate_graph_output_size() -> None:
    """Verify preview rendering captures at graph resolution and resizes PNG output."""
    preview_render_source = (REPO_ROOT / "plugin" / "preview" / "preview_render.py").read_text(encoding="utf-8")
    preview_selection_source = (REPO_ROOT / "plugin" / "preview" / "preview_outputs.py").read_text(encoding="utf-8")

    hash_index = preview_render_source.index("parameters_hash = hash_node_preview(")
    compute_index = preview_render_source.index("render_preview_image(")

    assert hash_index < compute_index
    assert "set_graph_output_size_value" not in preview_render_source
    assert "get_graph_output_size_value" not in preview_render_source
    assert "restore_output_size" not in preview_render_source
    assert "require_texture_output_property(node, output_prop)" in preview_render_source
    assert "graph.compute()" in (REPO_ROOT / "plugin" / "preview" / "preview_render.py").read_text(encoding="utf-8")
    assert "normalize_preview_image_size(image_path, size, size, qt_binding)" in preview_render_source
    assert (
        "texture_outputs = [prop for prop in outputs if is_texture_output_property(prop)]" in preview_selection_source
    )
    assert '"texture" in lowered or "bitmap" in lowered or "image" in lowered' in preview_selection_source


def test_plugin_node_preview_saves_sd_value_texture_payloads() -> None:
    """Verify preview rendering saves texture-like SDValue payloads."""
    preview_render_io_source = (REPO_ROOT / "plugin" / "preview" / "preview_render.py").read_text(encoding="utf-8")
    preview_texture_source = (REPO_ROOT / "plugin" / "preview" / "preview_outputs.py").read_text(encoding="utf-8")

    assert "save_node_preview_texture(value, image_path, node_id, output_id)" in preview_render_io_source
    assert "raw = cast(ValueContainer, value).get()" in preview_texture_source
    assert 'for method_name in ("save", "saveAs"):' in preview_texture_source
    assert "did not expose a saveable texture" in preview_texture_source


def test_plugin_node_preview_uses_temporary_output_fallback_and_resizes_png() -> None:
    """Verify preview rendering can fall back to temporary output nodes."""
    preview_render_io_source = (REPO_ROOT / "plugin" / "preview" / "preview_render.py").read_text(encoding="utf-8")
    preview_temporary_source = (REPO_ROOT / "plugin" / "preview" / "preview_outputs.py").read_text(encoding="utf-8")
    preview_outputs_source = (REPO_ROOT / "plugin" / "preview" / "preview_outputs.py").read_text(encoding="utf-8")

    assert "save_node_preview_via_temporary_output(graph, node, output_id, image_path)" in preview_render_io_source
    assert "create_temporary_output_node(graph, node, output_id)" in preview_temporary_source
    assert 'graph.newNode("sbs::compositing::output")' in preview_temporary_source
    assert 'node.newPropertyConnectionFromId(output_id, temp_node, "inputNodeOutput")' in preview_temporary_source
    assert "graph.deleteNode(temp_node)" in preview_temporary_source
    assert "normalize_preview_image_size(image_path, size, size, qt_binding)" in preview_render_io_source
    assert 'scaled.save(image_path, "PNG")' in preview_outputs_source


def test_plugin_exposes_execute_python_with_result_contract() -> None:
    """Verify execute_python is public and execute_code remains removed."""
    command_handler_source = COMMAND_HANDLER_PATH.read_text(encoding="utf-8")
    catalog_source = (REPO_ROOT / "plugin" / "commands" / "command_catalog.py").read_text(encoding="utf-8")
    python_execution_source = PYTHON_EXECUTION_PATH.read_text(encoding="utf-8")

    assert '"execute_python"' in catalog_source
    assert "for command_name in PLUGIN_COMMANDS" in command_handler_source
    assert "def execute_python(self, code: str, strict_json: bool = False) -> JsonMap:" in command_handler_source
    assert "return execute_python_code(sd, code, strict_json)" in command_handler_source
    assert '"result": {},' in python_execution_source
    assert 'exec(compile(code, "<mcp_execute_python>", "exec"), namespace)' in python_execution_source
    assert '"execute_code":' not in command_handler_source
    assert "def execute_code(" not in command_handler_source


def _plugin_constants() -> dict[str, LiteralValue]:
    """Read plugin constants from the host plugin source."""
    tree = ast.parse(PLUGIN_CONSTANTS_PATH.read_text(encoding="utf-8"))
    constants: dict[str, LiteralValue] = {}
    wanted = {"DEFAULT_PORTS"}
    constants.update(_module_constants(tree, wanted))
    missing = wanted - constants.keys()
    assert missing == set()
    return constants


def _bridge_protocol_constants() -> dict[str, LiteralValue]:
    """Read protocol constants from the host bridge source."""
    tree = ast.parse(BRIDGE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    constants: dict[str, LiteralValue] = {}
    wanted = {"HEADER_SIZE", "MAX_MSG_SIZE"}
    constants.update(_module_constants(tree, wanted))
    missing = wanted - constants.keys()
    assert missing == set()
    return constants


def _literal_value(node: ast.AST) -> LiteralValue:
    """Evaluate a supported AST literal constant expression."""
    if isinstance(node, ast.Constant):
        return cast(LiteralValue, node.value)
    if isinstance(node, ast.List):
        return [_literal_value(item) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal_value(item) for item in node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left = _literal_value(node.left)
        right = _literal_value(node.right)
        if isinstance(left, int) and isinstance(right, int):
            return left * right
    raise AssertionError(f"Unsupported plugin constant expression: {ast.dump(node)}")


def _module_constants(tree: ast.Module, wanted: set[str]) -> dict[str, LiteralValue]:
    """Collect selected module constants from an AST."""
    constants: dict[str, LiteralValue] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    constants[target.id] = _literal_value(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in wanted:
            assert node.value is not None
            constants[node.target.id] = _literal_value(node.value)
    return constants
