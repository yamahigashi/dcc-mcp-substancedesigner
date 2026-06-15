"""Library node lookup, listing, loading, and creation helpers."""

from __future__ import annotations

import os
from typing import cast
from urllib.parse import parse_qs, urlparse

from sd.api.sdbasetypes import float2

from ..json_types import JsonScalar, JsonValue
from .library_types import (
    LibraryCache,
    LibraryGraph,
    LibraryNode,
    LibraryNodeInfo,
    LibraryPackage,
    LibraryPackageManager,
    LibraryResource,
    PositionInput,
    PositionValue,
)

STANDARD_LIBRARY_PACKAGES: tuple[str, ...] = ()


def packages(package_manager: LibraryPackageManager) -> list[LibraryPackage]:
    """Return package manager packages, tolerating host API failures."""
    try:
        return list(package_manager.getPackages())
    except Exception:
        return []


def package_path(package: LibraryPackage) -> str:
    """Return a package path or an empty string."""
    try:
        return package.getFilePath()
    except Exception:
        return ""


def child_resources(package: LibraryPackage) -> list[LibraryResource]:
    """Return child graph resources using host recursion fallbacks."""
    for recursive in (True, False):
        try:
            children = list(package.getChildrenResources(recursive))
            if children:
                return [cast(LibraryResource, child) for child in children]
        except Exception:
            continue
    return []


def loaded_package_paths(package_manager: LibraryPackageManager) -> list[str]:
    """Return loaded package paths for diagnostics."""
    paths: list[str] = []
    for package in packages(package_manager):
        file_path = package_path(package)
        if file_path:
            paths.append(file_path)
    return paths


def is_package_loaded(package_manager: LibraryPackageManager, package_name_or_path: str) -> bool:
    """Return whether a package path or package file name is already loaded."""
    requested_name = os.path.basename(package_name_or_path).lower()
    requested_path = os.path.normcase(os.path.normpath(package_name_or_path))
    for file_path in loaded_package_paths(package_manager):
        normalized_file_path = os.path.normcase(os.path.normpath(file_path))
        if os.path.basename(file_path).lower() == requested_name:
            return True
        if normalized_file_path == requested_path:
            return True
        if not os.path.isabs(package_name_or_path) and normalized_file_path.endswith(requested_path):
            return True
    return False


def matching_graph_url(resource: LibraryResource, lowered_keyword: str) -> str | None:
    """Return a resource URL when it matches a keyword."""
    try:
        if "SDSBSCompGraph" not in resource.getClassName():
            return None
        resource_id = resource.getIdentifier()
        if lowered_keyword not in resource_id.lower():
            return None
        url = resource.getUrl()
        return url or None
    except Exception:
        return None


def library_node_info(
    resource: LibraryResource,
    package_path_value: str,
    lowered_filter: str,
) -> LibraryNodeInfo | None:
    """Return serializable library node info for a resource."""
    try:
        if "SDSBSCompGraph" not in resource.getClassName():
            return None
        resource_id = resource.getIdentifier()
        if lowered_filter and lowered_filter not in resource_id.lower():
            return None
        url = resource.getUrl()
        if not url:
            return None
        return {
            "identifier": resource_id,
            "url": url,
            "package": os.path.basename(package_path_value),
        }
    except Exception:
        return None


def resolve_library_url(package_manager: LibraryPackageManager, cache: LibraryCache, keyword: str) -> str | None:
    """Find a library graph URL by keyword and update the cache."""
    key = keyword.lower()
    if key in cache:
        return cache[key]
    for package in packages(package_manager):
        file_path = package_path(package)
        if not file_path:
            continue
        for resource in child_resources(package):
            resource_url = matching_graph_url(resource, key)
            if resource_url is None:
                continue
            cache[key] = resource_url
            try:
                cache[resource.getIdentifier().lower()] = resource_url
            except Exception:
                pass
            return resource_url
    return None


