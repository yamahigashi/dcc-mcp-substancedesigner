"""Scene graph lifecycle bridge command mixin."""

from __future__ import annotations

from typing import cast

from sd.api.sbs.sdsbscompgraph import SDSBSCompGraph
from sd.api.sdapiobject import SDAPIObject

from ..graph.graph_operations import create_graph as create_graph_payload
from ..graph.graph_operations import create_package as create_package_payload
from ..graph.graph_operations import delete_graph as delete_graph_payload
from ..graph.graph_operations import open_graph as open_graph_payload
from ..graph.graph_operations import save_package as save_package_payload
from ..graph.graph_types import GraphResource, PackageManager, UiManager
from ..graph.graph_types import HostPackage as LifecyclePackage
from ..json_types import JsonMap
from .command_protocols import SceneCommandHost


class SceneLifecycleCommandMixin:
    """Package and graph lifecycle commands."""

    def create_package(self, file_path: str | None = None) -> JsonMap:
        """Create a new host package."""
        host = cast(SceneCommandHost, self)
        return create_package_payload(cast(PackageManager, host._pkg_mgr()), file_path)

    def create_graph(
        self,
        package_index: int = 0,
        graph_name: str = "MCP_Graph",
        package_path: str | None = None,
    ) -> JsonMap:
        """Create a new graph in a package."""
        host = cast(SceneCommandHost, self)
        pkg = host._resolve_package(package_index, package_path)
        return create_graph_payload(new_composition_graph, cast(LifecyclePackage, pkg), graph_name)

    def delete_graph(self, graph_identifier: str, package_index: int = 0) -> JsonMap:
        """Delete a graph from a package."""
        host = cast(SceneCommandHost, self)
        pkg = host._resolve_package(package_index)
        return delete_graph_payload(cast(LifecyclePackage, pkg), graph_identifier)

    def open_graph(self, graph_identifier: str) -> JsonMap:
        """Open a graph in the host editor."""
        host = cast(SceneCommandHost, self)
        graph = host._resolve_graph(graph_identifier)
        return open_graph_payload(cast(UiManager, host._ui_mgr()), cast(GraphResource, graph), graph_identifier)

    def save_package(
        self,
        package_index: int = 0,
        file_path: str | None = None,
        package_path: str | None = None,
    ) -> JsonMap:
        """Save a package to its current or requested path."""
        host = cast(SceneCommandHost, self)
        pkg = host._resolve_package(package_index, package_path)
        return save_package_payload(cast(PackageManager, host._pkg_mgr()), cast(LifecyclePackage, pkg), file_path)


def new_composition_graph(parent: LifecyclePackage) -> GraphResource:
    """Create an SBS composition graph from a host package."""
    return cast(GraphResource, SDSBSCompGraph.sNew(cast(SDAPIObject, parent)))
