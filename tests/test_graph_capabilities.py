"""Capability-driven graph editing tests."""

from __future__ import annotations

from dcc_mcp_substancedesigner.authoring_reference import (
    AUTHORING_PREFIX,
    FUNCTION_CONTRACTS_URI,
    FUNCTION_LIVE_PROBE_RESULTS_URI,
    FX_MAP_GRAPH_URI,
    SDF_FUNCTION_WORKFLOW_URI,
)
from dcc_mcp_substancedesigner.commands import SubstanceDesignerCommands
from dcc_mcp_substancedesigner.graph_capabilities import normalize_graph_ref


class FakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.fail_on_command: str | None = None
        self.fail_on_parameter: str | None = None
        self.fail_next_connect = False

    def command(self, command_type: str, params: dict | None = None) -> dict:
        self.calls.append((command_type, params or {}))
        if self.fail_on_command == command_type:
            raise RuntimeError(f"{command_type} failed")
        if command_type == "get_nested_graph_state":
            return {
                "target": {
                    "graph_identifier": params.get("graph_identifier"),
                    "node_id": params.get("node_id"),
                    "property": params.get("property_id"),
                },
                "graph_type": "SDSBSFunctionGraph",
                "nodes": [{"id": "value", "definition": "sbs::function::const_float1"}],
                "connections": [],
                "output": {"node": "value"},
            }
        if command_type == "apply_nested_graph_state":
            state = (params or {}).get("state", {})
            return {"status": "applied", "nodes_created": len(state.get("nodes", []))}
        if command_type == "get_graph_info":
            return {
                "identifier": (params or {}).get("graph_identifier") or "GraphA",
                "node_count": 2,
                "nodes": [
                    {"identifier": "old_source", "definition": "sbs::compositing::uniform", "connections": []},
                    {
                        "identifier": "1573185646",
                        "definition": "sbs::compositing::output",
                        "connections": [
                            {"input": "input1", "from_node": "old_source", "from_output": "unique_filter_output"}
                        ],
                    },
                ],
                "truncated": False,
                "node_limit": (params or {}).get("node_limit", 500),
            }
        if command_type == "get_node_info":
            return {
                "node_id": (params or {}).get("node_id"),
                "definition": "sbs::compositing::uniform",
                "position": [10, 20],
                "inputs": [
                    {"id": "outputcolor", "type": "ColorRGBA", "value": [0, 0, 0, 1]},
                    {"id": "colorswitch", "type": "bool", "value": True},
                ],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
            }
        if command_type == "create_node":
            definition = str((params or {}).get("definition_id", "node"))
            return {"status": "created", "node_id": f"{definition.rsplit(':', 1)[-1]}_created"}
        if command_type == "create_instance_node":
            resource_url = str((params or {}).get("resource_url", "node"))
            return {
                "status": "created",
                "node_id": f"{resource_url.rsplit('/', 1)[-1]}_created",
                "resource_url": resource_url,
            }
        if command_type == "set_parameter":
            if self.fail_on_parameter == (params or {}).get("parameter_id"):
                raise RuntimeError(f"Property '{self.fail_on_parameter}' not found")
            return {"status": "set", "node_id": (params or {}).get("node_id")}
        if command_type == "connect_nodes":
            if self.fail_next_connect:
                self.fail_next_connect = False
                raise RuntimeError("connect_nodes failed once")
            return {"status": "connected", "from_node_id": (params or {}).get("from_node_id")}
        if command_type == "disconnect_nodes":
            return {"status": "disconnected", "node_id": (params or {}).get("node_id")}
        if command_type == "delete_node":
            return {"status": "deleted", "node_id": (params or {}).get("node_id")}
        if command_type == "move_node":
            return {"status": "moved", "node_id": (params or {}).get("node_id")}
        return {}


