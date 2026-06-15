"""Consistency tests for bundled MCP skills and plugin command coverage."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

from dcc_mcp_core.skills_helper import load_yaml_file

from dcc_mcp_substancedesigner.authoring_reference import public_tool_action_ids, public_tool_names

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "skills"

PUBLIC_TOOL_NAMES = set(public_tool_names())
INITIAL_TOOL_NAMES = [
    "get_scene",
    "get_graph",
    "get_node",
    "get_authoring_plan",
    "get_reference",
    "get_preview",
    "diagnostic",
    "execute_python",
]

REMOVED_TOOL_NAMES = {
    "ensure_library_package",
    "get_graph_summary",
    "get_node_label",
    "graph_snapshot",
    "get_library_nodes",
    "list_nodes",
    "list_node_definitions",
    "list_packages",
    "list_unused_nodes",
    "smart_connect",
    "trace_all_outputs",
    "validate_graph_outputs",
    "validate_required_inputs_bound",
    "connect_nodes",
    "create_node",
    "get_nested_graph",
    "plan_nested_graph_update",
    "apply_nested_graph_update",
    "set_graph_input",
    "set_parameter",
}

ALLOWED_TOOL_GROUPS = {"public"}
MAX_PUBLIC_TOOL_COUNT = 14

NON_EMPTY_STRING_PROPERTIES = {
    "get_graph": {"graph_identifier"},
    "get_node": {"node_id", "graph_identifier"},
    "execute_python": {"code"},
    "export_output": {"node_id", "file_path", "graph_identifier", "node_output_id"},
    "get_reference": {"uri"},
    "save_package": {"file_path", "package_path"},
}

NON_NEGATIVE_INTEGER_PROPERTIES = {
    "get_graph": {"node_limit"},
    "save_package": {"package_index"},
}

POSITIVE_INTEGER_PROPERTIES = {
    "get_preview": {"timeout_ms", "width", "height"},
}

POSITIVE_NUMBER_PROPERTIES = {}

NODE_ID_PROPERTIES = {
    "get_graph": {"owner_node_id"},
    "get_node": {"node_id"},
    "export_output": {"node_id"},
    "get_preview": {"node_id"},
}


def test_all_skill_tool_sources_exist() -> None:
    """Verify every skill tool entry points at an existing script."""
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            source_file = tool.get("source_file")
            assert source_file, f"{tools_yaml}: tool {tool.get('name')} has no source_file"
            assert (tools_yaml.parent / source_file).is_file(), f"{tools_yaml}: missing {source_file}"


def test_all_skill_tool_sources_import() -> None:
    """Verify every skill tool script can be imported with its local common module."""
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            script_path = tools_yaml.parent / tool["source_file"]
            _import_skill_script(script_path)


def test_all_skill_names_are_unique() -> None:
    """Verify bundled skill tool names are globally unique."""
    names = []
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        names.extend(tool["name"] for tool in payload.get("tools", []))

    assert len(names) == len(set(names))


def test_removed_tools_are_not_public() -> None:
    """Verify obsolete or ambiguous tools do not re-enter the MCP catalog."""
    names = set()
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        names.update(tool["name"] for tool in payload.get("tools", []))

    assert names.isdisjoint(REMOVED_TOOL_NAMES)


def test_skill_input_schema_matches_script_main_signature() -> None:
    """Verify tool input schemas align with script main signatures."""
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            script_path = tools_yaml.parent / tool["source_file"]
            schema_properties = set(tool.get("input_schema", {}).get("properties", {}).keys())
            main_parameters = _script_main_parameters(script_path)

            assert schema_properties == main_parameters, (
                f"{tools_yaml}: tool {tool['name']} schema/script mismatch: "
                f"schema={sorted(schema_properties)} main={sorted(main_parameters)}"
            )


def test_skill_required_inputs_have_required_script_parameters() -> None:
    """Verify required schema fields exist on script parameters.

    Script entry points keep Python defaults for required MCP fields so missing
    arguments can be reported as adapter validation errors instead of raw
    ``TypeError: main() missing ...`` handler failures.
    """
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            script_path = tools_yaml.parent / tool["source_file"]
            required_schema = set(tool.get("input_schema", {}).get("required", []))
            main_parameters = _script_main_parameters(script_path)

            assert required_schema <= main_parameters, (
                f"{tools_yaml}: tool {tool['name']} required fields missing from script: "
                f"schema={sorted(required_schema)} main={sorted(main_parameters)}"
            )


def test_required_skill_fields_are_not_python_required_parameters() -> None:
    """Verify missing tool inputs go through adapter validation, not Python TypeError."""
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            script_path = tools_yaml.parent / tool["source_file"]
            required_schema = set(tool.get("input_schema", {}).get("required", []))
            required_main = _script_required_main_parameters(script_path)

            assert required_schema.isdisjoint(required_main), (
                f"{tools_yaml}: tool {tool['name']} required fields must have script defaults: "
                f"schema={sorted(required_schema)} python_required={sorted(required_main)}"
            )


def test_plugin_handlers_match_adapter_owned_allowlist() -> None:
    """Verify plugin command methods match adapter-owned public command names."""
    plugin_commands = _plugin_command_catalog_names()
    plugin_methods = _plugin_command_handler_method_names()
    facade_commands = _facade_command_names()

    assert _plugin_handler_uses_command_catalog()
    assert plugin_commands <= plugin_methods
    assert plugin_commands == facade_commands


def test_execute_python_is_public_and_execute_code_is_removed() -> None:
    """Verify execute_python is public and legacy execute_code is absent."""
    plugin_commands = _plugin_command_catalog_names()
    facade_commands = _facade_command_names()
    tool_names = set()
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        tool_names.update(tool["name"] for tool in payload.get("tools", []))

    assert "execute_python" in plugin_commands
    assert "execute_python" in facade_commands
    assert "execute_python" in tool_names
    assert "execute_code" not in plugin_commands
    assert "execute_code" not in facade_commands
    assert "execute_code" not in tool_names


def test_substance_designer_skill_mentions_sdf_function_workflow_entry_rule() -> None:
    skill_text = (SKILLS_DIR / "substance-designer" / "SKILL.md").read_text(encoding="utf-8")

    assert "substancedesigner://authoring/workflows/sdf-function" in skill_text
    assert "3d_texture_sdf" in skill_text
    assert "SDF Function" in skill_text


def test_skill_groups_define_public_workflow_surface() -> None:
    """Verify the public workflow catalog stays focused and includes execute_python."""
    public_tools = []
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            group = tool.get("group")
            assert group in ALLOWED_TOOL_GROUPS, f"{tools_yaml}: {tool['name']} has invalid group {group!r}"
            if group == "public":
                public_tools.append(tool["name"])

    assert set(public_tools) == PUBLIC_TOOL_NAMES
    assert public_tools == list(public_tool_names())
    assert "execute_python" in public_tools


def test_public_tool_action_ids_are_derived_from_tools_yaml() -> None:
    """Avoid a second hard-coded public tool catalog in Python."""
    public_tools = []
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        public_tools.extend(tool["name"] for tool in payload.get("tools", []) if tool.get("group") == "public")

    assert list(public_tool_names()) == public_tools
    assert public_tool_action_ids() == {name: f"substance_designer__{name}" for name in public_tools}
    source = (REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "authoring_reference.py").read_text(encoding="utf-8")
    assert "PUBLIC_TOOL_ACTION_IDS" not in source


def test_public_workflow_catalog_orders_initial_exposure_before_later_phase_tools() -> None:
    """Keep capped client exposure focused on orientation before mutation and file operations."""
    public_tools = []
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        public_tools.extend(tool["name"] for tool in payload.get("tools", []) if tool.get("group") == "public")

    assert public_tools[: len(INITIAL_TOOL_NAMES)] == INITIAL_TOOL_NAMES
    assert public_tools.index("validate_graph_change") > public_tools.index("execute_python")
    assert public_tools.index("apply_graph_change") > public_tools.index("execute_python")
    assert public_tools.index("replace_graph_state") > public_tools.index("execute_python")
    assert public_tools.index("export_output") > public_tools.index("execute_python")
    assert public_tools.index("save_package") > public_tools.index("execute_python")
    assert "refresh_plugin" not in public_tools


def test_public_workflow_surface_stays_within_budget() -> None:
    """Verify the public callable workflow surface stays small for Codex exposure."""
    groups = {group: set() for group in ALLOWED_TOOL_GROUPS}
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            groups[tool["group"]].add(tool["name"])

    assert len(groups["public"]) <= MAX_PUBLIC_TOOL_COUNT


def test_skill_schemas_expose_adapter_validation_constraints() -> None:
    """Verify tool schemas expose important adapter validation constraints."""
    tools = _tool_schemas_by_name()

    for tool_name, property_names in NON_EMPTY_STRING_PROPERTIES.items():
        properties = tools[tool_name]["input_schema"].get("properties", {})
        for property_name in property_names:
            if property_name in properties:
                assert properties[property_name].get("minLength") == 1, f"{tool_name}.{property_name}"

    for tool_name, property_names in NON_NEGATIVE_INTEGER_PROPERTIES.items():
        properties = tools[tool_name]["input_schema"].get("properties", {})
        for property_name in property_names:
            assert properties[property_name].get("minimum") == 0, f"{tool_name}.{property_name}"

    for tool_name, property_names in POSITIVE_INTEGER_PROPERTIES.items():
        properties = tools[tool_name]["input_schema"].get("properties", {})
        for property_name in property_names:
            assert properties[property_name].get("minimum") == 1, f"{tool_name}.{property_name}"

    for tool_name, property_names in POSITIVE_NUMBER_PROPERTIES.items():
        properties = tools[tool_name]["input_schema"].get("properties", {})
        for property_name in property_names:
            assert properties[property_name].get("exclusiveMinimum") == 0, f"{tool_name}.{property_name}"

    for tool_name, property_names in NODE_ID_PROPERTIES.items():
        properties = tools[tool_name]["input_schema"].get("properties", {})
        for property_name in property_names:
            assert properties[property_name].get("type") == ["string", "integer"], f"{tool_name}.{property_name}"


def test_flexible_input_shapes_are_advertised() -> None:
    """Verify user-facing flexible input contracts stay discoverable."""
    tools = _tool_schemas_by_name()

    plan_schema = tools["get_authoring_plan"]["input_schema"]
    assert set(plan_schema["properties"]) == {"graph_ref", "context", "intent", "include_raw"}

    capabilities_schema = tools["get_authoring_capabilities"]["input_schema"]
    assert set(capabilities_schema["properties"]) == {"graph_ref", "context", "intent", "include_raw"}

    validate_schema = tools["validate_graph_change"]["input_schema"]
    assert validate_schema.get("required") == ["change"]

    apply_schema = tools["apply_graph_change"]["input_schema"]
    assert apply_schema.get("required") == ["graph_ref", "change"]
    assert "validated before mutation" in apply_schema["properties"]["change"]["description"]


def test_critical_workflow_tools_advertise_substance_designer_mcp_terms() -> None:
    """Keep tool-search metadata weighted toward typed graph workflows."""
    tools = _tool_schemas_by_name()

    for tool_name in {
        "get_graph",
        "get_node",
        "get_preview",
        "get_authoring_plan",
        "get_authoring_capabilities",
        "get_reference",
        "validate_graph_change",
        "apply_graph_change",
        "replace_graph_state",
    }:
        description = tools[tool_name]["description"]
        assert "Substance Designer MCP" in description, tool_name
        assert tools[tool_name].get("search_aliases"), tool_name


def test_workflow_tools_have_first_page_search_aliases() -> None:
    """Keep the first-page workflow path discoverable when core ranks by aliases."""
    tools = _tool_schemas_by_name()

    for tool_name in {
        "get_graph",
        "get_node",
        "get_preview",
        "get_authoring_plan",
        "get_reference",
        "validate_graph_change",
    }:
        aliases = tools[tool_name].get("search_aliases") or []
        assert any(
            "graph" in alias or "capabilities" in alias or "preview" in alias or "node" in alias or "reference" in alias
            for alias in aliases
        ), tool_name


def test_execute_python_is_marked_destructive() -> None:
    """Verify arbitrary host Python advertises its fallback execution risk."""
    tools = _tool_schemas_by_name()
    execute_python = tools["execute_python"]

    assert execute_python["read_only"] is False
    assert execute_python["destructive"] is True
    assert execute_python["idempotent"] is False
    assert execute_python["annotations"]["destructive_hint"] is True
    assert execute_python["annotations"]["open_world_hint"] is True


def test_apply_graph_change_is_marked_destructive() -> None:
    """GraphChange can remove or rewire host graph state."""
    tools = _tool_schemas_by_name()
    apply_graph_change = tools["apply_graph_change"]

    assert apply_graph_change["read_only"] is False
    assert apply_graph_change["destructive"] is True
    assert apply_graph_change["idempotent"] is False
    assert apply_graph_change["annotations"]["destructive_hint"] is True


def _plugin_command_catalog_names() -> set[str]:
    tree = ast.parse((REPO_ROOT / "plugin" / "commands" / "command_catalog.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "PLUGIN_COMMANDS":
                    return set(_literal_string_sequence(node.value))
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "PLUGIN_COMMANDS"
        ):
            assert node.value is not None
            return set(_literal_string_sequence(node.value))
    raise AssertionError("plugin/command_catalog.py: missing PLUGIN_COMMANDS")


def _plugin_handler_uses_command_catalog() -> bool:
    tree = ast.parse((REPO_ROOT / "plugin" / "commands" / "command_handler.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.DictComp):
            continue
        if isinstance(node.generators[0].iter, ast.Name) and node.generators[0].iter.id == "PLUGIN_COMMANDS":
            return True
    return False


def _plugin_command_handler_method_names() -> set[str]:
    method_names: set[str] = set()
    for relative_path, class_name in (
        ("command_connection_mixin.py", "DirectConnectCommandMixin"),
        ("command_connection_mixin.py", "DisconnectCommandMixin"),
        ("command_handler.py", "CommandHandler"),
        ("command_host_context.py", "CommandHostMixin"),
        ("command_misc_mixin.py", "CommandParameterMixin"),
        ("command_misc_mixin.py", "CommandUtilityMixin"),
        ("node_command_creation_mixin.py", "NodeCreationCommandMixin"),
        ("node_command_editing_mixin.py", "NodeEditingCommandMixin"),
        ("node_command_query_mixin.py", "NodeInspectionCommandMixin"),
        ("node_command_query_mixin.py", "NodeLibraryCommandMixin"),
        ("node_command_nested_mixin.py", "NodeNestedGraphCommandMixin"),
        ("node_command_query_mixin.py", "NodePreviewCommandMixin"),
        ("scene_command_query_mixin.py", "SceneDiagnosticCommandMixin"),
        ("scene_lifecycle_mixin.py", "SceneLifecycleCommandMixin"),
        ("scene_command_query_mixin.py", "SceneQueryCommandMixin"),
    ):
        tree = ast.parse((REPO_ROOT / "plugin" / "commands" / relative_path).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                method_names.update(item.name for item in node.body if isinstance(item, ast.FunctionDef))
                break
        else:
            raise AssertionError(f"plugin/commands/{relative_path}: missing {class_name}")
    if method_names:
        return method_names
    raise AssertionError("plugin/command_handler.py: missing CommandHandler")


def _facade_command_names() -> set[str]:
    tree = ast.parse((REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "commands.py").read_text(encoding="utf-8"))
    command_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "command" and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                command_names.add(first_arg.value)
    return command_names


def _tool_schemas_by_name() -> dict[str, dict]:
    tools = {}
    for tools_yaml in SKILLS_DIR.glob("*/tools.yaml"):
        payload = load_yaml_file(tools_yaml)
        for tool in payload.get("tools", []):
            tools[tool["name"]] = tool
    return tools


def _script_main_parameters(script_path: Path) -> set[str]:
    main_node = _script_main_node(script_path)
    return {arg.arg for arg in main_node.args.args}


def _script_required_main_parameters(script_path: Path) -> set[str]:
    main_node = _script_main_node(script_path)
    args = main_node.args.args
    default_count = len(main_node.args.defaults)
    required_count = len(args) - default_count
    return {arg.arg for arg in args[:required_count]}


def _script_main_node(script_path: Path) -> ast.FunctionDef:
    tree = ast.parse(script_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError(f"{script_path}: missing main()")


def _import_skill_script(script_path: Path) -> None:
    script_dir = str(script_path.parent)
    module_name = f"_skill_catalog_import_{script_path.parent.parent.name}_{script_path.stem}"
    sys.path.insert(0, script_dir)
    try:
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        assert spec is not None, f"{script_path}: cannot create import spec"
        assert spec.loader is not None, f"{script_path}: import spec has no loader"
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
        try:
            sys.path.remove(script_dir)
        except ValueError:
            pass


def _literal_string_sequence(node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        raise AssertionError(f"Expected a string sequence, got {ast.dump(node)}")
    values = []
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            raise AssertionError(f"Expected a string literal, got {ast.dump(item)}")
        values.append(item.value)
    return values
