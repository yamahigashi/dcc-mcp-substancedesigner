"""Validate packaged Substance Designer authoring node definition artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILES = (
    REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions" / "atomic.json",
    REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions" / "library.json",
    REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions" / "function_atomic.json",
    REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions" / "function_library.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, default=list(DEFAULT_FILES))
    args = parser.parse_args()

    errors: list[str] = []
    definition_ids: dict[str, list[str]] = {}
    for path in args.files:
        payload = _load(path, errors)
        if payload is None:
            continue
        _validate_set(path, payload, errors, definition_ids)

    if errors:
        for error in errors:
            print(error)
        return 1
    print("Validated {} authoring node definition files.".format(len(args.files)))
    return 0


def _load(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append("{}: failed to read JSON: {}".format(path, exc))
        return None
    if not isinstance(payload, dict):
        errors.append("{}: root must be an object".format(path))
        return None
    return payload


def _validate_set(
    path: Path,
    payload: dict[str, Any],
    errors: list[str],
    definition_ids: dict[str, list[str]],
) -> None:
    if payload.get("resource_kind") != "node_definition_set":
        errors.append("{}: resource_kind must be node_definition_set".format(path))
    kind = payload.get("kind")
    if kind not in {"atomic", "library", "function-atomic", "function-library"}:
        errors.append("{}: kind must be atomic, library, function-atomic, or function-library".format(path))
    uses_v2_nodes = not isinstance(payload.get("nodes"), dict) and isinstance(payload.get("node_definitions"), dict)
    nodes = payload.get("node_definitions") if uses_v2_nodes else payload.get("nodes")
    if not isinstance(nodes, dict):
        errors.append("{}: nodes or node_definitions must be an object".format(path))
        return
    if payload.get("count") is not None and payload.get("count") != len(nodes):
        errors.append("{}: count {} does not match node count {}".format(path, payload.get("count"), len(nodes)))
    for slug, node in nodes.items():
        if not isinstance(node, dict):
            errors.append("{}:{}: node must be an object".format(path, slug))
            continue
        _validate_node(path, str(slug), node, str(kind), errors, definition_ids, uses_v2_nodes=uses_v2_nodes)


def _validate_node(
    path: Path,
    slug: str,
    node: dict[str, Any],
    kind: str,
    errors: list[str],
    definition_ids: dict[str, list[str]],
    *,
    uses_v2_nodes: bool,
) -> None:
    if node.get("slug") is not None and node.get("slug") != slug:
        errors.append("{}:{}: slug field does not match object key".format(path, slug))
    if node.get("kind") is not None and node.get("kind") != kind:
        errors.append("{}:{}: kind field does not match set kind".format(path, slug))
    definition_id = node.get("definition_id")
    if not isinstance(definition_id, str) or not definition_id:
        errors.append("{}:{}: definition_id is required".format(path, slug))
    else:
        definition_ids.setdefault(definition_id, []).append("{}#{}".format(path, slug))
    ports = node.get("ports")
    if not isinstance(ports, dict):
        errors.append("{}:{}: ports must be an object".format(path, slug))
        return
    for group in ("inputs", "outputs"):
        values = ports.get(group)
        normalized_values = _object_values(values) if uses_v2_nodes else values
        if not isinstance(normalized_values, list):
            errors.append("{}:{}: ports.{} must be a list or object".format(path, slug, group))
            continue
        _validate_unique_ids(path, slug, "ports.{}".format(group), normalized_values, errors)
    parameters = node.get("parameters")
    normalized_parameters = _object_values(parameters) if uses_v2_nodes else parameters
    if not isinstance(normalized_parameters, list):
        errors.append("{}:{}: parameters must be a list or object".format(path, slug))
    else:
        _validate_unique_ids(path, slug, "parameters", normalized_parameters, errors)
        for parameter in normalized_parameters:
            if isinstance(parameter, dict):
                _validate_parameter_enum(path, slug, parameter, errors)
    _validate_creation_metadata(path, slug, node, errors)


def _validate_unique_ids(path: Path, slug: str, group: str, values: list[Any], errors: list[str]) -> None:
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            errors.append("{}:{}: {}[{}] must be an object".format(path, slug, group, index))
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append("{}:{}: {}[{}].id is required".format(path, slug, group, index))
            continue
        if item_id in seen:
            errors.append("{}:{}: duplicate {} id {}".format(path, slug, group, item_id))
        seen.add(item_id)


def _validate_parameter_enum(path: Path, slug: str, parameter: dict[str, Any], errors: list[str]) -> None:
    enum = parameter.get("enum")
    if enum is None:
        return
    parameter_id = parameter.get("id", "<unknown>")
    if not isinstance(enum, dict):
        errors.append("{}:{}: parameters.{}.enum must be an object".format(path, slug, parameter_id))
        return
    options = enum.get("options")
    if not isinstance(options, list) or not options:
        errors.append("{}:{}: parameters.{}.enum.options must be a non-empty list".format(path, slug, parameter_id))
        return
    seen_values: set[str] = set()
    seen_ids: set[str] = set()
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}] must be an object".format(path, slug, parameter_id, index)
            )
            continue
        if "value" not in option:
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}].value is required".format(path, slug, parameter_id, index)
            )
        label = option.get("label")
        if not isinstance(label, str) or not label:
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}].label must be a non-empty string".format(
                    path, slug, parameter_id, index
                )
            )
        value_key = json.dumps(option.get("value"), sort_keys=True)
        if value_key in seen_values:
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}].value duplicates another option".format(
                    path, slug, parameter_id, index
                )
            )
        seen_values.add(value_key)
        option_id = option.get("id")
        if option_id is None:
            continue
        if not isinstance(option_id, str) or not option_id:
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}].id must be a non-empty string".format(
                    path, slug, parameter_id, index
                )
            )
        elif option_id in seen_ids:
            errors.append(
                "{}:{}: parameters.{}.enum.options[{}].id duplicates another option".format(
                    path, slug, parameter_id, index
                )
            )
        seen_ids.add(option_id)


def _validate_creation_metadata(path: Path, slug: str, node: dict[str, Any], errors: list[str]) -> None:
    creation = node.get("creation")
    if not isinstance(creation, dict):
        return
    package = creation.get("package")
    if isinstance(package, dict):
        _validate_package_metadata(path, slug, "creation.package", package, errors)
    candidates = creation.get("standard_package_candidates")
    if isinstance(candidates, list):
        for index, candidate in enumerate(candidates):
            if isinstance(candidate, dict):
                _validate_package_metadata(
                    path,
                    slug,
                    "creation.standard_package_candidates[{}]".format(index),
                    candidate,
                    errors,
                )


def _validate_package_metadata(
    path: Path,
    slug: str,
    location: str,
    package: dict[str, Any],
    errors: list[str],
) -> None:
    if "file_name" in package:
        errors.append("{}:{}: {}.file_name is deprecated; use path".format(path, slug, location))
    if "path" not in package:
        errors.append("{}:{}: {}.path is required".format(path, slug, location))


def _object_values(value: Any) -> list[Any] | Any:
    if isinstance(value, dict):
        return [{**item, "id": key} for key, item in value.items() if isinstance(item, dict)]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