class OwnerInferenceClient(FakeClient):
    def command(self, command_type: str, params: dict | None = None) -> dict:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info":
            return {
                "node_id": params["node_id"],
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::library::3d_viewer",
                "is_library_node": True,
                "position": [0, 0],
                "inputs": [{"id": "sdf_scene", "type": "float"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class InstanceOwnerInferenceClient(FakeClient):
    def command(self, command_type: str, params: dict | None = None) -> dict:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info":
            return {
                "node_id": params["node_id"],
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::sbscompgraph_instance",
                "is_library_node": True,
                "instance": {"resource_url": "pkg:///3d_viewer"},
                "position": [0, 0],
                "inputs": [{"id": "sdf_scene", "type": "function"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class ShapeSplatterInstanceOwnerInferenceClient(FakeClient):
    def command(self, command_type: str, params: dict | None = None) -> dict:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info":
            return {
                "node_id": params["node_id"],
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::sbscompgraph_instance",
                "is_library_node": True,
                "instance": {"resource_url": "pkg:///shape_splatter_v2"},
                "position": [0, 0],
                "inputs": [{"id": "shape_type", "type": "sbs::compositing::shape_type", "value": "2"}],
                "outputs": [{"id": "sdf_color"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


def test_authoring_capabilities_return_context_specific_toolbelt() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "shape_splatter_1",
            "owner_definition": "sbs::library::shape_splatter_v2",
            "property_id": "pattern_sdf_function",
        }
    )

    capabilities = result["result"]
    assert result["operation"] == "get_authoring_capabilities"
    assert capabilities["graph_context"]["graph_kind"] == "function_graph"
    assert capabilities["graph_context"]["contract"]["kind"] == "sdf_function"
    assert "sbs::function-library::3d_sdf_sphere" in capabilities["allowed_definitions"]
    assert "sbs::function::get_float1" in capabilities["allowed_definitions"]
    assert capabilities["output_contract"]["required"] is True
    assert "supported_changes" not in capabilities
    assert "ensure_node" in capabilities["apply_supported_changes"]
    assert capabilities["authoring_surfaces"][0]["operation_model"]["omitted_means"] == "preserve"
    assert FUNCTION_CONTRACTS_URI in capabilities["reference_uris"]
    assert FUNCTION_LIVE_PROBE_RESULTS_URI in capabilities["reference_uris"]
    assert f"{AUTHORING_PREFIX}/contracts/graph-change" in capabilities["reference_uris"]
    assert f"{AUTHORING_PREFIX}/contracts/operation-safety" in capabilities["reference_uris"]
    assert capabilities["apply_tool"] == "substance_designer__apply_graph_change"
    assert capabilities["workflow_profile"]["workflow_kind"] == "sdf_function"
    assert "3D Viewer.sdf_scene" in capabilities["workflow_profile"]["entrypoints"][0]
    assert any("3d_texture_sdf" in item for item in capabilities["workflow_profile"]["avoid"])
    assert "P" in capabilities["workflow_profile"]["mental_model"]
    assert f"{AUTHORING_PREFIX}/workflows/sdf-function" in capabilities["reference_uris"]
    assert {
        "tool": "substance_designer__validate_graph_change",
        "public_name": "validate_graph_change",
        "args": {
            "graph_ref": {
                "kind": "node_property_graph",
                "parent_graph": "GraphA",
                "owner_node_id": "shape_splatter_1",
                "owner_definition": "sbs::library::shape_splatter_v2",
                "property_id": "pattern_sdf_function",
                "graph_type": "SDSBSFunctionGraph",
            },
            "context": capabilities["graph_context"],
            "change": "<graph_change>",
        },
    } in capabilities["next_tools"]
    assert {
        "tool": "substance_designer__replace_graph_state",
        "public_name": "replace_graph_state",
        "args": {
            "graph_ref": {
                "kind": "node_property_graph",
                "parent_graph": "GraphA",
                "owner_node_id": "shape_splatter_1",
                "owner_definition": "sbs::library::shape_splatter_v2",
                "property_id": "pattern_sdf_function",
                "graph_type": "SDSBSFunctionGraph",
            },
            "state": "<complete_graph_state>",
            "expected_current_hash": "<state_hash_from_get_graph>",
        },
    } in capabilities["next_tools"]


def test_package_graph_sdf_intent_returns_workflow_suggestion_before_node_choice() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        intent="sdf",
    )

    capabilities = result["result"]
    assert capabilities["graph_context"]["graph_kind"] == "substance_graph"
    assert capabilities["workflow_suggestions"][0]["workflow_kind"] == "sdf_function"
    assert capabilities["workflow_suggestions"][0]["workflow_uri"] == SDF_FUNCTION_WORKFLOW_URI
    assert capabilities["workflow_suggestions"][0]["entry_nodes"] == [
        {
            "definition": "sbs::library::3d_viewer",
            "role": "sdf_function_debug_entrypoint",
            "property_id": "sdf_scene",
            "reference_uri": f"{AUTHORING_PREFIX}/node/library/3d_viewer",
        },
        {
            "definition": "sbs::library::shape_splatter_v2",
            "role": "sdf_function_production_consumer",
            "property_id": "pattern_sdf_function",
            "reference_uri": f"{AUTHORING_PREFIX}/node/library/shape_splatter_v2",
        },
    ]
    assert any("3d_texture_sdf" in item for item in capabilities["workflow_suggestions"][0]["avoid"])
    assert SDF_FUNCTION_WORKFLOW_URI in capabilities["reference_uris"]
    assert "apply_tool" not in capabilities
    assert all(tool["public_name"] not in {"validate_graph_change", "apply_graph_change"} for tool in capabilities["next_tools"])
    assert any(tool["public_name"] == "get_authoring_plan" for tool in capabilities["next_tools"])


def test_authoring_plan_for_package_sdf_intent_blocks_mutation_until_visual_unit() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_plan(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        intent="sdf",
    )

    plan = result["result"]
    assert result["operation"] == "get_authoring_plan"
    assert plan["phase"] == "plan_before_capabilities"
    assert plan["mutation_unlocked"] is False
    assert plan["next_unit"] == "sdf_function"
    assert SDF_FUNCTION_WORKFLOW_URI in plan["workflow_refs"]
    assert [unit["unit"] for unit in plan["visual_units"]] == [
        "sdf_function",
        "shape_splatter",
        "fx_map",
        "material_composite",
    ]
    assert all(unit["preview_targets"] for unit in plan["visual_units"])
    assert all(tool["public_name"] not in {"validate_graph_change", "apply_graph_change"} for tool in plan["next_tools"])


def test_authoring_capabilities_infers_owner_definition_from_owner_node() -> None:
    fake = OwnerInferenceClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "property_id": "sdf_scene",
        }
    )

    capabilities = result["result"]
    assert capabilities["graph_ref"]["owner_definition"] == "sbs::library::3d_viewer"
    assert capabilities["graph_context"]["contract"]["kind"] == "sdf_function"
    assert capabilities["graph_context"]["confidence"] == "high"
    assert fake.calls[0] == ("get_node_info", {"node_id": "viewer_1", "graph_identifier": "GraphA"})


def test_authoring_capabilities_resolves_instance_owner_definition_from_resource_url() -> None:
    fake = InstanceOwnerInferenceClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_instance",
            "owner_definition": "sbs::compositing::sbscompgraph_instance",
            "property_id": "sdf_scene",
        }
    )

    capabilities = result["result"]
    assert capabilities["graph_ref"]["owner_definition"] == "sbs::library::3d_viewer"
    assert capabilities["graph_context"]["contract"]["kind"] == "sdf_function"


def test_authoring_capabilities_resolves_shape_splatter_instance_owner_definition() -> None:
    fake = ShapeSplatterInstanceOwnerInferenceClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "splatter_instance",
            "owner_definition": "sbs::compositing::sbscompgraph_instance",
            "property_id": "pattern_sdf_function",
        }
    )

    capabilities = result["result"]
    assert capabilities["graph_ref"]["owner_definition"] == "sbs::library::shape_splatter_v2"
    assert capabilities["graph_context"]["contract"]["kind"] == "sdf_function"


def test_sdf_authoring_capabilities_can_be_filtered_by_intent_family() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    graph_ref = {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "viewer_1",
        "owner_definition": "sbs::library::3d_viewer",
        "property_id": "sdf_scene",
    }

    primitive = commands.get_authoring_capabilities(graph_ref=graph_ref, intent="sdf primitive")["result"]
    material = commands.get_authoring_capabilities(graph_ref=graph_ref, intent="sdf material")["result"]

    assert "sbs::function-library::3d_sdf_sphere" in primitive["allowed_definitions"]
    assert "sbs::function-library::3d_sdf_op_union" not in primitive["allowed_definitions"]
    assert "sbs::function-library::set_color" not in primitive["allowed_definitions"]
    assert primitive["definition_filter"]["family"] == "primitive"
    assert "sbs::function-library::set_color" in material["allowed_definitions"]
    assert "sbs::function-library::set_roughness" in material["allowed_definitions"]
    assert "sbs::function-library::3d_sdf_sphere" not in material["allowed_definitions"]
    assert material["definition_filter"]["family"] == "material"


def test_get_graph_accepts_node_property_graph_ref() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        }
    )

    assert result["operation"] == "get_graph"
    assert result["graph_ref"]["kind"] == "node_property_graph"
    assert result["graph_context"]["graph_kind"] == "function_graph"
    assert result["graph_context"]["contract"]["kind"] == "pixel_processor"
    assert result["nodes"] == [{"id": "value", "definition": "sbs::function::const_float1"}]
    assert fake.calls == [
        (
            "get_nested_graph_state",
            {
                "node_id": "pixel_1",
                "property_id": "perpixel",
                "graph_identifier": "GraphA",
                "graph_type": "SDSBSFunctionGraph",
            },
        )
    ]


def test_normalize_graph_ref_accepts_common_nested_graph_aliases() -> None:
    assert normalize_graph_ref(
        {
            "kind": "node_property_graph",
            "graph": "GraphA",
            "node_id": "viewer_1",
            "property": "sdf_scene",
        }
    ) == {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "viewer_1",
        "property_id": "sdf_scene",
        "graph_type": "SDSBSFunctionGraph",
    }

    assert normalize_graph_ref(
        {
            "kind": "fx_map_graph",
            "graph": "GraphA",
            "nodeId": "fx_1",
        }
    ) == {
        "kind": "fx_map_graph",
        "graph_identifier": "GraphA",
        "owner_node_id": "fx_1",
        "graph_type": "SDSBSFxMapGraph",
    }


def test_get_graph_full_enriches_node_property_graph_ports_from_definitions() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        detail_level="full",
    )

    assert result["nodes"][0]["id"] == "value"
    assert result["nodes"][0]["ports"]["outputs"]["unique_filter_output"]["type"] == "float"
    assert result["nodes"][0]["ports_evidence"]["source"] == "definition_registry"


def test_get_node_accepts_node_property_graph_ref_and_returns_internal_ports() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_node_detail(
        node_id="value",
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
    )

    assert result["node_id"] == "value"
    assert result["definition"] == "sbs::function::const_float1"
    assert result["ports"]["outputs"]["unique_filter_output"]["type"] == "float"
    assert result["graph_ref"]["kind"] == "node_property_graph"


def test_get_graph_filters_node_property_graph_by_node_ids() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        node_ids=["missing"],
    )

    assert result["nodes"] == []
    assert result["connections"] == []


