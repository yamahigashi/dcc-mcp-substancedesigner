"""Scene query and diagnostic bridge command mixins."""

from __future__ import annotations

from typing import cast

from ..controls import preview_cache_path
from ..graph.graph_queries import diagnostic as diagnostic_payload
from ..graph.graph_queries import graph_info as graph_info_payload
from ..graph.graph_queries import scene_info
from ..graph.graph_types import (
    QueryGraph,
    ScenePackageManager,
    SceneUiManager,
)
from ..host.host_runtime import PYSIDE_PATH, QT_BINDING_USED, invoker_ready
from ..json_types import JsonMap
from ..plugin_constants import PLUGIN_VERSION
from .command_catalog import PLUGIN_COMMANDS
from .command_protocols import SceneCommandHost


class SceneQueryCommandMixin:
    """Scene inventory and graph query commands."""

    def get_scene_info(self) -> JsonMap:
        """Return package, graph, and version inventory."""
        host = cast(SceneCommandHost, self)
        return scene_info(
            cast(ScenePackageManager, host._pkg_mgr()),
            cast(SceneUiManager, host._ui_mgr()),
            host._get_sd_version(),
            ".".join(map(str, PLUGIN_VERSION)),
        )

    def get_graph_info(
        self,
        graph_identifier: str | None = None,
        node_limit: int = 100,
        include_connections: bool = True,
    ) -> JsonMap:
        """Return graph summary information."""
        host = cast(SceneCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        return graph_info_payload(cast(QueryGraph, graph), node_limit, include_connections)


class SceneDiagnosticCommandMixin:
    """Host runtime diagnostic commands."""

    def diagnostic(self) -> JsonMap:
        """Return a full health check of the host environment."""
        host = cast(SceneCommandHost, self)
        try:
            sd_version = host._get_sd_version()
            sd_version_error = None
        except Exception as e:
            sd_version = None
            sd_version_error = str(e)
        return diagnostic_payload(
            cast(ScenePackageManager, host._pkg_mgr()),
            cast(SceneUiManager, host._ui_mgr()),
            sd_version,
            sd_version_error,
            QT_BINDING_USED or "NONE",
            PYSIDE_PATH or "NOT FOUND",
            invoker_ready(),
            len(host._lib_url_cache),
            host._standard_library_preload_results,
            list(PLUGIN_COMMANDS),
            preview_cache_path(),
            len(host._preview_cache),
        )
