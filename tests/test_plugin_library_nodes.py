"""Tests for plugin-side library node helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_NODE_CREATION_PATH = REPO_ROOT / "plugin" / "library" / "library_nodes.py"
LIBRARY_NODE_LISTING_PATH = REPO_ROOT / "plugin" / "library" / "library_nodes.py"
LIBRARY_NODE_LOOKUP_PATH = REPO_ROOT / "plugin" / "library" / "library_nodes.py"


class FakeResource:
    """Fake package resource."""

    def __init__(self, identifier: str, url: str, class_name: str = "SDSBSCompGraph") -> None:
        """Store fake resource metadata."""
        self.identifier = identifier
        self.url = url
        self.class_name = class_name

    def getClassName(self) -> str:
        """Return a fake class name."""
        return self.class_name

    def getIdentifier(self) -> str:
        """Return a fake identifier."""
        return self.identifier

    def getUrl(self) -> str:
        """Return a fake URL."""
        return self.url


class FakePackage:
    """Fake package containing resources."""

    def __init__(self, file_path: str, resources: list[FakeResource]) -> None:
        """Store fake package state."""
        self.file_path = file_path
        self.resources = resources

    def getFilePath(self) -> str:
        """Return a fake package path."""
        return self.file_path

    def getChildrenResources(self, _recursive: bool) -> list[FakeResource]:
        """Return fake child resources."""
        return self.resources

    def findResourceFromUrl(self, url: str) -> FakeResource | None:
        """Find a fake resource by URL."""
        for resource in self.resources:
            if resource.getUrl() == url:
                return resource
        return None


class FakePackageManager:
    """Fake package manager."""

    def __init__(self, packages: list[FakePackage]) -> None:
        """Store fake packages."""
        self.packages = packages
        self.loaded_paths: list[str] = []

    def getPackages(self) -> list[FakePackage]:
        """Return fake packages."""
        return self.packages

    def loadUserPackage(self, file_path: str) -> FakePackage:
        """Load a fake package."""
        package = FakePackage(file_path, [FakeResource("Spline", "pkg:///spline")])
        self.loaded_paths.append(file_path)
        self.packages.append(package)
        return package


class FakeNode:
    """Fake created library node."""

    def __init__(self) -> None:
        """Initialize fake node state."""
        self.position: tuple[float, float] | None = None

    def setPosition(self, position: tuple[float, float]) -> None:
        """Record a fake position."""
        self.position = position


class FakeGraph:
    """Fake graph that creates instance nodes."""

    def __init__(self) -> None:
        """Initialize fake graph state."""
        self.created_resource: FakeResource | None = None
        self.node = FakeNode()

    def newInstanceNode(self, resource: FakeResource) -> FakeNode:
        """Create a fake instance node."""
        self.created_resource = resource
        return self.node


def test_resolve_library_url_updates_keyword_and_identifier_cache() -> None:
    """Verify keyword resolution populates keyword and identifier cache keys."""
    module = _load_library_nodes_module()
    resource = FakeResource("Blend", "pkg://library/blend")
    package_manager = FakePackageManager([FakePackage("/tmp/library.sbs", [resource])])
    cache: dict[str, str] = {}

    assert module.resolve_library_url(package_manager, cache, "ble") == "pkg://library/blend"
    assert cache == {"ble": "pkg://library/blend", "blend": "pkg://library/blend"}


def test_list_library_nodes_filters_graph_resources_and_updates_cache() -> None:
    """Verify library listing filters graph resources and updates the cache."""
    module = _load_library_nodes_module()
    resources = [
        FakeResource("Blend", "pkg://library/blend"),
        FakeResource("Bitmap", "pkg://library/bitmap", "SDBitmapResource"),
    ]
    package_manager = FakePackageManager([FakePackage("/tmp/library.sbs", resources)])
    cache: dict[str, str] = {}

    result = module.list_library_nodes(package_manager, cache, "ble", 10)

    assert result["count"] == 1
    assert result["nodes"] == [{"identifier": "Blend", "url": "pkg://library/blend", "package": "library.sbs"}]
    assert result["truncated"] is False
    assert result["filter"] == "ble"
    assert result["loaded_packages"] == ["/tmp/library.sbs"]
    assert cache == {"blend": "pkg://library/blend"}


def test_load_package_searches_known_package_dirs(monkeypatch) -> None:
    """Verify package loading accepts a package file name."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    package_path = "/opt/sd/resources/packages/spline_tools.sbs"
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR", "/opt/sd/resources/packages")
    monkeypatch.setattr(module.os.path, "exists", lambda path: _same_path(module, path, package_path))

    result = module.load_package(package_manager, "spline_tools.sbs")

    assert result["loaded"] is True
    assert _same_path(module, result["package_path"], package_path)
    assert [_norm_path(module, path) for path in package_manager.loaded_paths] == [_norm_path(module, package_path)]