def test_validate_graph_change_rejects_definition_outside_context() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change={
            "nodes": [{"id": "sphere", "definition": "sbs::function-library::3d_sdf_sphere"}],
            "connections": [],
            "output": "sphere",
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["preflight_only"] is True
    assert validation["requires_apply"] is False
    assert validation["errors"][0]["code"] == "definition_not_allowed_in_graph_context"
    assert validation["errors"][0]["path"] == "change.nodes[0].definition"


def test_validate_graph_change_checks_ports_and_required_output_contract() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change={
            "nodes": [
                {"id": "source", "definition": "sbs::function::const_float1"},
                {"id": "swizzle", "definition": "sbs::function::swizzle1"},
            ],
            "connections": [
                {"from": "source", "from_output": "missing_output", "to": "swizzle", "to_input": "vector"},
                {"from": "source", "from_output": "unique_filter_output", "to": "swizzle", "to_input": "missing_input"},
            ],
        },
    )

    errors = result["result"]["errors"]
    assert {error["code"] for error in errors} == {
        "source_port_not_allowed",
        "target_port_not_allowed",
    }
    assert result["result"]["valid"] is False
    assert result["result"]["preflight_only"] is True
    assert result["result"]["requires_apply"] is False


def test_validate_graph_change_valid_result_points_to_apply_tool() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
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

    result = commands.validate_graph_change(
        graph_ref=graph_ref,
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change=change,
    )

    validation = result["result"]
    assert validation["valid"] is True
    assert validation["preflight_only"] is True
    assert validation["requires_apply"] is True
    assert validation["operation_plan"]["strategy"] == "patch_property_graph"
    assert validation["operation_plan"]["destructive"] is False
    assert validation["operation_plan"]["sets_output"] is True
    assert validation["operation_plan"]["removes_connections"] is False
    assert validation["operation_plan"]["preserves_unmentioned"] is True
    assert {
        "tool": "substance_designer__apply_graph_change",
        "public_name": "apply_graph_change",
        "args": {
            "graph_ref": normalized_graph_ref,
            "context": validation["graph_context"],
            "change": change,
        },
    } in validation["next_tools"]


def test_validate_graph_change_accepts_operations_parameter_patch_for_existing_fx_map_node() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx"},
        change={
            "operations": [
                {
                    "op": "set_parameter",
                    "node": "1573143990",
                    "parameter": "patternsize",
                    "value": [0.2, 0.2],
                    "value_type": "float2",
                }
            ]
        },
    )

    validation = result["result"]
    assert validation["valid"] is True
    assert validation["requires_apply"] is True
    assert "operations" in validation["change"]
    assert validation["operation_plan"]["strategy"] == "patch_fx_map_graph"
    assert validation["operation_plan"]["destructive"] is False


def test_validate_graph_change_rejects_fx_map_change_without_owner_node_id() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA"},
        change={"operations": [{"op": "set_parameter", "node": "paramset", "parameter": "amount", "value": 0.5}]},
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert {error["code"] for error in validation["errors"]} == {"missing_owner_node_id"}


def test_validate_graph_change_marks_explicit_remove_connection_destructive() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={"operations": [{"op": "remove_connection", "to": "sample", "to_input": "pos"}]},
    )

    strategy = result["result"]["operation_plan"]
    assert result["result"]["valid"] is True
    assert strategy["strategy"] == "patch_property_graph"
    assert strategy["destructive"] is True
    assert strategy["destructive_scope"] == "explicit_remove_connection"
    assert strategy["removes_connections"] is True


def test_validate_graph_change_rejects_package_ensure_node_without_definition() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        change={"operations": [{"op": "ensure_node", "id": "new_node"}]},
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert {error["code"] for error in validation["errors"]} == {"missing_definition"}


def test_validate_graph_change_rejects_mixed_operations_and_replace_state() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx"},
        change={
            "operations": [{"op": "set_parameter", "node": "n1", "parameter": "patternsize", "value": [0.2, 0.2]}],
            "nodes": [{"id": "n1", "definition": "sbs::fxmap::paramset"}],
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["errors"][0]["code"] == "mixed_graph_change_modes"


def test_validate_graph_change_rejects_non_object_operations() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx"},
        change={"operations": ["not-an-operation"]},
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["errors"][0]["code"] == "invalid_operation"
    assert validation["errors"][0]["path"] == "change.operations[0]"


def test_validate_graph_change_rejects_output_node_usages_list_before_apply() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {
                        "identifier": "basecolor",
                        "usages": ["baseColor"],
                    },
                }
            ],
            "connections": [],
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["requires_apply"] is False
    assert validation["errors"][0]["code"] == "invalid_output_usage_value"
    assert validation["errors"][0]["path"] == "change.nodes[0].parameters.usages"


def test_validate_graph_change_rejects_ambiguous_output_usage_aliases() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {
                        "usage": "baseColor",
                        "usages": "normal",
                    },
                }
            ],
            "connections": [],
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["errors"][0]["code"] == "ambiguous_output_usage_parameter"


def test_validate_graph_change_accepts_output_usage_object_metadata() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {
                        "usage": {
                            "name": "baseColor",
                            "components": "RGBA",
                            "color_space": "Linear",
                        },
                    },
                }
            ],
            "connections": [],
        },
    )

    validation = result["result"]
    assert validation["valid"] is True


def test_validate_graph_change_rejects_orphan_output_usage_metadata() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {
                        "component": "RGBA",
                        "color_space": "Linear",
                    },
                }
            ],
            "connections": [],
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["errors"][0]["code"] == "orphan_output_usage_metadata"
    assert validation["errors"][0]["path"] == "change.nodes[0].parameters.component"
    assert validation["errors"][1]["code"] == "orphan_output_usage_metadata"
    assert validation["errors"][1]["path"] == "change.nodes[0].parameters.color_space"


def test_apply_graph_change_for_node_property_graph_uses_internal_property_graph_command() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        context={"graph_kind": "function_graph", "contract": {"kind": "parameter_function"}},
        change={
            "nodes": [{"id": "value", "definition": "sbs::function::const_float1", "parameters": {"value": 1.0}}],
            "connections": [],
            "output": "value",
        },
    )

    assert result["operation"] == "apply_graph_change"
    assert result["result"]["applied"] is True
    assert result["result"]["apply_strategy"] == "patch_property_graph"
    assert result["result"]["execution_trace"][0]["operation"] == "apply_nested_graph_patch"
    assert result["result"]["execution_trace"][0]["callable"] is False
    assert "internal_operation" not in result["result"]
    assert {
        "tool": "substance_designer__get_graph",
        "public_name": "get_graph",
        "args": {
            "graph_ref": {
                "kind": "node_property_graph",
                "parent_graph": "GraphA",
                "owner_node_id": "pixel_1",
                "property_id": "perpixel",
                "graph_type": "SDSBSFunctionGraph",
            }
        },
    } in result["result"]["next_tools"]
    assert fake.calls == [
        (
            "apply_nested_graph_patch",
            {
                "patch": {
                    "graph_kind": "node_property_graph",
                    "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
                    "graph_type": "SDSBSFunctionGraph",
                    "operations": [
                        {
                            "op": "ensure_node",
                            "id": "value",
                            "definition": "sbs::function::const_float1",
                            "parameters": {"value": 1.0},
                        },
                        {"op": "set_output", "node": "value"},
                    ],
                },
                "mode": "patch",
            },
        )
    ]