def find_library_resource(package_manager: LibraryPackageManager, url: str) -> LibraryResource | None:
    """Find a library resource by URL across packages."""
    for package in packages(package_manager):
        try:
            resource = package.findResourceFromUrl(url)
            if resource is not None:
                return resource
        except Exception:
            pass
    return None


def package_search_dirs() -> list[str]:
    """Return Substance Designer package directories worth searching."""
    dirs: list[str] = []
    for env_name in (
        "DCC_MCP_SUBSTANCEDESIGNER_PACKAGE_DIR",
        "SUBSTANCE_DESIGNER_PACKAGE_DIR",
        "SUBSTANCE_DESIGNER_RESOURCES",
    ):
        env_value = os.environ.get(env_name)
        if not env_value:
            continue
        dirs.append(env_value)
        dirs.append(os.path.join(env_value, "packages"))
    for root in (
        os.path.join(os.environ.get("ProgramFiles", "C:/Program Files"), "Adobe"),
        "C:/Program Files/Adobe",
    ):
        dirs.append(os.path.join(root, "Adobe Substance 3D Designer", "resources", "packages"))
    deduped: list[str] = []
    for directory in dirs:
        normalized = os.path.normpath(directory)
        if normalized not in deduped:
            deduped.append(normalized)
    return deduped


def resource_dependency_id(resource_url: str) -> str | None:
    """Return dependency query id from a pkg URL when present."""
    try:
        values = parse_qs(urlparse(resource_url).query).get("dependency")
    except Exception:
        return None
    return values[0] if values else None


def standard_package_names_for_hint(package_hint: JsonValue) -> list[str]:
    """Return explicit standard package names from node-definition package metadata."""
    names: list[str] = []
    _collect_package_names(package_hint, names)
    return list(dict.fromkeys(name for name in names if name))


def _collect_package_names(value: JsonValue, output: list[str]) -> None:
    if isinstance(value, str) and value:
        output.append(value)
        return
    if isinstance(value, list):
        for item in value:
            _collect_package_names(item, output)
        return
    if not isinstance(value, dict):
        return
    for key in ("file_name", "package_name", "package", "path"):
        item = value.get(key)
        if isinstance(item, str) and item:
            output.append(item)
        elif isinstance(item, (dict, list)):
            _collect_package_names(item, output)
    candidates = value.get("standard_package_candidates")
    if isinstance(candidates, list):
        _collect_package_names(candidates, output)


def package_candidates(package_name_or_path: str) -> list[str]:
    """Return concrete package paths for a package name or path."""
    if os.path.isabs(package_name_or_path):
        return [os.path.normpath(package_name_or_path)]
    return [os.path.join(directory, package_name_or_path) for directory in package_search_dirs()]


def load_package(package_manager: LibraryPackageManager, package_name_or_path: str) -> JsonValue:
    """Load a package by absolute path or known package file name."""
    if is_package_loaded(package_manager, package_name_or_path):
        return {
            "loaded": False,
            "already_loaded": True,
            "package": package_name_or_path,
            "tried": [],
            "loaded_packages": loaded_package_paths(package_manager),
        }
    tried: list[str] = []
    for candidate in package_candidates(package_name_or_path):
        tried.append(candidate)
        if not os.path.exists(candidate):
            continue
        package = package_manager.loadUserPackage(candidate)
        return {
            "loaded": True,
            "package_path": package_path(package) or candidate,
            "tried": tried,
            "loaded_packages": loaded_package_paths(package_manager),
        }
    raise FileNotFoundError("Package '{}' not found. Tried: {}".format(package_name_or_path, tried))


def preload_standard_library_packages(package_manager: LibraryPackageManager) -> list[JsonValue]:
    """Best-effort load standard packages needed for common authoring discovery."""
    results: list[JsonValue] = []
    for package_name in STANDARD_LIBRARY_PACKAGES:
        try:
            result = load_package(package_manager, package_name)
            if isinstance(result, dict):
                result["package_name"] = package_name
            results.append(result)
        except Exception as exc:
            results.append(
                {
                    "package_name": package_name,
                    "loaded": False,
                    "already_loaded": False,
                    "error": str(exc),
                    "tried": package_candidates(package_name),
                }
            )
    return results


