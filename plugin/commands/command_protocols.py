"""Protocols and aliases for command host dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeAlias

from ..host.host_types import HostGraph, HostNode, HostPackage, HostPackageManager, HostUiManager
from ..json_types import JsonMap, JsonValue
from ..nested_graph.nested_graph_types import MutableNestedGraph, MutableNestedNode

CommandMethod: TypeAlias = Callable[..., JsonValue]


class SceneCommandHost(Protocol):
    """Protocol for host state and helpers used by scene commands."""

    _lib_url_cache: dict[str, str]
    _preview_cache: dict[str, JsonMap]
    _standard_library_preload_results: list[JsonValue]

    def _pkg_mgr(self) -> HostPackageManager:
        """Return the host package manager."""
        ...

    def _ui_mgr(self) -> HostUiManager:
        """Return the host UI manager."""
        ...

    def _get_sd_version(self) -> str:
        """Return the Substance Designer version."""
        ...

    def _resolve_package(self, package_index: int = 0, package_path: str | None = None) -> HostPackage:
        """Resolve a host package."""
        ...

    def _resolve_graph(self, graph_identifier: str | None = None) -> HostGraph:
        """Resolve a host graph."""
        ...


class NodeCommandHost(Protocol):
    """Protocol for host state and helpers used by node commands."""

    _lib_url_cache: dict[str, str]
    _preview_cache: dict[str, JsonMap]

    def _resolve_graph(self, graph_identifier: str | None = None) -> HostGraph:
        """Resolve a host graph."""
        ...

    def _ui_mgr(self) -> HostUiManager:
        """Return the host UI manager."""
        ...

    def _find_node(self, graph: HostGraph, node_id: JsonValue) -> HostNode:
        """Find a node in a graph."""
        ...

    def _pkg_mgr(self) -> HostPackageManager:
        """Return the host package manager."""
        ...

    def _set_node_params(self, node: MutableNestedNode, params: JsonMap) -> JsonMap | None:
        """Apply parameter values to a node."""
        ...

    def _safe_connect(
        self,
        graph: MutableNestedGraph,
        from_node: MutableNestedNode,
        from_out: str,
        to_node: MutableNestedNode,
        to_in: str,
    ) -> None:
        """Connect nested graph nodes."""
        ...