def test_apply_graph_change_lowers_property_graph_state_change_to_patch_by_default() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [{"id": "value", "definition": "sbs::function::const_float4", "parameters": {"value": 1.0}}],
            "connections": [],
            "output": "value",
        },
    )

    payload = result["result"]
    assert payload["validation"]["operation_plan"]["strategy"] == "patch_property_graph"
    assert payload["validation"]["operation_plan"]["destructive"] is False
    assert payload["validation"]["operation_plan"]["preserves_unmentioned"] is True
    assert payload["validation"]["operation_plan"]["sets_output"] is True
    assert payload["apply_strategy"] == "patch_property_graph"
    assert fake.calls[-1][1]["patch"]["operations"] == [
        {"op": "ensure_node", "id": "value", "definition": "sbs::function::const_float4", "parameters": {"value": 1.0}},
        {"op": "set_output", "node": "value"},
    ]
    assert fake.calls == [
        (
            "apply_nested_graph_patch",
            {
                "patch": {
                    "graph_kind": "node_property_graph",
                    "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
                    "graph_type": "SDSBSFunctionGraph",
                    "operations": [
                        {
                            "op": "ensure_node",
                            "id": "value",
                            "definition": "sbs::function::const_float4",
                            "parameters": {"value": 1.0},
                        },
                        {"op": "set_output", "node": "value"},
                    ],
                },
                "mode": "patch",
            },
        )
    ]


def test_apply_graph_change_patches_existing_property_graph_connection_without_redeclaring_nodes() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "connections": [
                {
                    "from": {"node": "existing_source", "output": "unique_filter_output"},
                    "to": {"node": "existing_target", "input": "input1"},
                }
            ]
        },
    )

    assert result["result"]["applied"] is True
    assert fake.calls[-1] == (
        "apply_nested_graph_patch",
        {
            "patch": {
                "graph_kind": "node_property_graph",
                "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
                "graph_type": "SDSBSFunctionGraph",
                "operations": [
                    {
                        "op": "ensure_connection",
                        "from": "existing_source",
                        "to": "existing_target",
                        "from_output": "unique_filter_output",
                        "to_input": "input1",
                    }
                ],
            },
            "mode": "patch",
        },
    )


def test_apply_graph_change_patches_existing_property_graph_output_without_redeclaring_node() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={"output": "existing_value"},
    )

    assert result["result"]["applied"] is True
    assert fake.calls[-1][1]["patch"]["operations"] == [{"op": "set_output", "node": "existing_value"}]


def test_apply_graph_change_patches_existing_fx_map_node_position_without_definition() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={"nodes": [{"id": "existing_paramset", "position": [10, 20]}]},
    )

    assert result["result"]["applied"] is True
    assert fake.calls[-1][1]["patch"]["operations"] == [
        {"op": "ensure_node", "id": "existing_paramset", "position": [10, 20]}
    ]


def test_apply_graph_change_rejects_full_property_graph_replace() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "replace_all": True,
            "nodes": [{"id": "value", "definition": "sbs::function::const_float4"}],
            "connections": [],
            "output": "value",
        },
    )

    assert result["result"]["applied"] is False
    assert result["result"]["validation"]["operation_plan"]["strategy"] == "replace_property_graph"
    assert result["result"]["validation"]["operation_plan"]["apply_ready"] is False
    assert result["result"]["errors"][0]["code"] == "full_replace_not_supported_by_apply_graph_change"
    assert fake.calls == []


def test_apply_graph_change_lowers_function_library_nodes_to_host_creation() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "owner_definition": "sbs::library::3d_viewer",
            "property_id": "sdf_scene",
        },
        context=None,
        change={
            "nodes": [{"id": "sphere", "definition": "sbs::function-library::3d_sdf_sphere"}],
            "connections": [],
            "output": {"node": "sphere", "output": "unique_filter_output"},
        },
    )

    sphere = fake.calls[-1][1]["patch"]["operations"][0]
    assert sphere["definition"] == "sbs::function-library::3d_sdf_sphere"
    assert sphere["host_creation"]["kind"] == "function_graph_resource_instance"
    assert sphere["host_creation"]["resource_url"].startswith("pkg:///3d_sdf_primitives/3d_sdf_sphere")
    assert sphere["host_creation"]["package_hint"]["path"] == "3d_functions.sbs"


def test_apply_graph_change_lowers_function_library_input_parameters_to_constants() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "owner_definition": "sbs::library::3d_viewer",
            "property_id": "sdf_scene",
        },
        context=None,
        change={
            "nodes": [
                {
                    "id": "rock",
                    "definition": "sbs::function-library::3d_sdf_rock",
                    "parameters": {"seed_input": 7, "scale": 0.35, "center_position": [0.1, 0.2, 0.3]},
                }
            ],
            "connections": [],
            "output": {"node": "rock", "output": "unique_filter_output"},
        },
    )

    operations = fake.calls[-1][1]["patch"]["operations"]
    assert operations[:4] == [
        {
            "op": "ensure_node",
            "id": "rock",
            "definition": "sbs::function-library::3d_sdf_rock",
            "host_creation": operations[0]["host_creation"],
        },
        {
            "op": "ensure_node",
            "id": "rock__seed_input",
            "definition": "sbs::function::const_float1",
            "parameters": {"__constant__": 7},
        },
        {
            "op": "ensure_node",
            "id": "rock__scale",
            "definition": "sbs::function::const_float1",
            "parameters": {"__constant__": 0.35},
        },
        {
            "op": "ensure_node",
            "id": "rock__center_position",
            "definition": "sbs::function::const_float3",
            "parameters": {"__constant__": [0.1, 0.2, 0.3]},
        },
    ]
    assert operations[4:7] == [
        {
            "op": "ensure_connection",
            "from": "rock__seed_input",
            "to": "rock",
            "from_output": "unique_filter_output",
            "to_input": "seed_input",
        },
        {
            "op": "ensure_connection",
            "from": "rock__scale",
            "to": "rock",
            "from_output": "unique_filter_output",
            "to_input": "scale",
        },
        {
            "op": "ensure_connection",
            "from": "rock__center_position",
            "to": "rock",
            "from_output": "unique_filter_output",
            "to_input": "center_position",
        },
    ]


def test_validate_graph_change_rejects_unlowerable_function_library_parameters() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "owner_definition": "sbs::library::3d_viewer",
            "property_id": "sdf_scene",
        },
        change={
            "nodes": [
                {
                    "id": "rock",
                    "definition": "sbs::function-library::3d_sdf_rock",
                    "parameters": {"not_a_port": 1.0},
                }
            ],
            "output": "rock",
        },
    )

    assert result["result"]["valid"] is False
    assert result["result"]["errors"][0]["code"] == "unsupported_instance_parameter"
    assert result["result"]["errors"][0]["path"] == "change.nodes[0].parameters.not_a_port"


def test_apply_graph_change_canonicalizes_function_library_port_aliases() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "owner_definition": "sbs::library::3d_viewer",
            "property_id": "sdf_scene",
        },
        context=None,
        change={
            "nodes": [
                {"id": "sphere", "definition": "sbs::function-library::3d_sdf_sphere"},
                {"id": "color", "definition": "sbs::function-library::set_color"},
            ],
            "connections": [
                {
                    "from": "sphere",
                    "from_output": "unique_filter_output",
                    "to": "color",
                    "to_input": "sdf_scene",
                },
                {
                    "from": "sphere",
                    "from_output": "unique_filter_output",
                    "to": "color",
                    "to_input": "base_color",
                },
            ],
            "output": {"node": "color", "output": "unique_filter_output"},
        },
    )

    assert result["result"]["validation"]["valid"] is True
    assert fake.calls[-1][1]["patch"]["operations"][2:4] == [
        {
            "op": "ensure_connection",
            "from": "sphere",
            "to": "color",
            "from_output": "unique_filter_output",
            "to_input": "scene",
        },
        {
            "op": "ensure_connection",
            "from": "sphere",
            "to": "color",
            "from_output": "unique_filter_output",
            "to_input": "basecolor",
        },
    ]


