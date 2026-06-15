"""Host API context helpers for bridge command handlers."""

from __future__ import annotations

from typing import cast

import sd

from ..host.host_resources import find_node as find_host_node
from ..host.host_resources import resolve_graph as resolve_host_graph
from ..host.host_resources import resolve_package as resolve_host_package
from ..host.host_types import (
    HostApplication,
    HostGraph,
    HostNode,
    HostPackage,
    HostPackageManager,
    HostUiManager,
)
from ..json_types import JsonMap, JsonValue
from ..nested_graph.nested_graph_types import MutableNestedGraph, MutableNestedNode
from .command_nested_helpers import safe_nested_connect, set_nested_node_params


class CommandHostMixin:
    """Host API helper methods shared across command mixins."""

    def _app(self) -> HostApplication:
        """Return the Substance Designer application handle."""
        return host_application()

    def _pkg_mgr(self) -> HostPackageManager:
        """Return the host package manager."""
        return package_manager()

    def _ui_mgr(self) -> HostUiManager:
        """Return the host UI manager."""
        return ui_manager()

    def _get_sd_version(self) -> str:
        """Return the host Substance Designer version."""
        return sd_version()

    def _resolve_package(self, package_index: int = 0, package_path: str | None = None) -> HostPackage:
        """Resolve a host package by index or path."""
        return resolve_host_package(self._pkg_mgr(), package_index, package_path)

    def _resolve_graph(self, graph_identifier: str | None = None) -> HostGraph:
        """Resolve a graph by identifier or host editor context."""
        return resolve_host_graph(self._pkg_mgr(), self._ui_mgr(), graph_identifier)

    def _find_node(self, graph: HostGraph, node_id: JsonValue) -> HostNode:
        """Find a node in a graph by identifier."""
        return find_host_node(graph, node_id)

    def _set_node_params(self, node: MutableNestedNode, params: JsonMap) -> JsonMap:
        """Apply parameter values to a node."""
        return set_nested_node_params(node, params)

    def _safe_connect(
        self,
        graph: MutableNestedGraph,
        from_node: MutableNestedNode,
        from_out: str,
        to_node: MutableNestedNode,
        to_in: str,
    ) -> None:
        """Connect nodes with port validation."""
        safe_nested_connect(graph, from_node, from_out, to_node, to_in)


def host_application() -> HostApplication:
    """Return the Substance Designer application handle."""
    return cast(HostApplication, sd.getContext().getSDApplication())


def package_manager() -> HostPackageManager:
    """Return the host package manager."""
    return host_application().getPackageMgr()


def ui_manager() -> HostUiManager:
    """Return the host UI manager."""
    return host_application().getUIMgr()


def sd_version() -> str:
    """Return the host Substance Designer version."""
    try:
        return host_application().getVersion()
    except Exception:
        return "unknown"
