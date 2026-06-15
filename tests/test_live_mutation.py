"""Live mutation checks for a running Substance Designer plugin bridge."""

from __future__ import annotations

import os
import time

import pytest

from dcc_mcp_substancedesigner.commands import commands_from_env

pytestmark = pytest.mark.integration


def _require_live_mutation() -> None:
    if os.environ.get("DCC_MCP_SUBSTANCEDESIGNER_LIVE") != "1":
        pytest.skip("Set DCC_MCP_SUBSTANCEDESIGNER_LIVE=1 to run live integration tests")


def _create_disposable_package(commands):
    package = commands.create_package()
    package_index = package["result"].get("package_index")
    if package_index is None:
        pytest.fail("create_package did not return package_index; update the Substance Designer plugin")
    return package_index


def test_live_create_and_delete_disposable_graph() -> None:
    _require_live_mutation()
    commands = commands_from_env()
    package_index = _create_disposable_package(commands)
    graph_name = f"MCP_Integration_{int(time.time())}"

    created = commands.create_graph(graph_name=graph_name, package_index=package_index)
    graph_identifier = created["result"]["identifier"]

    try:
        state = commands.get_graph_state(graph_identifier=graph_identifier)
        assert state["identifier"] == graph_identifier
    finally:
        deleted = commands.delete_graph(graph_identifier=graph_identifier, package_index=package_index)
        assert deleted["operation"] == "delete_graph"


def test_live_mutate_disposable_graph_node_and_settings() -> None:
    _require_live_mutation()
    commands = commands_from_env()
    package_index = _create_disposable_package(commands)
    graph_name = f"MCP_Mutation_{int(time.time())}"

    created = commands.create_graph(graph_name=graph_name, package_index=package_index)
    graph_identifier = created["result"]["identifier"]

    try:
        opened = commands.open_graph(graph_identifier=graph_identifier)
        sized = commands.set_graph_output_size(
            graph_identifier=graph_identifier,
            width_log2=8,
            height_log2=8,
        )
        output = commands.create_output_node(
            graph_identifier=graph_identifier,
            usage="baseColor",
            position=[0, 0],
        )
        node_id = output["result"]["node_id"]
        moved = commands.move_node(
            graph_identifier=graph_identifier,
            node_id=node_id,
            position=[128, 64],
        )
        detail = commands.get_node_detail(graph_identifier=graph_identifier, node_id=node_id)
        deleted_node = commands.delete_node(graph_identifier=graph_identifier, node_id=node_id)

        assert opened["operation"] == "open_graph"
        assert sized["operation"] == "set_graph_output_size"
        assert output["operation"] == "create_output_node"
        assert moved["result"]["position"] == [128.0, 64.0]
        assert detail["node_id"] == node_id
        assert deleted_node["result"]["deleted"] == node_id
    finally:
        deleted_graph = commands.delete_graph(graph_identifier=graph_identifier, package_index=package_index)
        assert deleted_graph["operation"] == "delete_graph"