def test_apply_graph_change_accepts_endpoint_object_connections_for_function_graphs() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "viewer_1",
            "owner_definition": "sbs::library::3d_viewer",
            "property_id": "sdf_scene",
        },
        context=None,
        change={
            "nodes": [
                {"id": "sphere", "definition": "sbs::function-library::3d_sdf_sphere"},
                {"id": "color", "definition": "sbs::function-library::set_color"},
            ],
            "connections": [
                {
                    "from": {"node": "sphere", "output": "unique_filter_output"},
                    "to": {"node": "color", "input": "sdf_scene"},
                }
            ],
            "output": {"node": "color", "output": "unique_filter_output"},
        },
    )

    assert result["result"]["validation"]["valid"] is True
    assert fake.calls[-1][1]["patch"]["operations"][2:3] == [
        {
            "op": "ensure_connection",
            "from": "sphere",
            "to": "color",
            "from_output": "unique_filter_output",
            "to_input": "scene",
        }
    ]


def test_apply_graph_change_accepts_builtin_endpoint_for_pixel_processor_function_graph() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        context=None,
        change={
            "nodes": [{"id": "sample", "definition": "sbs::function::samplecol"}],
            "connections": [
                {
                    "from": {"builtin": "$pos"},
                    "to": {"node": "sample", "input": "pos"},
                }
            ],
            "output": "sample",
        },
    )

    assert result["result"]["validation"]["valid"] is True
    assert fake.calls[-1][1]["patch"]["operations"][1:2] == [
        {"op": "ensure_connection", "from": {"builtin": "$pos"}, "to": "sample", "to_input": "pos"}
    ]


def test_apply_graph_change_accepts_named_builtin_endpoint_for_sdf_function_graph() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "splatter_1",
            "owner_definition": "sbs::library::shape_splatter_v2",
            "property_id": "pattern_sdf_function",
        },
        context=None,
        change={
            "nodes": [{"id": "shape_id", "definition": "sbs::function::tofloat"}],
            "connections": [
                {
                    "from": {"builtin": "shape.id"},
                    "to": {"node": "shape_id", "input": "value"},
                }
            ],
            "output": "shape_id",
        },
    )

    assert result["result"]["validation"]["valid"] is True
    patch = fake.calls[-1][1]["patch"]
    assert patch["operations"][1:3] == [
        {
            "op": "ensure_node",
            "id": "shape_id__value",
            "definition": "sbs::function::get_integer1",
            "parameters": {"__constant__": "shape.id"},
        },
        {
            "op": "ensure_connection",
            "from": "shape_id__value",
            "to": "shape_id",
            "from_output": "unique_filter_output",
            "to_input": "value",
        },
    ]


def test_apply_graph_change_patches_existing_function_node_parameters_without_output() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [
                {
                    "id": "1573197239",
                    "parameters": {"__constant__": {"value": [0.2, 0.4], "value_type": "float2"}},
                }
            ]
        },
    )

    assert result["result"]["validation"]["valid"] is True
    assert result["result"]["apply_strategy"] == "patch_property_graph"
    assert fake.calls[-1][1]["patch"]["operations"] == [
        {
            "op": "ensure_node",
            "id": "1573197239",
            "parameters": {"__constant__": {"value": [0.2, 0.4], "value_type": "float2"}},
        }
    ]
    assert result["result"]["parameter_results"] == {
        "applied": [{"node": "1573197239", "parameter": "__constant__", "value": [0.2, 0.4], "value_type": "float2"}],
        "skipped": [],
        "errors": [],
    }


def test_apply_graph_change_accepts_top_level_parameters_for_function_graph_creation() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [
                {"id": "pp_rg", "definition": "sbs::function::const_float2"},
                {"id": "pp_ba", "definition": "sbs::function::const_float2"},
                {"id": "pp_vec4", "definition": "sbs::function::vector4"},
            ],
            "parameters": [
                {"node": "pp_rg", "parameter": "__constant__", "value": {"x": 0.125, "y": 0.25}},
                {"node": "pp_ba", "parameter": "__constant__", "value": {"x": 0.5, "y": 1.0}},
            ],
            "connections": [
                {
                    "from": "pp_rg",
                    "from_output": "unique_filter_output",
                    "to": "pp_vec4",
                    "to_input": "componentsin",
                },
                {
                    "from": "pp_ba",
                    "from_output": "unique_filter_output",
                    "to": "pp_vec4",
                    "to_input": "componentslast",
                },
            ],
            "output": {"node": "pp_vec4", "output": "unique_filter_output"},
        },
    )

    operations = fake.calls[-1][1]["patch"]["operations"]
    assert operations[0]["parameters"] == {"__constant__": {"x": 0.125, "y": 0.25}}
    assert operations[1]["parameters"] == {"__constant__": {"x": 0.5, "y": 1.0}}
    assert "capabilities" not in result["result"]["validation"]


def test_apply_graph_change_accepts_top_level_parameters_for_function_graph_patch() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "parameters": [
                {"node": "1573198576", "parameter": "__constant__", "value": {"x": 0.125, "y": 0.25}},
                {"node": "1573198577", "parameter": "__constant__", "value": {"x": 0.5, "y": 1.0}},
            ]
        },
    )

    assert result["result"]["validation"]["valid"] is True
    assert result["result"]["apply_strategy"] == "patch_property_graph"
    assert fake.calls[-1][1]["patch"]["operations"] == [
        {
            "op": "ensure_node",
            "id": "1573198576",
            "parameters": {"__constant__": {"x": 0.125, "y": 0.25}},
        },
        {
            "op": "ensure_node",
            "id": "1573198577",
            "parameters": {"__constant__": {"x": 0.5, "y": 1.0}},
        },
    ]
    assert result["result"]["parameter_results"]["applied"] == [
        {"node": "1573198576", "parameter": "__constant__", "value": {"x": 0.125, "y": 0.25}, "value_type": "float2"},
        {"node": "1573198577", "parameter": "__constant__", "value": {"x": 0.5, "y": 1.0}, "value_type": "float2"},
    ]


def test_validate_graph_change_output_type_mismatch_suggests_compatible_root_nodes() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [{"id": "sum", "definition": "sbs::function::add"}],
            "connections": [],
            "output": "sum",
        },
    )

    errors = result["result"]["errors"]
    mismatch = next(error for error in errors if error["code"] == "output_type_mismatch")
    assert {"definition": "sbs::function::const_float4", "output_type": "float4"} in mismatch[
        "suggested_root_definitions"
    ]
    assert {"definition": "sbs::function::samplecol", "output_type": "float4"} in mismatch["suggested_root_definitions"]


def test_validate_graph_change_invalid_result_omits_large_capability_echo() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [{"id": "bad", "definition": "sbs::function-library::3d_sdf_sphere"}],
            "connections": [],
            "output": "bad",
        },
    )

    validation = result["result"]
    assert validation["valid"] is False
    assert validation["capabilities"] is None
    assert validation["capability_summary"]["allowed_definition_count"] > 0
    assert "nodes" not in validation["capability_summary"]
    assert "allowed_definitions" not in validation["capability_summary"]