def ensure_standard_package_for_resource(
    package_manager: LibraryPackageManager,
    resource_url: str,
    package_hint: JsonValue = None,
) -> JsonValue:
    """Load an explicit standard package candidate for a resource URL when metadata provides one."""
    tried: list[str] = []
    package_names = standard_package_names_for_hint(package_hint)
    for package_name in package_names:
        for candidate in package_candidates(package_name):
            tried.append(candidate)
            if not os.path.exists(candidate):
                continue
            package = package_manager.loadUserPackage(candidate)
            return {
                "loaded": True,
                "package_name": package_name,
                "package_path": package_path(package) or candidate,
                "tried": tried,
            }
    return {
        "loaded": False,
        "candidate_package_names": package_names,
        "package_hint": package_hint,
        "tried": tried,
    }


def resource_not_found_message(
    package_manager: LibraryPackageManager, resource_url: str, load_attempt: JsonValue
) -> str:
    """Return an actionable resource lookup failure message."""
    return (
        "Resource '{}' not found. The package may be unloaded or the URL may be wrong. "
        "dependency={}, loaded_packages={}, standard_package_candidates={}, load_attempt={}. "
        "Built-in library nodes require node-definition package metadata; user package nodes require the package to be loaded."
    ).format(
        resource_url,
        resource_dependency_id(resource_url),
        loaded_package_paths(package_manager),
        standard_package_names_for_hint(load_attempt.get("package_hint") if isinstance(load_attempt, dict) else None),
        load_attempt,
    )


def list_library_nodes(
    package_manager: LibraryPackageManager, cache: LibraryCache, filter_text: str, limit: int
) -> JsonValue:
    """List library graph resources available from packages."""
    results: list[JsonValue] = []
    lowered_filter = filter_text.lower()
    for package in packages(package_manager):
        file_path = package_path(package)
        if not file_path:
            continue
        for resource in child_resources(package):
            info = library_node_info(resource, file_path, lowered_filter)
            if info is None:
                continue
            cache[cast(str, info["identifier"]).lower()] = cast(str, info["url"])
            results.append(info)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return {
        "count": len(results),
        "nodes": results,
        "truncated": len(results) >= limit,
        "filter": filter_text,
        "loaded_packages": loaded_package_paths(package_manager),
        "standard_package_candidates": package_candidates(filter_text) if filter_text.endswith(".sbs") else [],
    }


def set_library_node_position(node: LibraryNode, position: PositionInput | None) -> None:
    """Set a library node position when coordinates are supplied."""
    if position is None or len(position) < 2:
        return
    node.setPosition(cast(PositionValue, float2(coordinate(position[0]), coordinate(position[1]))))


def coordinate(value: JsonScalar) -> float:
    """Coerce a JSON scalar to a graph coordinate."""
    if isinstance(value, (bool, int, float, str)):
        return float(value)
    raise ValueError("Library node position entries must be scalar values.")


def create_library_node(
    graph: LibraryGraph,
    package_manager: LibraryPackageManager,
    cache: LibraryCache,
    keyword: str,
    position: PositionInput | None = None,
) -> LibraryNode:
    """Create a library instance node by keyword."""
    url = resolve_library_url(package_manager, cache, keyword)
    if not url:
        raise ValueError(
            "Library node '{}' not found. Read substancedesigner://authoring/node/instance/instance_node "
            "and load the package that contains '{}' before creating an instance node.".format(
                keyword,
                keyword,
            )
        )
    resource = find_library_resource(package_manager, url)
    if resource is None:
        raise ValueError("Resource URL not found: {}".format(url))
    node = graph.newInstanceNode(resource)
    if not node:
        raise RuntimeError("newInstanceNode failed for '{}'.".format(url))
    set_library_node_position(node, position)
    return node
