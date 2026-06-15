"""Tests for read-only command normalization."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from dcc_mcp_substancedesigner.authoring_reference import public_tool_action_ids
from dcc_mcp_substancedesigner.bridge import SubstanceDesignerBridgeError
from dcc_mcp_substancedesigner.commands import SubstanceDesignerCommands, SubstanceDesignerValidationError


class FakeClient:
    def __init__(self, *, create_package_returns_index: bool = True) -> None:
        self.calls = []
        self.create_package_returns_index = create_package_returns_index

    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_scene_info":
            return {
                "sd_version": "16.0.0",
                "plugin_version": "3.3.0",
                "current_graph": "GraphA",
                "current_graph_node_count": 2,
                "packages": [
                    {
                        "file_path": "E:/materials/test.sbs",
                        "graphs": [
                            {"identifier": "GraphA", "type": "SDSBSCompGraph", "node_count": 2},
                            {"identifier": "GraphB", "type": "SDSBSCompGraph", "node_count": 1},
                        ],
                    }
                ],
            }
        if command_type == "get_graph_info":
            return {
                "identifier": "GraphA",
                "package_path": "E:/materials/test.sbs",
                "node_count": 3,
                "node_limit": params.get("node_limit", 100),
                "truncated": False,
                "nodes": [
                    {
                        "identifier": "node_1",
                        "definition": "sbs::compositing::uniform",
                        "position": [1, 2],
                        "connections": [],
                    },
                    {
                        "identifier": "node_2",
                        "definition": "sbs::compositing::levels",
                        "position": [3, 4],
                        "connections": [
                            {
                                "input": "input1",
                                "from_node": "node_1",
                                "from_output": "unique_filter_output",
                                "connRefOutput": "12345",
                            }
                        ],
                    },
                    {
                        "identifier": "out_1",
                        "definition": "sbs::compositing::output",
                        "position": [5, 6],
                        "annotations": [
                            {"id": "label", "value": "Base Color"},
                            {"id": "identifier", "value": "basecolor"},
                            {
                                "id": "usages",
                                "value": [{"name": "baseColor", "components": "RGBA", "color_space": "sRGB"}],
                            },
                        ],
                        "connections": [
                            {"input": "inputNodeOutput", "from_node": "node_2", "from_output": "unique_filter_output"}
                        ],
                    },
                ],
            }
        if command_type == "get_node_info":
            if params["node_id"] == "out_1":
                return {
                    "node_id": "out_1",
                    "definition": "sbs::compositing::output",
                    "is_library_node": False,
                    "position": [5, 6],
                    "inputs": [{"id": "inputNodeOutput", "connected_from": ["node_2.unique_filter_output"]}],
                    "outputs": [],
                    "annotations": [{"id": "label", "value": "opacity"}, {"id": "identifier", "value": "opacity"}],
                }
            return {
                "node_id": params["node_id"],
                "definition": "sbs::compositing::uniform"
                if params["node_id"] == "node_1"
                else "sbs::compositing::levels",
                "is_library_node": False,
                "position": [1, 2],
                "inputs": [{"id": "outputcolor", "value": {"r": 1, "g": 0, "b": 0, "a": 1}}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
            }
        if command_type == "inspect_node":
            return {
                "target": {
                    key: value for key, value in params.items() if key in {"node_id", "definition_id", "resource_url"}
                },
                "node_id": params.get("node_id") or "tmp_1",
                "temporary_node_id": None if params.get("node_id") else "tmp_1",
                "definition": params.get("definition_id") or "pkg:///perlin_noise?dependency=1",
                "is_library_node": bool(params.get("resource_url")),
                "instance": {"resource_url": params["resource_url"]} if params.get("resource_url") else None,
                "inputs": [{"id": "input1"}, {"id": "intensity", "value": 1.0, "type": "float"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
                "property_context": {
                    "property_id": params["property_id"],
                    "available": False,
                }
                if params.get("property_id")
                else None,
            }
        if command_type == "get_preview":
            if params.get("node_id") is None:
                return {
                    "preview_type": "graph_3d_view",
                    "image_path": "E:/tmp/graph_preview.png",
                    "width": params.get("width") or 512,
                    "height": params.get("height") or 512,
                    "graph_id": params.get("graph_identifier") or "GraphA",
                    "graph_identifier": params.get("graph_identifier") or "GraphA",
                    "resolution": params["resolution"],
                    "captured_ms": 92,
                    "requires_ui": True,
                    "opened_graph": bool(params.get("graph_identifier")),
                }
            return {
                "preview_type": "node_output",
                "image_path": "E:/tmp/preview.png",
                "width": 256,
                "height": 256,
                "graph_id": params.get("graph_identifier") or "GraphA",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "node_id": params["node_id"],
                "node_output_id": params.get("node_output_id") or "unique_filter_output",
                "channel": params["channel"],
                "resolution": params["resolution"],
                "render_ms": 184,
                "cached": False,
                "parameters_hash": "abc123",
            }
        if command_type == "export_output":
            return {
                "status": "exported",
                "node_id": params["node_id"],
                "node_output_id": params.get("node_output_id") or "unique_filter_output",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "file_path": params["file_path"],
                "format": "png",
            }
        if command_type == "create_graph":
            return {
                "identifier": "NewGraph",
                "requested_name": params["graph_name"],
                "sanitized_name": "NewGraph",
                "type": "SDSBSCompGraph",
                "package": "E:/materials/test.sbs",
            }
        if command_type == "create_package":
            result = {
                "file_path": params.get("file_path") or "",
                "message": "New package created.",
            }
            if self.create_package_returns_index:
                result["package_index"] = 1
            return result
        if command_type == "save_package":
            return {
                "status": "saved",
                "package_index": params.get("package_index", 0),
                "file_path": params.get("file_path") or params.get("package_path") or "E:/materials/test.sbs",
            }
        if command_type == "create_node":
            return {
                "node_id": "uniform_1",
                "definition": params["definition_id"],
                "position": params["position"],
            }
        if command_type == "create_instance_node":
            return {
                "node_id": "instance_1",
                "resource_url": params["resource_url"],
                "position": params["position"],
            }
        if command_type == "connect_nodes":
            return {
                "from_node": params["from_node_id"],
                "from_output": params.get("from_output") or "unique_filter_output",
                "to_node": params["to_node_id"],
                "to_input": params.get("to_input") or "input1",
                "success": True,
            }
        if command_type == "move_node":
            return {"node_id": params["node_id"], "position": params["position"]}
        if command_type == "duplicate_node":
            return {"original_node_id": params["node_id"], "new_node_id": "copy_1", "offset": params.get("offset")}
        if command_type == "set_parameter":
            return {
                "node_id": params["node_id"],
                "parameter_id": params["parameter_id"],
                "value": params["value"],
                "value_type": params["value_type"],
            }
        if command_type == "list_controls":
            return {
                "target": params["target"],
                "controls": [{"id": "gain", "value": 0.5, "role": "node_parameter"}],
            }
        if command_type == "set_controls":
            return {
                "target": params["target"],
                "updated": [{"id": params["updates"][0]["id"], "status": "updated"}],
            }
        if command_type == "list_graph_inputs":
            return {
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "inputs": [
                    {
                        "id": "color_root",
                        "value": [1, 1, 1, 1],
                        "value_type": "color",
                        "group": "Palette",
                        "constraints": {"group": "Palette"},
                    }
                ],
            }
        if command_type == "set_graph_input":
            if params.get("target"):
                return {
                    "graph_identifier": params.get("graph_identifier") or "GraphA",
                    "input_id": params.get("input_id") or params["target"].get("property"),
                    "value": params.get("value"),
                    "value_type": params.get("value_type") or "float",
                    "status": "bound",
                    "target": params["target"],
                    "input": {
                        "id": params.get("input_id") or params["target"].get("property"),
                        "status": "created",
                    },
                }
            return {
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "input_id": params["input_id"],
                "value": params["value"],
                "value_type": params.get("value_type") or "float",
                "status": "updated",
            }
        if command_type == "set_node_comment":
            return {
                "node_id": params["node_id"],
                "parameter_id": "comment",
                "value": params["comment"],
                "status": "updated",
            }
        if command_type == "set_graph_output_size":
            return {
                "graph": params.get("graph_identifier") or "GraphA",
                "width_log2": params["width_log2"],
                "height_log2": params["height_log2"],
                "size": "{}x{}".format(2 ** params["width_log2"], 2 ** params["height_log2"]),
            }
        if command_type == "create_frame":
            return {
                "label": params["label"],
                "node_ids": params.get("node_ids") or [],
                "position": params.get("position") or [0, 0],
                "size": params.get("size") or [480, 320],
            }
        if command_type == "load_package":
            return {
                "loaded": True,
                "package_path": params.get("path")
                or "C:/Program Files/Adobe/packages/{}".format(params["package_name"]),
            }
        if command_type == "get_nested_graph_state":
            return {
                "target": {
                    "graph_identifier": params.get("graph_identifier") or "GraphA",
                    "node_id": params["node_id"],
                    "property": params["property_id"],
                },
                "graph_type": params["graph_type"],
                "exists": True,
                "nodes": [
                    {"id": "uv", "definition": "sbs::function::get_float2", "position": [0, 0]},
                    {"id": "x", "definition": "sbs::function::swizzle1", "position": [160, 0]},
                ],
                "owner_inputs": [],
                "external_references": [],
                "connections": [{"from": "uv", "from_output": "unique_filter_output", "to": "x", "to_input": "vector"}],
                "output": {"node": "x"},
            }
        if command_type == "apply_nested_graph_state":
            return {
                "status": "applied",
                "operation": params["mode"],
                "target": params["state"]["target"],
                "nodes_created": len(params["state"]["nodes"]),
                "connections_created": len(params["state"]["connections"]),
            }
        if command_type == "apply_fx_map_graph_state":
            return {
                "status": "applied",
                "operation": params["mode"],
                "target": params["state"]["target"],
                "graph_type": params["state"]["graph_type"],
                "nodes_created": len(params["state"]["nodes"]),
                "connections_created": len(params["state"]["connections"]),
            }
        if command_type == "apply_fx_map_graph_patch":
            return {
                "status": "patched",
                "operation": params["mode"],
                "target": params["patch"]["target"],
                "graph_type": params["patch"]["graph_type"],
                "operations": params["patch"]["operations"],
            }
        if command_type == "apply_nested_graph_patch":
            return {
                "status": "patched",
                "operation": params["mode"],
                "target": params["patch"]["target"],
                "graph_type": params["patch"]["graph_type"],
                "operations": params["patch"]["operations"],
            }
        if command_type == "get_fx_map_graph_state":
            return {
                "target": {
                    "graph_identifier": params.get("graph_identifier") or "GraphA",
                    "node_id": params["node_id"],
                },
                "graph_type": "SDSBSFxMapGraph",
                "exists": True,
                "nodes": [
                    {"id": "quadrant", "definition": "sbs::fxmap::paramset", "position": [0, 0]},
                ],
                "connections": [],
                "output": {"node": "quadrant"},
            }
        if command_type == "bind_parameter_input":
            return {
                "status": "applied",
                "operation": "bind_parameter_input",
                "target": params["target"],
                "input": {
                    "id": "secondary_barb_amount",
                    "requested_id": "secondary_barb_amount",
                    "actual_property_id": "secondary_barb_amount",
                    "function_reference": "secondary_barb_amount",
                    "value_type": "float",
                    "status": "created",
                },
                "next_tools": [
                    {
                        "tool": "get_nested_graph",
                        "arguments": {
                            "node_id": "303",
                            "property_id": "opacitymult",
                            "graph_identifier": "GraphA",
                            "graph_type": "SDSBSFunctionGraph",
                        },
                    }
                ],
            }
        if command_type == "execute_python":
            return {
                "status": "ok",
                "executed": True,
                "result": {"answer": 42},
                "stdout": "hello\n",
                "stderr": "",
                "message": "",
                "traceback": "",
            }
        if command_type == "diagnostic":
            return {
                "status": "ok",
                "bridge": {"status": "connected"},
                "command_registry": [
                    "create_node",
                    "connect_nodes",
                    "set_parameter",
                    "execute_python",
                ],
            }
        if command_type == "refresh_plugin":
            return {
                "status": "refreshed",
                "reloaded_count": 8,
                "handler_count": 36,
                "handler_commands": ["diagnostic", "refresh_plugin"],
            }
        raise AssertionError(command_type)


class ShapeSplatterFakeClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if command_type == "get_node_info" and params and params.get("node_id") == "splatter_1":
            self.calls.append((command_type, params or {}))
            return {
                "node_id": "splatter_1",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::sbscompgraph_instance",
                "resolved_definition": "sbs::library::shape_splatter_v2",
                "is_library_node": True,
                "position": [100, 200],
                "instance": {"resource_url": "pkg:///shape_splatter_v2"},
                "inputs": [{"id": "pattern_sdf_function", "type": "function"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class EmptyPreviewClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_preview":
            return {}
        return super().command(command_type, params)


class MissingPreviewImagePathClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_preview":
            return {"width": 256, "height": 256}
        return super().command(command_type, params)


class FunctionPropertyNodeClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info" and params and params["node_id"] == "pixel_1":
            return {
                "node_id": "pixel_1",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::pixelprocessor",
                "is_library_node": False,
                "position": [100, 200],
                "inputs": [{"id": "perpixel", "type": "function"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        if command_type == "get_node_info" and params and params["node_id"] == "value_1":
            return {
                "node_id": "value_1",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::valueprocessor",
                "is_library_node": False,
                "position": [100, 200],
                "inputs": [{"id": "function", "type": "function"}, {"id": "outputtype", "value": "float"}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class SdfFunctionNodeClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info" and params and params["node_id"] == "viewer_1":
            return {
                "node_id": "viewer_1",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::library::3d_viewer",
                "is_library_node": True,
                "position": [100, 200],
                "inputs": [
                    {"id": "scene_type", "value": 0, "type": "int"},
                    {"id": "sdf_scene", "type": "float"},
                    {"id": "enable_bounding_frame", "value": False, "type": "bool"},
                    {"id": "bounding_frame_size", "value": [1, 1, 1], "type": "float3"},
                ],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        if command_type == "get_node_info" and params and params["node_id"] == "splatter_1":
            return {
                "node_id": "splatter_1",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::library::shape_splatter_v2",
                "is_library_node": True,
                "position": [320, 200],
                "inputs": [
                    {"id": "shape_type", "value": 2, "type": "int"},
                    {"id": "pattern_sdf_function", "type": "float"},
                    {"id": "sdf_bounding_frame_size", "value": [1, 1, 1], "type": "float3"},
                ],
                "outputs": [{"id": "sdf_color"}, {"id": "sdf_metalness"}, {"id": "sdf_roughness"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class SdfFunctionInstanceNodeClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info" and params and params["node_id"] == "viewer_instance":
            return {
                "node_id": "viewer_instance",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::sbscompgraph_instance",
                "resolved_definition": "sbs::compositing::sbscompgraph_instance",
                "is_library_node": True,
                "instance": {"resource_url": "pkg:///3d_viewer"},
                "position": [100, 200],
                "inputs": [
                    {"id": "scene_type", "value": 0, "type": "int"},
                    {"id": "output", "value": 0, "type": "int"},
                    {"id": "sdf_scene", "type": "function"},
                ],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        if command_type == "get_node_info" and params and params["node_id"] == "splatter_instance":
            return {
                "node_id": "splatter_instance",
                "graph_identifier": params.get("graph_identifier") or "GraphA",
                "definition": "sbs::compositing::sbscompgraph_instance",
                "is_library_node": True,
                "instance": {"resource_url": "pkg:///shape_splatter_v2"},
                "position": [320, 200],
                "inputs": [
                    {"id": "shape_type", "type": "sbs::compositing::shape_type", "value": "2"},
                    {"id": "pattern_sdf_function", "type": "function"},
                ],
                "outputs": [{"id": "sdf_color"}, {"id": "sdf_metalness"}, {"id": "sdf_roughness"}],
                "annotations": [],
                "nested_graph_refs": [],
            }
        return super().command(command_type, params)


class GraphResolvedNodeClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_node_info":
            return {
                "node_id": params["node_id"],
                "graph_identifier": "Substance_graph",
                "resolved_graph_identifier": "Substance_graph",
                "definition": "sbs::compositing::uniform",
                "is_library_node": False,
                "position": [100, 200],
                "inputs": [{"id": "outputcolor", "value": {"r": 0.25, "g": 0.5, "b": 0.75, "a": 1.0}}],
                "outputs": [{"id": "unique_filter_output"}],
                "annotations": [],
            }
        return super().command(command_type, params)


class ErrorPreviewClient(FakeClient):
    def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.calls.append((command_type, params or {}))
        if command_type == "get_preview":
            return {
                "status": "error",
                "message": "Node did not produce a value",
                "node_id": params.get("node_id"),
                "diagnostics": [
                    {
                        "severity": "error",
                        "stage": "render",
                        "message": "root output did not produce a value",
                    }
                ],
            }
        return super().command(command_type, params)


def test_get_scene_info_normalizes_inventory() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_scene_info()

    assert result["application"]["version"] == "16.0.0"
    assert result["package_count"] == 1
    assert result["graph_count"] == 2
    assert result["packages"][0]["graphs"][0]["identifier"] == "GraphA"


def test_list_graphs_flattens_packages() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.list_graphs()

    assert result["graph_count"] == 2
    assert result["graphs"][0]["package_path"] == "E:/materials/test.sbs"


def test_get_graph_state_uses_plugin_graph_info() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(graph_identifier="GraphA")

    assert fake.calls == [
        ("get_graph_info", {"graph_identifier": "GraphA", "node_limit": 500, "include_connections": True})
    ]
    assert result["operation"] == "get_graph"
    assert result["identifier"] == "GraphA"
    assert result["package_path"] == "E:/materials/test.sbs"
    assert result["nodes"][0]["position"] == [1.0, 2.0]
    assert result["connection_count"] == 2
    assert result["graph_outputs"][0]["usage"] == "baseColor"
    assert result["graph_outputs"][0]["usage_source"] == "explicit"
    assert result["connections"][0]["to_node"] == "node_2"
    assert result["canonical_connections"][0] == {
        "from": {"node": "node_1", "output": "unique_filter_output", "output_uid": "12345"},
        "to": {"node": "node_2", "input": "input1"},
    }
    assert "substancedesigner://authoring/contracts/compositing-graph-state" in result["reference_uris"]
    assert {
        "tool": "substance_designer__get_authoring_capabilities",
        "public_name": "get_authoring_capabilities",
        "args": {"graph_ref": {"kind": "package_graph", "graph_identifier": "GraphA"}},
    } in result["next_tools"]


def test_get_node_detail_normalizes_ports() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_node_detail(node_id="node_1", include_raw=True)

    assert result["node_id"] == "node_1"
    assert result["graph_identifier"] is None
    assert result["resolved_graph_identifier"] is None
    assert result["inputs"][0]["id"] == "outputcolor"
    assert result["outputs"][0]["id"] == "unique_filter_output"
    assert result["kind"] == "filter"
    assert result["filter_type"] == "uniform"
    assert result["parameters"][0]["identifier"] == "outputcolor"
    assert result["parameters"][0]["value_type"] == "color"
    assert result["parameters"][0]["semantic_role"] == "color"
    assert "substancedesigner://authoring/node-definition/sbs::compositing::uniform" in result["reference_uris"]
    assert "substancedesigner://authoring/contracts/node-introspection" in result["reference_uris"]
    assert result["raw"]["definition"] == "sbs::compositing::uniform"


def test_get_node_detail_preserves_resolved_graph_identifier() -> None:
    commands = SubstanceDesignerCommands(client=GraphResolvedNodeClient())  # type: ignore[arg-type]

    result = commands.get_node_detail(node_id="1573191775")

    assert result["node_id"] == "1573191775"
    assert result["graph_identifier"] == "Substance_graph"
    assert result["resolved_graph_identifier"] == "Substance_graph"


def test_get_node_detail_exposes_editable_property_graphs_even_when_graph_does_not_exist() -> None:
    commands = SubstanceDesignerCommands(client=FunctionPropertyNodeClient())  # type: ignore[arg-type]

    result = commands.get_node_detail(node_id="pixel_1", graph_identifier="GraphA")

    graph = result["editable_property_graphs"][0]
    assert graph["property_id"] == "perpixel"
    assert graph["exists"] is False
    assert graph["contract"]["kind"] == "pixel_processor"
    assert graph["contract"]["output"]["type"] == "float4"
    assert graph["graph_ref"] == {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "pixel_1",
        "owner_definition": "sbs::compositing::pixelprocessor",
        "property_id": "perpixel",
        "graph_type": "SDSBSFunctionGraph",
    }
    assert result["inputs"][0]["graph_ref"] == graph["graph_ref"]
    assert result["nested_graph_refs"][0]["exists"] is False


def test_get_node_detail_exposes_value_processor_as_partial_known_contract() -> None:
    commands = SubstanceDesignerCommands(client=FunctionPropertyNodeClient())  # type: ignore[arg-type]

    result = commands.get_node_detail(node_id="value_1", graph_identifier="GraphA")

    graph = result["editable_property_graphs"][0]
    assert graph["property_id"] == "function"
    assert graph["contract"]["kind"] == "value_processor"
    assert graph["contract"]["output"]["type"] == "owner_output_type"
    assert graph["contract"]["output"]["resolved_type"] == "float"
    assert graph["contract"]["confidence"] in {"medium", "high"}


def test_get_node_detail_exposes_sdf_graph_surfaces_and_enum_labels() -> None:
    commands = SubstanceDesignerCommands(client=SdfFunctionNodeClient())  # type: ignore[arg-type]

    viewer = commands.get_node_detail(node_id="viewer_1", graph_identifier="GraphA")
    splatter = commands.get_node_detail(node_id="splatter_1", graph_identifier="GraphA")

    viewer_surface = viewer["graph_surfaces"][0]
    assert viewer_surface["property_id"] == "sdf_scene"
    assert viewer_surface["contract_kind"] == "sdf_function"
    assert viewer_surface["exists"] is False
    assert viewer_surface["apply_support"]["patch"]["supported"] is True
    assert viewer_surface["apply_support"]["create_if_missing"]["supported"] is True
    assert viewer_surface["apply_support"]["replace_full_state"]["supported"] is False
    assert viewer_surface["workflow_uri"] == "substancedesigner://authoring/workflows/sdf-function"
    assert viewer_surface["graph_ref"] == {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "viewer_1",
        "owner_definition": "sbs::library::3d_viewer",
        "property_id": "sdf_scene",
        "graph_type": "SDSBSFunctionGraph",
    }
    assert viewer_surface["next_tools"] == [
        {
            "tool": "substance_designer__get_graph",
            "public_name": "get_graph",
            "args": {"graph_ref": viewer_surface["graph_ref"]},
        },
        {
            "tool": "substance_designer__get_authoring_capabilities",
            "public_name": "get_authoring_capabilities",
            "args": {"graph_ref": viewer_surface["graph_ref"]},
        },
    ]
    assert viewer_surface["preview_targets"] == [
        {
            "node_id": "viewer_1",
            "node_output_id": "output",
            "purpose": "preview SDF function silhouette before downstream composition",
        }
    ]
    scene_type = next(item for item in viewer["inputs"] if item["id"] == "scene_type")
    assert scene_type["current_label"] == "SDF"
    assert scene_type["enum_options"][0] == {"value": 0, "id": "SDF", "label": "SDF"}

    splatter_surface = splatter["graph_surfaces"][0]
    assert splatter_surface["property_id"] == "pattern_sdf_function"
    assert splatter_surface["contract_kind"] == "sdf_function"
    assert splatter_surface["contract"]["builtins"]["shape.id"]["readable"] is True
    assert {
        "property_id": "pattern_sdf_function",
        "contract_kind": "sdf_function",
        "exists": False,
        "apply_support": splatter_surface["apply_support"],
        "graph_ref": splatter_surface["graph_ref"],
    } in splatter["editable_graph_refs"]
    assert splatter["sdf_graph_ref"] == splatter_surface["graph_ref"]
    assert splatter_surface["preview_targets"] == [
        {
            "node_id": "splatter_1",
            "node_output_id": "sdf_color",
            "purpose": "verify SDF contribution is readable in Shape Splatter output",
        },
        {
            "node_id": "splatter_1",
            "node_output_id": "height",
            "purpose": "verify scattered SDF height contribution before material composition",
        },
    ]
    shape_type = next(item for item in splatter["inputs"] if item["id"] == "shape_type")
    assert shape_type["current_label"] == "Cube"
    assert shape_type["enum_options"][0] == {"value": 1, "id": "SDF Function", "label": "SDF Function"}


def test_get_node_detail_resolves_sdf_instance_node_to_authoring_surface() -> None:
    commands = SubstanceDesignerCommands(client=SdfFunctionInstanceNodeClient())  # type: ignore[arg-type]

    viewer = commands.get_node_detail(node_id="viewer_instance", graph_identifier="GraphA")

    assert viewer["definition"] == "sbs::compositing::sbscompgraph_instance"
    assert viewer["resolved_definition"] == "sbs::library::3d_viewer"
    assert viewer["runtime_definition"] == "sbs::compositing::sbscompgraph_instance"
    assert viewer["definition_evidence"] == {
        "source": "instance_resource_url",
        "resource_url": "pkg:///3d_viewer",
    }
    surface = viewer["graph_surfaces"][0]
    assert surface["property_id"] == "sdf_scene"
    assert surface["graph_ref"]["owner_definition"] == "sbs::library::3d_viewer"
    scene_type = next(item for item in viewer["inputs"] if item["id"] == "scene_type")
    assert scene_type["current_label"] == "SDF"
    output = next(item for item in viewer["inputs"] if item["id"] == "output")
    assert output["enum_options"][0] == {"value": 0, "label": "Beauty"}
    assert viewer["preview_contract"]["node_output"]["dimension_fields"] == ["resolution"]


def test_get_node_detail_resolves_shape_splatter_instance_enum_metadata() -> None:
    commands = SubstanceDesignerCommands(client=SdfFunctionInstanceNodeClient())  # type: ignore[arg-type]

    splatter = commands.get_node_detail(node_id="splatter_instance", graph_identifier="GraphA")

    assert splatter["resolved_definition"] == "sbs::library::shape_splatter_v2"
    shape_type = next(item for item in splatter["inputs"] if item["id"] == "shape_type")
    assert shape_type["current_label"] == "Cube"
    assert shape_type["enum_options"][0] == {"value": 1, "id": "SDF Function", "label": "SDF Function"}


def test_inspect_node_shapes_runtime_and_static_comparison() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.inspect_node(definition_id="sbs::compositing::blend", graph_identifier="GraphA")

    assert fake.calls[-1] == (
        "inspect_node",
        {"definition_id": "sbs::compositing::blend", "graph_identifier": "GraphA"},
    )
    assert result["status"] == "ok"
    assert result["runtime"]["ports"]["inputs"][0]["id"] == "input1"
    assert result["runtime"]["parameters"][0]["id"] == "intensity"
    assert result["static_reference"]["matched"] is True
    assert result["static_reference"]["uri"].startswith("substancedesigner://authoring/node/atomic/")
    assert result["comparison"]["status"] == "mismatch"
    assert result["static_reference"]["uri"] in result["reference_uris"]
    assert result["evidence"]["source"] == "live_host_introspection"


def test_inspect_node_accepts_existing_node_id() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.inspect_node(node_id=101, graph_identifier="GraphA")

    assert fake.calls[-1] == ("inspect_node", {"node_id": "101", "graph_identifier": "GraphA"})
    assert result["target"] == {"node_id": "101"}
    assert result["evidence"]["node_id"] == "101"
    assert result["evidence"]["temporary_node_id"] is None


def test_inspect_node_reports_unavailable_property_context() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.inspect_node(node_id="1572481176", property_id="thickness_image")

    assert fake.calls[-1] == ("inspect_node", {"node_id": "1572481176", "property_id": "thickness_image"})
    assert result["runtime"]["property_context"] == {"property_id": "thickness_image", "available": False}
    assert "substancedesigner://authoring/contracts/node-introspection" in result["reference_uris"]


def test_inspect_node_validates_single_target_before_bridge_call() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="exactly one"):
        commands.inspect_node()
    with pytest.raises(SubstanceDesignerValidationError, match="exactly one"):
        commands.inspect_node(definition_id="sbs::compositing::blend", resource_url="pkg:///blend")
    with pytest.raises(SubstanceDesignerValidationError, match="node_id"):
        commands.inspect_node(node_id=" ")

    assert fake.calls == []


def test_search_node_reference_uses_static_authoring_resources_without_bridge_call() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.search_node_reference(
        query="spline bend warp curl deform",
        kind="library",
        category="spline",
        graph_scope="SDSBSCompGraph",
        limit=5,
    )

    assert result["operation"] == "search_node_reference"
    assert result["result"]["matches"][0]["slug"] == "spline_warp"
    assert "use_when" in result["result"]["matches"][0]
    assert "substancedesigner://authoring/contracts/reference-first-policy" in result["result"]["reference_uris"]
    assert fake.calls == []


def test_get_preview_uses_resolution_preset_and_wraps_metadata() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_preview(
        graph_identifier="GraphA",
        node_id="node_1",
        node_output_id="unique_filter_output",
        resolution="small",
    )

    assert fake.calls == [
        (
            "get_preview",
            {
                "node_id": "node_1",
                "graph_identifier": "GraphA",
                "node_output_id": "unique_filter_output",
                "channel": "rgba",
                "resolution": "small",
                "timeout_ms": 10000,
            },
        )
    ]
    assert result["operation"] == "get_preview"
    assert result["result"]["image_path"] == "E:/tmp/preview.png"
    assert result["result"]["width"] == 256
    assert result["result"]["cached"] is False


def test_get_preview_without_node_id_captures_graph_3d_view() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_preview(graph_identifier="GraphA", resolution="medium", width=640, height=360)

    assert fake.calls == [
        (
            "get_preview",
            {
                "graph_identifier": "GraphA",
                "channel": "rgba",
                "resolution": "medium",
                "timeout_ms": 10000,
                "width": 640,
                "height": 360,
            },
        )
    ]
    assert result["operation"] == "get_preview"
    assert result["result"]["preview_type"] == "graph_3d_view"
    assert result["result"]["image_path"] == "E:/tmp/graph_preview.png"
    assert result["result"]["width"] == 640
    assert result["result"]["height"] == 360


def test_export_output_forwards_requested_file_path() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.export_output(
        node_id="node_1",
        graph_identifier="GraphA",
        node_output_id="basecolor",
        file_path="E:/exports/basecolor.png",
    )

    assert result["operation"] == "export_output"
    assert result["result"]["file_path"] == "E:/exports/basecolor.png"
    assert fake.calls == [
        (
            "export_output",
            {
                "node_id": "node_1",
                "file_path": "E:/exports/basecolor.png",
                "graph_identifier": "GraphA",
                "node_output_id": "basecolor",
            },
        )
    ]


def test_get_preview_exposes_preview_contract_metadata() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    node_preview = commands.get_preview(node_id="node_1")
    graph_preview = commands.get_preview(graph_identifier="GraphA")

    assert node_preview["result"]["preview_contract"]["node_output"]["dimension_fields"] == ["resolution"]
    assert graph_preview["result"]["preview_contract"]["graph_3d_view"]["dimension_fields"] == [
        "resolution",
        "width",
        "height",
    ]


def test_node_id_inputs_accept_integers_and_forward_strings() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.get_node_detail(node_id=101)
    commands.get_preview(node_id=404)
    commands.connect_nodes(from_node_id=101, to_node_id=202, from_output="unique_filter_output", to_input="input1")
    commands.set_parameter(node_id=202, parameter_id="label", value="Base Color", value_type="string")
    commands.create_frame(label="Base Color", node_ids=[202])
    commands.get_nested_graph_state(node_id=303, property_id="perpixel")

    assert fake.calls == [
        ("get_node_info", {"node_id": "101"}),
        (
            "get_preview",
            {"node_id": "404", "channel": "rgba", "resolution": "small", "timeout_ms": 10000},
        ),
        (
            "connect_nodes",
            {
                "from_node_id": "101",
                "to_node_id": "202",
                "from_output": "unique_filter_output",
                "to_input": "input1",
            },
        ),
        ("set_parameter", {"node_id": "202", "parameter_id": "label", "value": "Base Color", "value_type": "string"}),
        ("create_frame", {"label": "Base Color", "node_ids": ["202"], "description": "", "padding": 160.0}),
        (
            "get_nested_graph_state",
            {"node_id": "303", "property_id": "perpixel", "graph_type": "SDSBSFunctionGraph"},
        ),
    ]


def test_load_package_forwards_path_or_package_name() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    loaded = commands.load_package(path="C:/sd/resources/packages/spline_tools.sbs")

    assert loaded["operation"] == "load_package"
    assert fake.calls == [
        ("load_package", {"path": "C:/sd/resources/packages/spline_tools.sbs"}),
    ]


def test_create_frame_forwards_grouping_payload() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.create_frame(
        label="USER EDIT Splines",
        node_ids=["left", "right"],
        description="Spline controls",
        graph_identifier="GraphA",
        color=[0.2, 0.5, 0.7, 0.18],
    )

    assert result["operation"] == "create_frame"
    assert fake.calls == [
        (
            "create_frame",
            {
                "label": "USER EDIT Splines",
                "node_ids": ["left", "right"],
                "description": "Spline controls",
                "graph_identifier": "GraphA",
                "padding": 160.0,
                "color": [0.2, 0.5, 0.7, 0.18],
            },
        )
    ]


def test_get_preview_rejects_arbitrary_resolution() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="resolution"):
        commands.get_preview(node_id="node_1", resolution="4096")


def test_get_preview_rejects_node_preview_dimensions() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="node_output previews use resolution"):
        commands.get_preview(node_id="node_1", width=640)


def test_get_preview_rejects_empty_host_payload() -> None:
    commands = SubstanceDesignerCommands(client=EmptyPreviewClient())  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerBridgeError, match="no preview payload"):
        commands.get_preview(node_id="node_1")


def test_get_preview_rejects_missing_image_path() -> None:
    commands = SubstanceDesignerCommands(client=MissingPreviewImagePathClient())  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerBridgeError, match="no image_path"):
        commands.get_preview(node_id="node_1")


def test_get_preview_returns_host_diagnostics_for_render_failures() -> None:
    commands = SubstanceDesignerCommands(client=ErrorPreviewClient())  # type: ignore[arg-type]

    result = commands.get_preview(node_id="pixel_1")

    assert result["operation"] == "get_preview"
    assert result["ok"] is False
    assert result["result"]["message"] == "Node did not produce a value"
    assert result["result"]["diagnostics"][0]["stage"] == "render"


def test_get_graph_state_exposes_consumers_producers_and_output_bindings() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_graph_state(graph_identifier="GraphA", include_node_details=True)

    assert result["identifier"] == "GraphA"
    assert result["connection_count"] == 2
    assert result["consumers"]["node_1"][0]["node"] == "node_2"
    assert result["producers"]["out_1"][0]["node"] == "node_2"
    assert result["output_bindings"][0]["label"] == "opacity"
    assert result["graph_outputs"][0]["usage"] == "opacity"
    assert result["connections"][0]["conn_ref_output"] == "12345"
    assert result["connections"][0]["from_output_uid"] == "12345"
    assert result["canonical_connections"][0]["from"]["node"] == "node_1"
    assert result["canonical_connections"][0]["to"]["input"] == "input1"


def test_get_graph_state_filters_package_graph_by_position_bounds() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_identifier="GraphA",
        position_bounds={"min_x": 0, "max_x": 2, "min_y": 0, "max_y": 3},
    )

    assert [node["identifier"] for node in result["nodes"]] == ["node_1"]
    assert result["connections"] == []
    assert result["partial_view"] is True
    assert result["unsafe_as_replace_input"] is True


def test_get_graph_state_filters_nested_graph_marks_partial_view() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "property_id": "perpixel",
        },
        node_ids=["value"],
    )

    assert result["partial_view"] is True
    assert result["unsafe_as_replace_input"] is True


def test_get_graph_state_opens_node_property_graph_from_owner_and_property() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_identifier="GraphA",
        owner_node_id="viewer_1",
        property_id="sdf_scene",
    )

    assert result["graph_ref"] == {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "viewer_1",
        "owner_definition": "sbs::compositing::levels",
        "property_id": "sdf_scene",
        "graph_type": "SDSBSFunctionGraph",
    }
    assert fake.calls[-1] == (
        "get_nested_graph_state",
        {
            "node_id": "viewer_1",
            "property_id": "sdf_scene",
            "graph_identifier": "GraphA",
            "graph_type": "SDSBSFunctionGraph",
        },
    )


def test_get_graph_state_reports_unknown_output_usage_as_info_when_identifier_exists() -> None:
    class UnknownUsageClient(FakeClient):
        def command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            if command_type == "get_node_info" and params and params["node_id"] == "out_1":
                return {
                    "node_id": "out_1",
                    "definition": "sbs::compositing::output",
                    "is_library_node": False,
                    "position": [5, 6],
                    "inputs": [{"id": "inputNodeOutput", "connected_from": ["node_2.unique_filter_output"]}],
                    "outputs": [],
                    "annotations": [
                        {"id": "label", "value": "MCP Pixel Processor Test"},
                        {"id": "identifier", "value": "mcp_pixel_processor_test"},
                    ],
                }
            return super().command(command_type, params)

    commands = SubstanceDesignerCommands(client=UnknownUsageClient())  # type: ignore[arg-type]

    result = commands.get_graph_state(graph_identifier="GraphA", include_node_details=True)

    diagnostics = result["graph_outputs"][0]["diagnostics"]
    assert {
        "severity": "info",
        "code": "output_usage_unset",
        "message": "Graph output usage is unset; identifier and label remain available for caller policy.",
        "source": "canonical_graph",
    } in diagnostics
    assert all(item["code"] != "unresolved_output_usage" for item in diagnostics)


def test_get_graph_state_detail_level_fetches_semantic_node_details() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(graph_identifier="GraphA", detail_level="semantic")

    assert result["detail_level"] == "semantic"
    assert result["nodes"][0]["parameters"][0]["identifier"] == "outputcolor"
    assert result["graph_outputs"][0]["identifier"] == "opacity"
    assert [call[0] for call in fake.calls].count("get_node_info") == 3


def test_get_graph_state_include_parameters_fetches_semantic_parameters() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(graph_identifier="GraphA", include_parameters=True)

    assert result["include_parameters"] is True
    assert result["nodes"][0]["parameters"][0]["identifier"] == "outputcolor"
    assert [call[0] for call in fake.calls].count("get_node_info") == 3


def test_graph_output_trace_and_summary_use_semantic_model() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    outputs = commands.get_graph_outputs(graph_identifier="GraphA")
    trace = commands.trace_output(graph_identifier="GraphA", output_identifier="opacity")
    summary = commands.summarize_graph(graph_identifier="GraphA")

    assert outputs["operation"] == "get_graph_outputs"
    assert outputs["result"]["outputs"][0]["usage"] == "opacity"
    assert trace["operation"] == "trace_output"
    assert trace["result"]["found"] is True
    assert trace["result"]["node_ids"] == ["node_1", "node_2", "out_1"]
    assert summary["operation"] == "summarize_graph"
    assert summary["result"]["outputs"][0]["upstream_node_ids"] == ["node_1", "node_2", "out_1"]
    assert summary["result"]["parameters"][0]["parameters"][0]["semantic_role"] == "color"
    assert "substancedesigner://authoring/contracts/compositing-graph-state" in summary["result"]["reference_uris"]


def test_validate_graph_lineage_reports_reachability_to_output_label() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_lineage(
        graph_identifier="GraphA",
        source_node_id="node_1",
        source_output="unique_filter_output",
        target_output_identifier="opacity",
    )

    assert result["operation"] == "validate_graph_lineage"
    assert result["result"]["valid"] is True
    assert result["result"]["target_node_id"] == "out_1"
    assert result["result"]["path_length"] == 2


def test_validate_graph_lineage_rejects_missing_path() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.validate_graph_lineage(source_node_id="node_2", target_node_id="node_1")

    assert result["result"]["valid"] is False
    assert "does not reach" in result["result"]["errors"][0]


def test_create_graph_wraps_operation_result() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    result = commands.create_graph(graph_name="NewGraph")

    assert result["operation"] == "create_graph"
    assert result["ok"] is True
    assert result["result"]["identifier"] == "NewGraph"


def test_create_package_wraps_package_index_for_follow_up_mutations() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.create_package()

    assert fake.calls == [("create_package", {})]
    assert result["operation"] == "create_package"
    assert result["result"]["package_index"] == 1


def test_create_package_derives_missing_package_index_from_scene_inventory() -> None:
    fake = FakeClient(create_package_returns_index=False)
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.create_package()

    assert fake.calls == [("create_package", {}), ("get_scene_info", {})]
    assert result["operation"] == "create_package"
    assert result["result"]["package_index"] == 0


def test_save_package_wraps_bridge_command() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.save_package(package_index=1, file_path="E:/materials/saved.sbs")

    assert result["operation"] == "save_package"
    assert result["result"]["status"] == "saved"
    assert fake.calls == [("save_package", {"package_index": 1, "file_path": "E:/materials/saved.sbs"})]


def test_create_node_passes_definition_and_position() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.create_node(definition_id="sbs::compositing::uniform", position=[10, 20])

    assert fake.calls == [
        (
            "create_node",
            {
                "definition_id": "sbs::compositing::uniform",
                "position": [10, 20],
            },
        )
    ]
    assert result["result"]["node_id"] == "uniform_1"


def test_create_node_accepts_aliases_and_routes_pkg_resources() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.create_node(node_type="uniform", position={"x": 10, "y": 20})
    routed = commands.create_node(resource_url="pkg:///noise?dependency=1", position={"left": 30, "top": 40})

    assert fake.calls[-2:] == [
        ("create_node", {"definition_id": "sbs::compositing::uniform", "position": [10.0, 20.0]}),
        ("create_instance_node", {"resource_url": "pkg:///noise?dependency=1", "position": [30.0, 40.0]}),
    ]
    assert routed["operation"] == "create_instance_node"


def test_connect_nodes_and_set_parameter_wrap_mutation_results() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]

    connected = commands.connect_nodes(
        from_node_id="a",
        to_node_id="b",
        from_output="unique_filter_output",
        to_input="source",
    )
    parameter = commands.set_parameter(node_id="b", parameter_id="opacity", value=0.5)

    assert connected["operation"] == "connect_nodes"
    assert connected["result"]["to_input"] == "source"
    assert parameter["operation"] == "set_parameter"
    assert parameter["result"]["value"] == 0.5


def test_connect_nodes_accepts_port_objects_and_omitted_ports() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.connect_nodes(
        from_node_id="a",
        to_node_id="b",
        from_output={"id": "unique_filter_output"},
        to_input={"property_id": "source"},
    )
    commands.connect_nodes(from_node_id="a", to_node_id="b")

    assert fake.calls[-2:] == [
        (
            "connect_nodes",
            {
                "from_node_id": "a",
                "to_node_id": "b",
                "from_output": "unique_filter_output",
                "to_input": "source",
            },
        ),
        ("connect_nodes", {"from_node_id": "a", "to_node_id": "b"}),
    ]


def test_set_parameter_accepts_control_aliases() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.set_parameter(
        node_id="b",
        control={"source": {"parameter_id": "blendmode"}},
        value="multiply",
        value_type="enum",
    )

    assert fake.calls[-1] == (
        "set_parameter",
        {"node_id": "b", "parameter_id": "blendmode", "value": "multiply", "value_type": "enum"},
    )


def test_controls_and_graph_inputs_forward_to_bridge() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    controls = commands.list_controls(target={"kind": "node", "node_id": "node_1"})
    updated = commands.set_controls(target={"kind": "node", "node_id": "node_1"}, updates={"id": "gain", "value": 0.8})
    inputs = commands.list_graph_inputs(graph_identifier="GraphA")
    graph_input = commands.set_graph_input(
        graph_identifier="GraphA",
        input_id="color_root",
        value=[0.2, 0.3, 0.4, 1.0],
        value_type="ColorRGBA",
    )

    assert controls["operation"] == "list_controls"
    assert updated["result"]["updated"][0]["id"] == "gain"
    assert inputs["result"]["inputs"][0]["id"] == "color_root"
    assert graph_input["result"]["value_type"] == "ColorRGBA"
    assert fake.calls[-4:] == [
        ("list_controls", {"target": {"kind": "node", "node_id": "node_1"}}),
        ("set_controls", {"target": {"kind": "node", "node_id": "node_1"}, "updates": [{"id": "gain", "value": 0.8}]}),
        ("list_graph_inputs", {"graph_identifier": "GraphA"}),
        (
            "set_graph_input",
            {
                "input_id": "color_root",
                "value": [0.2, 0.3, 0.4, 1.0],
                "value_type": "ColorRGBA",
                "graph_identifier": "GraphA",
                "mode": "replace",
            },
        ),
    ]


def test_set_graph_input_forwards_target_binding_options() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    graph_input = commands.set_graph_input(
        input_id="shaft_width",
        value=0.25,
        value_type="float",
        target={"graph_identifier": "GraphA", "node_id": 303, "property": "opacitymult"},
        description="Shaft width",
        min=0,
        max=1,
        step=0.01,
    )

    assert graph_input["result"]["status"] == "bound"
    assert fake.calls[-1] == (
        "set_graph_input",
        {
            "input_id": "shaft_width",
            "value": 0.25,
            "value_type": "float",
            "target": {"graph_identifier": "GraphA", "node_id": 303, "property": "opacitymult"},
            "mode": "replace",
            "description": "Shaft width",
            "min": 0,
            "max": 1,
            "step": 0.01,
        },
    )


def test_editor_vectors_colors_and_output_size_accept_common_objects() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    commands.move_node(node_id="node_1", position={"x": 4, "y": 8})
    commands.duplicate_node(node_id="node_1", offset={"left": 12, "top": 16})
    commands.create_frame(label="Frame", size={"width": 400, "height": 300}, color={"r": 0.1, "g": 0.2, "b": 0.3})
    output_size = commands.set_graph_output_size(resolution="2048x1024")

    assert fake.calls[-4:] == [
        ("move_node", {"node_id": "node_1", "position": [4.0, 8.0]}),
        ("duplicate_node", {"node_id": "node_1", "offset": [12.0, 16.0]}),
        (
            "create_frame",
            {
                "label": "Frame",
                "description": "",
                "size": [400.0, 300.0],
                "padding": 160.0,
                "color": [0.1, 0.2, 0.3, 1.0],
            },
        ),
        ("set_graph_output_size", {"width_log2": 11, "height_log2": 10}),
    ]
    assert output_size["result"]["size"] == "2048x1024"


def test_metadata_mutation_commands_forward_to_bridge() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    comment = commands.set_node_comment(node_id=101, comment="Comment")

    assert comment["result"]["value"] == "Comment"


def test_nested_graph_state_tools_validate_diff_and_apply() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    desired = _nested_graph_state()

    validation = commands.validate_nested_graph_state(state=desired)
    diff = commands.diff_nested_graph_state(
        current_state={
            **desired,
            "nodes": desired["nodes"][:1],
            "connections": [],
            "output": None,
        },
        desired_state=desired,
    )
    applied = commands.apply_nested_graph_state(state=desired, mode="replace")

    assert validation["operation"] == "validate_nested_graph_state"
    assert validation["result"]["valid"] is True
    assert diff["operation"] == "diff_nested_graph_state"
    assert diff["result"]["status"] == "changed"
    assert diff["result"]["requires_replace"] is True
    assert applied["operation"] == "apply_nested_graph_state"
    assert applied["result"]["nodes_created"] == 2
    assert fake.calls == [("apply_nested_graph_state", {"state": desired, "mode": "replace"})]


def test_apply_graph_change_for_fx_map_graph_rejects_full_replace() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    change = {
        "replace_all": True,
        "nodes": [
            {
                "id": "draw_pattern",
                "definition": "sbs::fxmap::paramset",
                "parameters": {"patterntype": 0},
            }
        ],
        "connections": [],
        "output": {"node": "draw_pattern"},
    }

    result = commands.apply_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": 303},
        change=change,
    )

    assert result["result"]["applied"] is False
    assert result["result"]["validation"]["operation_plan"]["strategy"] == "replace_fx_map_graph"
    assert result["result"]["errors"][0]["code"] == "full_replace_not_supported_by_apply_graph_change"
    assert fake.calls == []


def test_apply_graph_change_for_fx_map_graph_operations_uses_patch_command() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    change = {
        "operations": [
            {
                "op": "set_parameter",
                "node": "1573143990",
                "parameter": "patternsize",
                "value": [0.2, 0.2],
                "value_type": "float2",
            }
        ]
    }

    result = commands.apply_graph_change(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": 303},
        change=change,
    )

    assert result["result"]["applied"] is True
    assert result["result"]["execution_trace"][0]["operation"] == "apply_fx_map_graph_patch"
    assert fake.calls == [
        (
            "apply_fx_map_graph_patch",
            {
                "patch": {
                    "graph_kind": "fx_map_graph",
                    "target": {"graph_identifier": "GraphA", "node_id": "303"},
                    "graph_type": "SDSBSFxMapGraph",
                    "operations": change["operations"],
                },
                "mode": "patch",
            },
        )
    ]


def test_replace_graph_state_requires_current_hash_before_nested_replace() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    graph_ref = {
        "kind": "node_property_graph",
        "parent_graph": "GraphA",
        "owner_node_id": "pixel_1",
        "owner_definition": "sbs::compositing::pixelprocessor",
        "property_id": "perpixel",
    }
    current = commands.get_graph_state(graph_ref=graph_ref)
    replacement = {
        "nodes": [{"id": "value", "definition": "sbs::function::const_float1"}],
        "connections": [],
        "output": {"node": "value"},
    }

    result = commands.replace_graph_state(
        graph_ref=graph_ref,
        state=replacement,
        expected_current_hash=current["state_hash"],
    )

    assert result["operation"] == "replace_graph_state"
    assert result["result"]["replace_strategy"] == "replace_property_graph"
    assert fake.calls[-1] == (
        "apply_nested_graph_state",
        {
            "state": {
                "target": {"graph_identifier": "GraphA", "node_id": "pixel_1", "property": "perpixel"},
                "graph_type": "SDSBSFunctionGraph",
                "nodes": replacement["nodes"],
                "connections": [],
                "output": {"node": "value"},
            },
            "mode": "replace",
        },
    )


def test_replace_graph_state_rejects_stale_hash_without_mutation() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="state hash"):
        commands.replace_graph_state(
            graph_ref={
                "kind": "node_property_graph",
                "parent_graph": "GraphA",
                "owner_node_id": "pixel_1",
                "owner_definition": "sbs::compositing::pixelprocessor",
                "property_id": "perpixel",
            },
            state={"nodes": [], "connections": [], "output": None},
            expected_current_hash="stale",
        )

    assert [call[0] for call in fake.calls] == ["get_nested_graph_state"]


def test_validate_graph_change_infers_instance_owner_definition_from_node_id() -> None:
    fake = ShapeSplatterFakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.validate_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "splatter_1",
            "property_id": "pattern_sdf_function",
        },
        change={
            "nodes": [{"id": "rock", "definition": "sbs::function-library::3d_sdf_rock"}],
            "connections": [],
            "output": "rock",
        },
    )

    assert result["result"]["valid"] is True
    assert result["result"]["graph_ref"]["owner_definition"] == "sbs::library::shape_splatter_v2"
    assert fake.calls == [
        (
            "get_node_info",
            {
                "node_id": "splatter_1",
                "graph_identifier": "GraphA",
            },
        )
    ]


def test_apply_graph_change_compacts_large_success_payloads() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    nodes = [
        {"id": f"value_{index}", "definition": "sbs::function::const_float4", "parameters": {"value": index}}
        for index in range(50)
    ]

    result = commands.apply_graph_change(
        graph_ref={
            "kind": "node_property_graph",
            "parent_graph": "GraphA",
            "owner_node_id": "pixel_1",
            "owner_definition": "sbs::compositing::pixelprocessor",
            "property_id": "perpixel",
        },
        change={"nodes": nodes, "connections": [], "output": "value_49"},
    )

    payload = result["result"]
    assert payload["applied"] is True
    assert payload["apply_strategy"] == "patch_property_graph"
    assert payload["validation"]["change_summary"] == {
        "operation_count": 0,
        "node_count": 50,
        "connection_count": 0,
        "sets_output": True,
        "full_replace_requested": False,
    }
    assert "change" not in payload["validation"]
    assert "capabilities" not in payload["validation"]
    assert "patch" not in payload
    assert "operations" not in payload["result"]
    assert "state" not in payload


def test_get_graph_for_fx_map_graph_reads_referenced_fx_map_graph() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_graph_state(
        graph_ref={"kind": "fx_map_graph", "graph_identifier": "GraphA", "owner_node_id": 303}
    )

    assert result["graph_ref"] == {
        "kind": "fx_map_graph",
        "graph_identifier": "GraphA",
        "owner_node_id": "303",
        "graph_type": "SDSBSFxMapGraph",
    }
    assert result["graph_context"]["graph_kind"] == "fx_map_graph"
    assert result["graph_type"] == "SDSBSFxMapGraph"
    assert result["exists"] is True
    assert result["nodes"][0]["definition"] == "sbs::fxmap::paramset"
    assert fake.calls == [
        (
            "get_fx_map_graph_state",
            {
                "node_id": "303",
                "graph_identifier": "GraphA",
            },
        )
    ]


def test_nested_graph_state_target_node_id_accepts_integer() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["target"]["node_id"] = 303

    validation = commands.validate_nested_graph_state(state=desired)

    assert validation["result"]["valid"] is True
    assert validation["result"]["state"]["target"]["node_id"] == "303"


def test_nested_graph_state_accepts_legacy_input_nodes() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["nodes"][0] = {
        "id": "feather_length",
        "node_type": "input",
        "value_type": "float2",
        "default": [0.5, 0.25],
        "position": [0, 0],
    }
    desired["connections"][0]["from"] = "feather_length"

    result = commands.validate_nested_graph_state(state=desired)

    assert result["result"]["valid"] is True
    assert result["result"]["state"]["nodes"][0]["definition"] == "sbs::function::get_float2"
    assert result["result"]["state"]["nodes"][0]["parameters"]["__constant__"]["value"] == "feather_length"
    assert result["result"]["state"]["external_references"][0]["id"] == "feather_length"


def test_nested_graph_state_accepts_color_input_nodes_as_float4_getters() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["nodes"][0] = {
        "id": "color_root",
        "node_type": "input",
        "value_type": "ColorRGBA",
        "default": {"r": 0.1, "g": 0.2, "b": 0.3, "a": 1.0},
    }
    desired["connections"][0]["from"] = "color_root"

    result = commands.validate_nested_graph_state(state=desired)

    assert result["result"]["valid"] is True
    assert result["result"]["state"]["nodes"][0]["definition"] == "sbs::function::get_float4"
    assert result["result"]["state"]["nodes"][0]["parameters"]["__constant__"]["value"] == "color_root"
    assert result["result"]["state"]["external_references"][0]["value_type"] == "color"


@pytest.mark.parametrize(
    "value_type",
    [
        "bool",
        "color",
        "ColorRGBA",
        "float",
        "float2",
        "float3",
        "float4",
        "int",
        "int2",
        "int3",
        "int4",
        "string",
    ],
)
def test_nested_graph_state_accepts_external_reference_value_types(value_type: str) -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["external_references"] = [{"id": "external_value", "value_type": value_type}]

    validation = commands.validate_nested_graph_state(state=desired)

    assert validation["result"]["valid"] is True


def test_nested_graph_state_accepts_designer_level_external_get_node_references() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["nodes"][0] = {
        "id": "external",
        "definition": "sbs::function::get_float1",
        "parameters": {"__constant__": {"value": "#external_value", "type": "string"}},
    }
    desired["external_references"] = [{"id": "external_value", "value_type": "float"}]
    desired["connections"] = [
        {"from": "external", "from_output": "unique_filter_output", "to": "x", "to_input": "vector"}
    ]

    validation = commands.validate_nested_graph_state(state=desired)

    assert validation["result"]["valid"] is True
    assert validation["result"]["state"]["nodes"][0]["parameters"]["__constant__"]["value"] == "external_value"


def test_nested_graph_state_normalizes_hash_prefixed_input_references() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["nodes"][0] = {
        "id": "#external_value",
        "node_type": "input",
        "value_type": "float",
    }
    desired["external_references"] = [{"id": "#secondary_value", "value_type": "float"}]
    desired["connections"][0]["from"] = "external_value"

    validation = commands.validate_nested_graph_state(state=desired)

    assert validation["result"]["valid"] is True
    state = validation["result"]["state"]
    assert state["nodes"][0]["id"] == "external_value"
    assert state["nodes"][0]["parameters"]["__constant__"]["value"] == "external_value"
    assert state["external_references"] == [
        {"id": "secondary_value", "requested_id": "#secondary_value", "value_type": "float"},
        {"id": "external_value", "requested_id": "#external_value", "value_type": "float"},
    ]


def test_nested_graph_state_diff_includes_external_references() -> None:
    commands = SubstanceDesignerCommands(client=FakeClient())  # type: ignore[arg-type]
    desired = _nested_graph_state()
    desired["external_references"] = [{"id": "external_value", "value_type": "float"}]

    diff = commands.diff_nested_graph_state(current_state=_nested_graph_state(), desired_state=desired)

    assert {"type": "add_external_references", "ids": ["external_value"]} in diff["result"]["changes"]
    assert diff["result"]["requires_replace"] is True


def test_get_and_diff_nested_graph_state_can_read_current_state_from_bridge() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    state = commands.get_nested_graph_state(node_id="pixel_1", property_id="perpixel", graph_identifier="GraphA")
    diff = commands.diff_nested_graph_state(desired_state=_nested_graph_state())

    assert state["operation"] == "get_nested_graph_state"
    assert state["result"]["target"]["property"] == "perpixel"
    assert "substancedesigner://authoring/contracts/nested-graph-state" in state["result"]["reference_uris"]
    assert diff["result"]["valid"] is True
    assert fake.calls == [
        (
            "get_nested_graph_state",
            {
                "node_id": "pixel_1",
                "property_id": "perpixel",
                "graph_identifier": "GraphA",
                "graph_type": "SDSBSFunctionGraph",
            },
        ),
        (
            "get_nested_graph_state",
            {
                "node_id": "pixel_1",
                "property_id": "perpixel",
                "graph_identifier": "GraphA",
                "graph_type": "SDSBSFunctionGraph",
            },
        ),
    ]


def test_get_pixel_processor_graph_uses_nested_graph_target_contract() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.get_pixel_processor_graph(node_id="pixel_1", graph_identifier="GraphA")

    assert result["operation"] == "get_pixel_processor_graph"
    assert result["result"]["target"]["node_id"] == "pixel_1"
    assert result["result"]["target"]["property"] == "perpixel"
    assert result["result"]["pixel_processor"]["property"] == "perpixel"
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


def test_invalid_nested_graph_state_is_rejected_before_bridge_call() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.validate_nested_graph_state(state={})
    with pytest.raises(SubstanceDesignerValidationError, match="nested graph state"):
        commands.apply_nested_graph_state(state={})

    assert result["result"]["valid"] is False
    assert fake.calls == []


def test_bind_parameter_input_forwards_target_and_input() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.bind_parameter_input(
        target={"graph_identifier": "GraphA", "node_id": 303, "property": "opacitymult"},
        input={"id": "secondary_barb_amount", "value_type": "float", "default": 0.5},
    )

    assert result["operation"] == "bind_parameter_input"
    assert result["result"]["input"]["function_reference"] == "secondary_barb_amount"
    assert result["result"]["next_tools"][0] == {
        "tool": "substance_designer__get_graph",
        "public_name": "get_graph",
        "args": {
            "graph_ref": {
                "kind": "node_property_graph",
                "owner_node_id": "303",
                "property_id": "opacitymult",
                "parent_graph": "GraphA",
                "graph_type": "SDSBSFunctionGraph",
            }
        },
    }
    assert fake.calls == [
        (
            "bind_parameter_input",
            {
                "target": {"graph_identifier": "GraphA", "node_id": 303, "property": "opacitymult"},
                "input": {"id": "secondary_barb_amount", "value_type": "float", "default": 0.5},
                "mode": "replace",
            },
        )
    ]


def test_execute_python_forwards_code_and_wraps_result() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.execute_python(code='result = {"answer": 42}', strict_json=True)

    assert fake.calls[-1] == ("execute_python", {"code": 'result = {"answer": 42}', "strict_json": True})
    assert result["operation"] == "execute_python"
    assert result["status"] == "ok"
    assert result["executed"] is True
    assert result["python_result"] == {"answer": 42}
    assert result["stdout"] == "hello\n"
    assert result["execution_message"] == ""


def test_diagnostic_hides_internal_bridge_command_registry_by_default() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]
    action_ids = public_tool_action_ids()

    result = commands.diagnostic()

    assert result["operation"] == "diagnostic"
    assert result["result"]["status"] == "ok"
    assert "command_registry" not in result["result"]
    assert result["result"]["internal_command_count"] == 4
    assert result["result"]["public_mutation_tools"] == [
        "substance_designer__apply_graph_change",
        "substance_designer__replace_graph_state",
    ]
    assert result["result"]["public_tool_surface"]["complete"] is True
    assert result["result"]["public_tool_surface"]["count"] == len(action_ids)
    assert len(result["result"]["public_tool_surface"]["tools"]) == len(action_ids)
    assert [
        item["public_name"] for item in result["result"]["public_tool_surface"]["tools"]
    ] == list(action_ids)
    assert {
        item["public_name"]: item["tool"] for item in result["result"]["public_tool_surface"]["tools"]
    } == action_ids
    assert {
        item["public_name"]: item["exposed_name"] for item in result["result"]["public_tool_surface"]["tools"]
    } == {name: name for name in action_ids}
    assert {
        item["public_name"] for item in result["result"]["public_tool_surface"]["tools"]
    } >= {
        "get_graph",
        "get_authoring_plan",
        "get_authoring_capabilities",
        "validate_graph_change",
        "apply_graph_change",
        "get_preview",
    }
    assert {
        item["exposed_name"] for item in result["result"]["public_tool_surface"]["tools"]
    } >= {
        "get_graph",
        "get_authoring_plan",
        "get_authoring_capabilities",
        "validate_graph_change",
        "apply_graph_change",
        "get_preview",
    }
    assert "critical_workflow_tools" not in result["result"]["public_tool_surface"]
    assert result["result"]["public_tool_surface"]["orientation_tools"] == [
        {
            "public_name": "get_graph",
            "exposed_name": "get_graph",
            "tool": "substance_designer__get_graph",
        },
        {
            "public_name": "get_node",
            "exposed_name": "get_node",
            "tool": "substance_designer__get_node",
        },
        {
            "public_name": "get_preview",
            "exposed_name": "get_preview",
            "tool": "substance_designer__get_preview",
        },
    ]
    assert result["result"]["public_tool_surface"]["planning_tools"] == [
        {
            "public_name": "get_authoring_plan",
            "exposed_name": "get_authoring_plan",
            "tool": "substance_designer__get_authoring_plan",
        },
    ]
    assert result["result"]["public_tool_surface"]["later_phase_tools"] == [
        {
            "public_name": "validate_graph_change",
            "exposed_name": "validate_graph_change",
            "tool": "substance_designer__validate_graph_change",
        },
        {
            "public_name": "apply_graph_change",
            "exposed_name": "apply_graph_change",
            "tool": "substance_designer__apply_graph_change",
        },
        {
            "public_name": "get_authoring_capabilities",
            "exposed_name": "get_authoring_capabilities",
            "tool": "substance_designer__get_authoring_capabilities",
        },
    ]


def test_refresh_plugin_forwards_to_bridge_and_wraps_result() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    result = commands.refresh_plugin()

    assert fake.calls[-1] == ("refresh_plugin", {})
    assert result["operation"] == "refresh_plugin"
    assert result["result"]["status"] == "refreshed"
    assert result["result"]["handler_count"] == 36


def test_required_authoring_inputs_are_validated_before_bridge_call() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="definition_id"):
        commands.create_node(definition_id="")

    with pytest.raises(SubstanceDesignerValidationError, match="position"):
        commands.move_node(node_id="node_1", position=[1])

    with pytest.raises(SubstanceDesignerValidationError, match="package_index"):
        commands.create_graph(graph_name="GraphA", package_index=-1)

    with pytest.raises(SubstanceDesignerValidationError, match="graph_identifier"):
        commands.create_node(definition_id="sbs::compositing::uniform", graph_identifier=" ")

    with pytest.raises(SubstanceDesignerValidationError, match="file_path"):
        commands.create_package(file_path=" ")

    assert fake.calls == []


def test_reference_inputs_are_validated_before_bridge_call() -> None:
    fake = FakeClient()
    commands = SubstanceDesignerCommands(client=fake)  # type: ignore[arg-type]

    with pytest.raises(SubstanceDesignerValidationError, match="node_spacing_x"):
        commands.arrange_nodes(node_spacing_x=0)

    assert fake.calls == []


def _nested_graph_state() -> dict[str, Any]:
    return {
        "target": {
            "graph_identifier": "GraphA",
            "node_id": "pixel_1",
            "property": "perpixel",
        },
        "graph_type": "SDSBSFunctionGraph",
        "nodes": [
            {"id": "uv", "definition": "sbs::function::get_float2", "position": [0, 0]},
            {
                "id": "x",
                "definition": "sbs::function::swizzle1",
                "position": [160, 0],
                "parameters": {"components": {"value": "x", "type": "string"}},
            },
        ],
        "external_references": [],
        "connections": [{"from": "uv", "from_output": "unique_filter_output", "to": "x", "to_input": "vector"}],
        "output": {"node": "x"},
    }