def test_apply_graph_change_for_package_graph_uses_internal_authoring_primitives() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "uniform",
                    "definition": "sbs::compositing::uniform",
                    "position": [0, 0],
                    "parameters": {"outputcolor": {"value": [1, 0, 0, 1], "value_type": "float4"}},
                },
                {"id": "blend", "definition": "sbs::compositing::blend", "position": [260, 0]},
            ],
            "connections": [
                {
                    "from": "uniform",
                    "from_output": "unique_filter_output",
                    "to": "blend",
                    "to_input": "source",
                }
            ],
        },
    )

    assert result["operation"] == "apply_graph_change"
    assert result["result"]["applied"] is True
    assert result["result"]["apply_strategy"] == "merge_package_graph"
    assert [entry["operation"] for entry in result["result"]["execution_trace"]] == [
        "create_node",
        "set_parameter",
        "create_node",
        "connect_nodes",
    ]
    assert all(entry["callable"] is False for entry in result["result"]["execution_trace"])
    assert "internal_operations" not in result["result"]
    assert result["result"]["node_map"] == {
        "uniform": "uniform_created",
        "blend": "blend_created",
    }
    assert result["result"]["created"] == {
        "uniform": "uniform_created",
        "blend": "blend_created",
    }
    assert result["result"]["created_nodes"] == [
        {
            "id": "uniform",
            "node_id": "uniform_created",
            "definition": "sbs::compositing::uniform",
        },
        {
            "id": "blend",
            "node_id": "blend_created",
            "definition": "sbs::compositing::blend",
        },
    ]
    assert result["result"]["connections"] == [
        {
            "from": {"node": "uniform", "node_id": "uniform_created", "output": "unique_filter_output"},
            "to": {"node": "blend", "node_id": "blend_created", "input": "source"},
        }
    ]
    assert result["result"]["updated_nodes"] == ["uniform_created"]
    assert result["result"]["updated_outputs"] == []
    assert all("result" not in item for item in result["result"]["created_nodes"])
    assert "operations" not in result["result"]
    assert fake.calls == [
        (
            "create_node",
            {
                "definition_id": "sbs::compositing::uniform",
                "graph_identifier": "GraphA",
                "position": [0.0, 0.0],
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "uniform_created",
                "parameter_id": "outputcolor",
                "value": [1, 0, 0, 1],
                "value_type": "float4",
                "graph_identifier": "GraphA",
            },
        ),
        (
            "create_node",
            {
                "definition_id": "sbs::compositing::blend",
                "graph_identifier": "GraphA",
                "position": [260.0, 0.0],
            },
        ),
        (
            "connect_nodes",
            {
                "from_node_id": "uniform_created",
                "to_node_id": "blend_created",
                "from_output": "unique_filter_output",
                "to_input": "source",
                "graph_identifier": "GraphA",
            },
        ),
    ]


def test_parameter_results_use_static_parameter_types_for_library_enum_ints() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "viewer",
                    "definition": "sbs::library::3d_viewer",
                    "parameters": {"scene_type": 0, "output": 0},
                }
            ]
        },
    )

    assert result["result"]["parameter_results"]["applied"] == [
        {"node": "3d_viewer_created", "parameter": "scene_type", "value": 0, "value_type": "int"},
        {"node": "3d_viewer_created", "parameter": "output", "value": 0, "value_type": "int"},
    ]


def test_apply_graph_change_lowers_output_usage_parameter_to_host_usages() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "position": [1700, 120],
                    "parameters": {
                        "identifier": "mcp_pixel_processor_test",
                        "label": "MCP Pixel Processor Test",
                        "usage": "baseColor",
                    },
                }
            ],
            "connections": [],
        },
    )

    assert result["result"]["applied"] is True
    assert fake.calls == [
        (
            "create_node",
            {
                "definition_id": "sbs::compositing::output",
                "graph_identifier": "GraphA",
                "position": [1700.0, 120.0],
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "output_created",
                "parameter_id": "identifier",
                "value": "mcp_pixel_processor_test",
                "value_type": "string",
                "graph_identifier": "GraphA",
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "output_created",
                "parameter_id": "label",
                "value": "MCP Pixel Processor Test",
                "value_type": "string",
                "graph_identifier": "GraphA",
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "output_created",
                "parameter_id": "usages",
                "value": "baseColor",
                "value_type": "usage_array",
                "graph_identifier": "GraphA",
            },
        ),
    ]


def test_apply_graph_change_lowers_output_usage_object_to_host_usages() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {
                        "usage": {
                            "name": "baseColor",
                            "components": "RGBA",
                            "color_space": "Linear",
                        },
                    },
                }
            ],
            "connections": [],
        },
    )

    assert result["result"]["applied"] is True
    assert fake.calls == [
        (
            "create_node",
            {
                "definition_id": "sbs::compositing::output",
                "graph_identifier": "GraphA",
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "output_created",
                "parameter_id": "usages",
                "value": {"name": "baseColor", "components": "RGBA", "color_space": "Linear"},
                "value_type": "usage_array",
                "graph_identifier": "GraphA",
            },
        ),
    ]


def test_apply_graph_change_accepts_endpoint_object_connections_for_package_graphs() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {"id": "uniform", "definition": "sbs::compositing::uniform"},
                {"id": "blend", "definition": "sbs::compositing::blend"},
            ],
            "connections": [
                {
                    "from": {"node": "uniform", "output": "unique_filter_output"},
                    "to": {"node": "blend", "input": "source"},
                }
            ],
        },
    )

    assert result["result"]["applied"] is True
    assert fake.calls[-1] == (
        "connect_nodes",
        {
            "from_node_id": "uniform_created",
            "to_node_id": "blend_created",
            "from_output": "unique_filter_output",
            "to_input": "source",
            "graph_identifier": "GraphA",
        },
    )


def test_apply_graph_change_rewires_existing_package_node_connection_with_snapshot() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "connections": [
                {
                    "from": {"node": "1573185644", "output": "unique_filter_output"},
                    "to": {"node": "1573185646", "input": "input1"},
                }
            ]
        },
    )

    assert result["result"]["applied"] is True
    assert [call[0] for call in fake.calls[-2:]] == ["disconnect_nodes", "connect_nodes"]
    assert fake.calls[-2][1] == {"node_id": "1573185646", "input_id": "input1", "graph_identifier": "GraphA"}
    assert fake.calls[-1][1] == {
        "from_node_id": "1573185644",
        "to_node_id": "1573185646",
        "from_output": "unique_filter_output",
        "to_input": "input1",
        "graph_identifier": "GraphA",
    }
    assert result["result"]["execution_trace"][-2]["previous_connections"] == [
        {"from_node": "old_source", "from_output": "unique_filter_output"}
    ]


def test_apply_graph_change_rewires_declared_existing_package_node_connection_with_snapshot() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [{"id": "1573185646", "definition": "sbs::compositing::output"}],
            "connections": [
                {
                    "from": {"node": "1573185644", "output": "unique_filter_output"},
                    "to": {"node": "1573185646", "input": "input1"},
                }
            ],
        },
    )

    assert result["result"]["applied"] is True
    assert [call[0] for call in fake.calls[-2:]] == ["disconnect_nodes", "connect_nodes"]
    assert fake.calls[-2][1] == {"node_id": "1573185646", "input_id": "input1", "graph_identifier": "GraphA"}


def test_apply_graph_change_restores_existing_connection_when_rewire_fails() -> None:
    fake = FakeClient()
    fake.fail_next_connect = True
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "connections": [
                {
                    "from": {"node": "1573185644", "output": "unique_filter_output"},
                    "to": {"node": "1573185646", "input": "input1"},
                }
            ]
        },
    )

    assert result["result"]["applied"] is False
    assert result["result"]["rolled_back"] is True
    assert result["result"]["rollback"]["restored_connections"] == [
        {
            "node_id": "1573185646",
            "input": "input1",
            "connections": [{"from_node": "old_source", "from_output": "unique_filter_output"}],
        }
    ]
    assert [call[0] for call in fake.calls[-2:]] == ["disconnect_nodes", "connect_nodes"]
    assert fake.calls[-1][1]["from_node_id"] == "old_source"


def test_apply_graph_change_updates_existing_package_node_parameter_with_snapshot() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "1573185644",
                    "definition": "sbs::compositing::uniform",
                    "parameters": {"outputcolor": {"value": [1, 0, 0, 1], "value_type": "float4"}},
                }
            ]
        },
    )

    assert result["result"]["applied"] is True
    assert fake.calls[-1] == (
        "set_parameter",
        {
            "node_id": "1573185644",
            "parameter_id": "outputcolor",
            "value": [1, 0, 0, 1],
            "value_type": "float4",
            "graph_identifier": "GraphA",
        },
    )


