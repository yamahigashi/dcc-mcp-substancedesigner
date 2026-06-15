"""Tests for stable MCP-facing schema normalization."""

from __future__ import annotations

from dcc_mcp_substancedesigner.schema import (
    normalize_graph_summary,
    normalize_node_detail,
    normalize_operation_result,
    normalize_packages,
    normalize_scene_info,
)


def test_scene_info_derives_counts_from_normalized_packages() -> None:
    result = normalize_scene_info(
        {
            "sd_version": "16.0.0",
            "plugin_version": "3.3.0",
            "current_graph_node_count": "4",
            "packages": [
                {"file_path": "", "graphs": [{"identifier": "A", "node_count": "2"}, {"ignored": object()}]},
                {"error": "broken package", "graphs": "not-a-list"},
                "not-a-package",
            ],
        }
    )

    assert result["application"]["version"] == "16.0.0"
    assert result["package_count"] == 2
    assert result["graph_count"] == 1
    assert result["current_graph_node_count"] == 4
    assert result["packages"][0]["is_saved"] is False
    assert result["packages"][1]["error"] == "broken package"


def test_package_filter_keeps_exact_package_path_only() -> None:
    result = normalize_packages(
        {
            "packages": [
                {"file_path": "A.sbs", "graphs": [{"identifier": "GraphA"}]},
                {"file_path": "B.sbs", "graphs": [{"identifier": "GraphB"}]},
            ]
        },
        package_path="B.sbs",
    )

    assert result["package_count"] == 1
    assert result["packages"][0]["file_path"] == "B.sbs"
    assert result["packages"][0]["graphs"][0]["identifier"] == "GraphB"


def test_graph_summary_normalizes_positions_connections_and_boolean_strings() -> None:
    result = normalize_graph_summary(
        {
            "identifier": "GraphA",
            "node_count": "3",
            "node_limit": "2",
            "truncated": "false",
            "nodes": [
                {
                    "identifier": "node_dict",
                    "definition": "sbs::compositing::blend",
                    "position": {"x": "1.5", "y": 2},
                    "connections": [{"input": "source", "from_node": "a", "from_output": "out"}, "bad"],
                },
                {
                    "identifier": "node_tuple",
                    "definition": "sbs::compositing::uniform",
                    "position": (3, "4.25"),
                },
            ],
        }
    )

    assert result["node_count"] == 3
    assert result["node_limit"] == 2
    assert result["truncated"] is False
    assert result["returned_node_count"] == 2
    assert result["nodes"][0]["position"] == [1.5, 2.0]
    assert result["nodes"][0]["connections"] == [{"input": "source", "from_node": "a", "from_output": "out"}]
    assert result["connections"] == [
        {"from_node": "a", "from_output": "out", "to_node": "node_dict", "to_input": "source"}
    ]
    assert result["canonical_connections"] == [
        {"from": {"node": "a", "output": "out"}, "to": {"node": "node_dict", "input": "source"}}
    ]
    assert result["connection_count"] == 1
    assert result["nodes"][1]["position"] == [3.0, 4.25]


def test_node_detail_normalizes_ports_and_missing_collections() -> None:
    result = normalize_node_detail(
        {
            "node_id": "node_1",
            "definition": "pkg:///library",
            "is_library_node": 1,
            "position": {"0": "8", "1": "-2.5"},
            "inputs": [{"id": "input1", "connected_from": ["a.out"]}, "bad"],
            "outputs": None,
            "annotations": [{"id": "label", "value": "Base"}],
            "note": None,
        }
    )

    assert result["is_library_node"] is True
    assert result["position"] == [8.0, -2.5]
    assert result["inputs"] == [{"id": "input1", "connected_from": ["a.out"]}]
    assert result["outputs"] == []
    assert result["annotations"] == [{"id": "label", "value": "Base"}]
    assert result["note"] == ""


def test_node_detail_extracts_output_usage_from_structured_usages_annotation() -> None:
    result = normalize_node_detail(
        {
            "node_id": "out_1",
            "definition": "sbs::compositing::output",
            "is_library_node": False,
            "annotations": [
                {"id": "identifier", "value": "out"},
                {"id": "label", "value": "Output"},
                {"id": "usages", "value": [{"name": "baseColor", "components": "RGBA", "color_space": "sRGB"}]},
            ],
        }
    )

    assert result["output_binding"]["usage"] == "baseColor"
    assert result["output_binding"]["usage_source"] == "explicit"


def test_operation_result_wraps_non_object_payloads() -> None:
    assert normalize_operation_result("diagnostic", ["ok"]) == {
        "operation": "diagnostic",
        "ok": True,
        "result": {"value": ["ok"]},
    }
