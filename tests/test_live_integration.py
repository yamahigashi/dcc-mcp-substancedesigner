"""Live integration checks for a running Substance Designer plugin bridge."""

from __future__ import annotations

import os

import pytest

from dcc_mcp_substancedesigner.commands import commands_from_env

pytestmark = pytest.mark.integration


def _require_live() -> None:
    if os.environ.get("DCC_MCP_SUBSTANCEDESIGNER_LIVE") != "1":
        pytest.skip("Set DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 to run live Substance Designer integration tests")


def test_live_diagnostic_bridge() -> None:
    _require_live()

    result = commands_from_env().diagnostic()

    assert result["operation"] == "diagnostic"
    assert result["ok"] is True
    assert "sd_running" in result["result"]


def test_live_scene_info_bridge() -> None:
    _require_live()

    result = commands_from_env().get_scene_info(include_raw=True)

    assert result["application"]["name"] == "Substance 3D Designer"
    assert "packages" in result
    assert "raw" in result


def test_live_read_only_graph_inventory_chain() -> None:
    _require_live()
    commands = commands_from_env()

    graphs = commands.list_graphs()

    assert graphs["graph_count"] >= 0

    if graphs["graph_count"] == 0:
        pytest.skip("No graphs are loaded in the live Substance Designer session")

    graph_identifier = graphs["graphs"][0]["identifier"]
    state = commands.get_graph_state(graph_identifier=graph_identifier, node_limit=25)

    assert state["identifier"] == graph_identifier
    assert state["returned_node_count"] <= 25

    if state["returned_node_count"] == 0:
        pytest.skip("Selected live graph has no nodes to inspect")

    node_id = state["nodes"][0]["identifier"]
    detail = commands.get_node_detail(graph_identifier=graph_identifier, node_id=node_id)

    assert detail["node_id"] == node_id
    assert "inputs" in detail
    assert "outputs" in detail