def test_apply_graph_change_accepts_top_level_parameters_for_existing_package_nodes_with_snapshot() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "parameters": [
                {
                    "node": "1573190249",
                    "parameter": "outputcolor",
                    "value": {"r": 0.125, "g": 0.25, "b": 0.5, "a": 1.0},
                },
                {"node": "1573198415", "parameter": "colorswitch", "value": False},
            ]
        },
    )

    assert result["result"]["applied"] is True
    assert [call[0] for call in fake.calls if call[0] == "set_parameter"] == ["set_parameter", "set_parameter"]


def test_apply_graph_change_restores_existing_parameter_and_position_on_later_failure() -> None:
    fake = FakeClient()
    fake.fail_next_connect = True
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "operations": [
                {
                    "op": "set_parameter",
                    "node": "1573185644",
                    "parameter": "outputcolor",
                    "value": [1, 0, 0, 1],
                    "value_type": "float4",
                },
                {"op": "move_node", "node": "1573185644", "position": [100, 200]},
                {
                    "op": "ensure_connection",
                    "from": {"node": "1573185644", "output": "unique_filter_output"},
                    "to": {"node": "1573185646", "input": "input1"},
                },
            ]
        },
    )

    assert result["result"]["applied"] is False
    assert result["result"]["rolled_back"] is True
    assert result["result"]["rollback"]["restored_parameters"] == [
        {
            "node_id": "1573185644",
            "parameter": "outputcolor",
            "value": [0, 0, 0, 1],
            "value_type": "ColorRGBA",
        }
    ]
    assert result["result"]["rollback"]["restored_positions"] == [
        {"node_id": "1573185644", "position": [10, 20]}
    ]


def test_apply_graph_change_rolls_back_package_graph_nodes_on_apply_failure() -> None:
    fake = FakeClient()
    fake.fail_on_parameter = "bad_property"
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "shape",
                    "definition": "sbs::compositing::uniform",
                    "parameters": {"outputcolor": {"value": [1, 0, 0, 1], "value_type": "float4"}},
                },
                {
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {"bad_property": "will_fail"},
                },
            ],
            "connections": [
                {"from": "shape", "from_output": "unique_filter_output", "to": "out", "to_input": "inputNodeOutput"}
            ],
        },
    )

    assert result["result"]["applied"] is False
    assert result["result"]["rolled_back"] is True
    assert result["result"]["partial_changes"] is False
    assert result["result"]["rollback"]["deleted"] == [
        {"node_id": "output_created", "result": {"status": "deleted", "node_id": "output_created"}},
        {"node_id": "uniform_created", "result": {"status": "deleted", "node_id": "uniform_created"}},
    ]
    assert [call[0] for call in fake.calls] == [
        "create_node",
        "set_parameter",
        "create_node",
        "set_parameter",
        "delete_node",
        "delete_node",
    ]


def test_apply_graph_change_failure_trace_identifies_failed_host_step() -> None:
    fake = FakeClient()
    fake.fail_on_parameter = "bad_property"
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {"id": "shape", "definition": "sbs::compositing::uniform"},
                {"id": "out", "definition": "sbs::compositing::output", "parameters": {"bad_property": "will_fail"}},
            ],
            "connections": [
                {"from": "shape", "from_output": "unique_filter_output", "to": "out", "to_input": "inputNodeOutput"}
            ],
        },
    )

    payload = result["result"]
    assert payload["applied"] is False
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_message"] == "Property 'bad_property' not found"
    assert payload["failed_step"] == {
        "operation": "set_parameter",
        "node": "out",
        "resolved_node_id": "output_created",
        "parameter": "bad_property",
    }
    assert payload["execution_trace"][-1] == {
        "operation": "set_parameter",
        "callable": False,
        "public_replacement": "substance_designer__apply_graph_change",
        "status": "failed",
        "node": "out",
        "resolved_node_id": "output_created",
        "parameter": "bad_property",
        "error_type": "RuntimeError",
        "error_message": "Property 'bad_property' not found",
    }


def test_apply_graph_change_rolls_back_package_patch_nodes_on_apply_failure() -> None:
    fake = FakeClient()
    fake.fail_on_parameter = "bad_property"
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "operations": [
                {"op": "ensure_node", "id": "shape", "definition": "sbs::compositing::uniform"},
                {
                    "op": "ensure_node",
                    "id": "out",
                    "definition": "sbs::compositing::output",
                    "parameters": {"bad_property": "will_fail"},
                },
            ]
        },
    )

    payload = result["result"]
    assert payload["applied"] is False
    assert payload["apply_strategy"] == "patch_package_graph"
    assert payload["rolled_back"] is True
    assert payload["partial_changes"] is False
    assert payload["failed_step"] == {
        "operation": "set_parameter",
        "node": "out",
        "resolved_node_id": "output_created",
        "parameter": "bad_property",
    }
    assert payload["rollback"]["deleted"] == [
        {"node_id": "output_created", "result": {"status": "deleted", "node_id": "output_created"}},
        {"node_id": "uniform_created", "result": {"status": "deleted", "node_id": "uniform_created"}},
    ]


def test_package_graph_capabilities_explain_library_node_creation() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        intent="tile pbr material",
    )

    tile = next(node for node in result["result"]["nodes"] if node["definition"] == "sbs::library::tile_generator")
    assert tile["creation"]["method"] == "create_instance_node"
    assert tile["creation"]["resource_url"] == "pkg:///tile_generator"
    assert tile["creation"]["package"]["path"] == "pattern_tile_generator.sbs"


def test_apply_graph_change_routes_library_definitions_to_instance_nodes() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "tiles",
                    "definition": "sbs::library::tile_generator",
                    "position": [0, 0],
                    "parameters": {"x_amount": 8},
                },
            ],
            "connections": [],
        },
    )

    assert result["result"]["applied"] is True
    assert [entry["operation"] for entry in result["result"]["execution_trace"]] == [
        "create_instance_node",
        "set_parameter",
    ]
    assert result["result"]["created_nodes"][0]["resource_url"] == "pkg:///tile_generator"
    assert fake.calls[:2] == [
        (
            "create_instance_node",
            {
                "resource_url": "pkg:///tile_generator",
                "graph_identifier": "GraphA",
                "position": [0.0, 0.0],
                "package_hint": {
                    "package": {
                        "evidence": {"source": "package_scan", "status": "complete"},
                        "kind": "builtin_standard_library",
                        "path": "pattern_tile_generator.sbs",
                    },
                    "standard_package_candidates": [
                        {
                            "evidence": {"source": "package_scan", "status": "complete"},
                            "path": "pattern_tile_generator.sbs",
                            "resource_url": "pkg:///tile_generator",
                        }
                    ],
                },
            },
        ),
        (
            "set_parameter",
            {
                "node_id": "tile_generator_created",
                "parameter_id": "x_amount",
                "value": 8,
                "value_type": "float",
                "graph_identifier": "GraphA",
            },
        ),
    ]


def test_validate_package_graph_rejects_unknown_library_parameter_with_suggestion() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "demo_bevel",
                    "definition": "sbs::library::bevel",
                    "parameters": {"bevel_width": 0.028},
                }
            ]
        },
    )

    error = result["result"]["errors"][0]
    assert result["result"]["valid"] is False
    assert error["code"] == "unknown_parameter"
    assert error["path"] == "change.nodes[0].parameters.bevel_width"
    assert error["did_you_mean"] == "distance"


def test_validate_package_graph_rejects_invalid_enum_value() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "splatter",
                    "definition": "sbs::library::shape_splatter_v2",
                    "parameters": {"shape_type": 5},
                }
            ]
        },
    )

    error = result["result"]["errors"][0]
    assert result["result"]["valid"] is False
    assert error["code"] == "invalid_enum_value"
    assert error["allowed_values"] == [1, 2, 3, 4, 10, 11, 12, 13]