def test_ensure_standard_package_uses_explicit_package_hint(monkeypatch) -> None:
    """Verify explicit node-definition package hints drive standard package loading."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    package_path = "/opt/sd/resources/packages/spline_tools.sbs"
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR", "/opt/sd/resources/packages")
    monkeypatch.setattr(module.os.path, "exists", lambda path: _same_path(module, path, package_path))

    result = module.ensure_standard_package_for_resource(
        package_manager,
        "pkg:///spline_bridge_2_splines?dependency=154",
        {"package": {"file_name": "spline_tools.sbs", "kind": "builtin_standard_library"}},
    )

    assert result["loaded"] is True
    assert result["package_name"] == "spline_tools.sbs"
    assert [_norm_path(module, path) for path in package_manager.loaded_paths] == [_norm_path(module, package_path)]


def test_ensure_standard_package_uses_relative_package_path_hint(monkeypatch) -> None:
    """Verify package hints preserve subdirectories under the standard package root."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    package_path = "/opt/sd/resources/packages/materials/pbr/bricks_001.sbs"
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR", "/opt/sd/resources/packages")
    monkeypatch.setattr(module.os.path, "exists", lambda path: _same_path(module, path, package_path))

    result = module.ensure_standard_package_for_resource(
        package_manager,
        "pkg:///bricks_001",
        {"package": {"path": "materials/pbr/bricks_001.sbs", "kind": "builtin_standard_library"}},
    )

    assert result["loaded"] is True
    assert result["package_name"] == "materials/pbr/bricks_001.sbs"
    assert [_norm_path(module, path) for path in package_manager.loaded_paths] == [_norm_path(module, package_path)]


def test_ensure_standard_package_for_3d_texture_sdf_uses_node_definition_hint(monkeypatch) -> None:
    """Verify 3D texture SDF package metadata triggers the package that actually contains it."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    package_path = "/opt/sd/resources/packages/3d_texture_jump_flood.sbs"
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR", "/opt/sd/resources/packages")
    monkeypatch.setattr(module.os.path, "exists", lambda path: _same_path(module, path, package_path))

    result = module.ensure_standard_package_for_resource(
        package_manager,
        "pkg:///3d_texture_sdf",
        {
            "standard_package_candidates": [
                {
                    "file_name": "3d_texture_jump_flood.sbs",
                    "resource_url": "pkg:///3d_texture_sdf",
                    "evidence": {"source": "package_scan", "status": "complete"},
                }
            ]
        },
    )

    assert result["loaded"] is True
    assert result["package_name"] == "3d_texture_jump_flood.sbs"
    assert [_norm_path(module, path) for path in package_manager.loaded_paths] == [_norm_path(module, package_path)]


def test_preload_standard_library_packages_is_empty_when_creation_uses_hints(monkeypatch) -> None:
    """Verify startup does not preload guessed standard packages."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    monkeypatch.setenv("DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR", "/opt/sd/resources/packages")

    result = module.preload_standard_library_packages(package_manager)

    assert result == []
    assert package_manager.loaded_paths == []


def test_preload_standard_library_packages_is_best_effort(monkeypatch) -> None:
    """Verify missing standard packages are reported without failing startup."""
    module = _load_library_nodes_module()
    package_manager = FakePackageManager([])
    monkeypatch.setattr(module.os.path, "exists", lambda _path: False)

    result = module.preload_standard_library_packages(package_manager)

    assert result == []


def test_create_library_node_resolves_resource_and_sets_position() -> None:
    """Verify library node creation resolves resources and applies position."""
    module = _load_library_nodes_module()
    resource = FakeResource("Blend", "pkg://library/blend")
    package_manager = FakePackageManager([FakePackage("/tmp/library.sbs", [resource])])
    graph = FakeGraph()

    node = module.create_library_node(graph, package_manager, {}, "Blend", [12, 34])

    assert node is graph.node
    assert graph.created_resource is resource
    assert graph.node.position == (12.0, 34.0)


def _norm_path(module: types.ModuleType, path: str) -> str:
    return module.os.path.normcase(module.os.path.normpath(path))


def _same_path(module: types.ModuleType, left: str, right: str) -> bool:
    return _norm_path(module, left) == _norm_path(module, right)


def _load_library_nodes_module() -> types.ModuleType:
    """Load concrete library node helper modules as package modules."""
    package = types.ModuleType("plugin")
    package.__path__ = [str(REPO_ROOT / "plugin")]  # type: ignore[attr-defined]
    sys.modules["plugin"] = package
    for module_name in [
        "plugin.library.library_nodes",
        "plugin.library.library_nodes",
        "plugin.library.library_nodes",
        "plugin.library.library_nodes",
        "plugin.library.library_nodes",
        "plugin.library.library_types",
        "plugin.library.library_nodes",
    ]:
        sys.modules.pop(module_name, None)
    module = _load_module("plugin.library.library_nodes", LIBRARY_NODE_LOOKUP_PATH)
    listing = _load_module("plugin.library.library_nodes", LIBRARY_NODE_LISTING_PATH)
    creation = _load_module("plugin.library.library_nodes", LIBRARY_NODE_CREATION_PATH)
    module.list_library_nodes = listing.list_library_nodes
    module.create_library_node = creation.create_library_node
    return module


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    """Load a module from a path under an explicit module name."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module