def test_validate_package_graph_rejects_unsupported_parameter_value_shape() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "package_graph", "graph_identifier": "GraphA"},
        context={"graph_kind": "substance_graph"},
        change={
            "nodes": [
                {
                    "id": "demo_bevel",
                    "definition": "sbs::library::bevel",
                    "parameters": {"distance": [{"pos": 0.0, "value": 1.0}]},
                }
            ]
        },
    )

    error = result["result"]["errors"][0]
    assert result["result"]["valid"] is False
    assert error["code"] == "unsupported_parameter_value_shape"


def test_context_resolution_uses_function_contract_metadata_for_known_host_properties() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    pixel = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        }
    )["result"]["graph_context"]
    value = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "value_1",
            "owner_definition": "sbs::compositing::valueprocessor",
            "property_id": "function",
        }
    )["result"]["graph_context"]
    shape = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "shape_splatter_1",
            "owner_definition": "sbs::library::shape_splatter_v2",
            "property_id": "position_function",
        }
    )["result"]["graph_context"]

    assert pixel["contract"]["kind"] == "pixel_processor"
    assert pixel["contract"]["output"]["type"] == "float4"
    assert pixel["contract"]["builtins"] == {"$pos": {"type": "float2", "readable": True}}
    assert value["contract"]["kind"] == "value_processor"
    assert value["contract"]["output"]["type"] == "owner_output_type"
    assert shape["contract"]["kind"] == "host_property_function"
    assert shape["contract"]["output"]["type"] == "float2"


def test_unknown_function_property_reports_unsupported_reasons_without_guessing() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "node_1",
            "owner_definition": "sbs::library::unknown",
            "property_id": "mystery_function",
        }
    )

    capabilities = result["result"]
    assert capabilities["graph_context"]["contract"]["kind"] == "unknown"
    assert capabilities["allowed_definitions"] == []
    assert capabilities["unsupported_reasons"][0]["code"] == "unknown_function_contract"


def test_validate_graph_change_rejects_missing_port_evidence() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "value_1",
            "property_id": "function",
        },
        context={
            "graph_kind": "function_graph",
            "contract": {"kind": "host_property_function", "output": {"type": "float4"}},
            "allowed_context_scopes": ["generic_function", "unknown_function_context"],
        },
        change={
            "nodes": [
                {"id": "source", "definition": "sbs::function-library::aces_tonemapper"},
                {"id": "target", "definition": "sbs::function::swizzle1"},
            ],
            "connections": [
                {"from": "source", "from_output": "unique_filter_output", "to": "target", "to_input": "vector"},
            ],
            "output": "target",
        },
    )

    assert result["result"]["valid"] is False
    assert "port_evidence_missing" in {error["code"] for error in result["result"]["errors"]}


def test_validate_graph_change_rejects_wrong_function_output_type() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={
            "nodes": [{"id": "value", "definition": "sbs::function::const_float1"}],
            "connections": [],
            "output": "value",
        },
    )

    assert result["result"]["valid"] is False
    assert "output_type_mismatch" in {error["code"] for error in result["result"]["errors"]}


def test_value_processor_rejects_string_output_using_live_probe_contract_evidence() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "value_1",
            "owner_definition": "sbs::compositing::valueprocessor",
            "property_id": "function",
        },
        change={
            "nodes": [{"id": "value", "definition": "sbs::function::const_string"}],
            "connections": [],
            "output": "value",
        },
    )

    errors = result["result"]["errors"]
    assert result["result"]["valid"] is False
    assert any(
        error["code"] == "output_contract_blocked"
        and error["contract"] == "value_processor"
        and error["reason"] == "value_processor_default_state_rejected"
        for error in errors
    )


def test_fx_map_capabilities_use_packaged_v2_fx_map_nodes() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_authoring_capabilities(graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA"})

    capabilities = result["result"]
    assert capabilities["graph_context"]["graph_kind"] == "fx_map_graph"
    assert "sbs::fxmap::paramset" in capabilities["allowed_definitions"]
    assert "sbs::fxmap::addnode" in capabilities["allowed_definitions"]
    assert FX_MAP_GRAPH_URI in capabilities["reference_uris"]


def test_fx_map_parameter_only_change_uses_patch_strategy_without_definition() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.apply_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={"nodes": [{"id": "existing_paramset", "parameters": {"random": 0.75}}]},
    )

    payload = result["result"]
    assert payload["validation"]["valid"] is True
    assert payload["apply_strategy"] == "patch_fx_map_graph"
    assert fake.calls[-1][1]["patch"]["operations"] == [
        {"op": "ensure_node", "id": "existing_paramset", "parameters": {"random": 0.75}}
    ]
    assert fake.calls[-1] == (
        "apply_fx_map_graph_patch",
        {
            "patch": {
                "graph_kind": "fx_map_graph",
                "target": {"graph_identifier": "GraphA", "node_id": "fx_node"},
                "graph_type": "SDSBSFxMapGraph",
                "operations": [{"op": "ensure_node", "id": "existing_paramset", "parameters": {"random": 0.75}}],
            },
            "mode": "patch",
        },
    )


def test_fx_map_patch_accepts_empty_node_property_graph_operation() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={
            "operations": [
                {
                    "op": "set_property_graph",
                    "node": "quadrant",
                    "property": "branchoffset",
                    "graph_type": "SDSBSFunctionGraph",
                    "nodes": [],
                    "connections": [],
                }
            ]
        },
    )

    assert result["result"]["valid"] is True


def test_fx_map_patch_validates_ports_for_new_nodes_in_same_change() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={
            "nodes": [
                {"id": "pattern", "definition": "sbs::fxmap::paramset"},
                {"id": "iterate", "definition": "sbs::fxmap::addnode"},
            ],
            "connections": [
                {
                    "from": "pattern",
                    "from_output": "unique_filter_output",
                    "to": "iterate",
                    "to_input": "output1",
                }
            ],
            "output": "iterate",
        },
    )

    assert result["result"]["valid"] is True
    assert result["result"]["errors"] == []


def test_fx_map_patch_accepts_node_property_graph_operation() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={
            "operations": [
                {
                    "op": "set_property_graph",
                    "node": "quadrant",
                    "property": "branchoffset",
                    "graph_type": "SDSBSFunctionGraph",
                    "nodes": [{"id": "offset", "definition": "sbs::function::const_float2"}],
                    "connections": [],
                    "output": "offset",
                }
            ]
        },
    )

    assert result["result"]["valid"] is True
    assert "set_property_graph" in result["result"]["capability_summary"]["apply_supported_changes"]

    applied = commands.apply_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": "fx_node"},
        change={
            "operations": [
                {
                    "op": "set_property_graph",
                    "node": "quadrant",
                    "property": "branchoffset",
                    "graph_type": "SDSBSFunctionGraph",
                    "nodes": [{"id": "offset", "definition": "sbs::function::const_float2"}],
                    "connections": [],
                    "output": "offset",
                }
            ]
        },
    )

    assert applied["result"]["applied"] is True
    assert fake.calls[-1] == (
        "apply_fx_map_graph_patch",
        {
            "patch": {
                "graph_kind": "fx_map_graph",
                "target": {"graph_identifier": "GraphA", "node_id": "fx_node"},
                "graph_type": "SDSBSFxMapGraph",
                "operations": [
                    {
                        "op": "set_property_graph",
                        "node": "quadrant",
                        "property": "branchoffset",
                        "graph_type": "SDSBSFunctionGraph",
                        "nodes": [{"id": "offset", "definition": "sbs::function::const_float2"}],
                        "connections": [],
                        "output": "offset",
                    }
                ],
            },
            "mode": "patch",
        },
    )
