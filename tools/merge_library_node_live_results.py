"""Merge library node live probe results into packaged node definition catalogs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NODE_DEFINITION_DIR = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions"
DEFAULT_CATALOGS = ("atomic.json", "library.json", "function_atomic.json", "function_library.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="library_node_live_probe_results JSON file")
    parser.add_argument("--node-definition-dir", type=Path, default=DEFAULT_NODE_DEFINITION_DIR)
    parser.add_argument("--check", action="store_true", help="validate and report changes without writing files")
    args = parser.parse_args()

    evidence = _load_json(args.evidence)
    errors = validate_evidence_set(evidence)
    if errors:
        for error in errors:
            print(error)
        return 1

    catalogs = load_catalogs(args.node_definition_dir)
    changes, merge_errors = merge_evidence(catalogs, evidence)
    if merge_errors:
        for error in merge_errors:
            print(error)
        return 1

    if args.check:
        print(
            "Validated library node live probe results; "
            "{} parameter enum contract(s) would change.".format(len(changes))
        )
        for change in changes:
            print(_change_line(change))
        return 0

    for catalog in catalogs.values():
        if catalog.changed:
            _write_json(catalog.path, catalog.payload)
    print("Merged {} parameter enum contract(s).".format(len(changes)))
    for change in changes:
        print(_change_line(change))
    return 0


class Catalog:
    def __init__(self, path: Path, payload: dict[str, Any]) -> None:
        self.path = path
        self.payload = payload
        self.changed = False


def load_catalogs(node_definition_dir: Path) -> dict[str, Catalog]:
    catalogs = {}
    for name in DEFAULT_CATALOGS:
        path = node_definition_dir / name
        payload = _load_json(path)
        catalogs[name] = Catalog(path, payload)
    return catalogs


def validate_evidence_set(evidence: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["evidence root must be an object"]
    resource_kind = evidence.get("resource_kind")
    if resource_kind != "library_node_live_probe_results":
        errors.append("resource_kind must be library_node_live_probe_results")
    if not sd_version_from_evidence(evidence):
        errors.append("sd_version must be a non-empty string")
    nodes = evidence.get("nodes")
    if not isinstance(nodes, dict):
        errors.append("nodes must be an object keyed by definition_id")
        return errors
    for definition_id, node in nodes.items():
        if not isinstance(definition_id, str) or not definition_id:
            errors.append("nodes keys must be non-empty definition ids")
        if not isinstance(node, dict):
            errors.append("nodes.{} must be an object".format(definition_id))
            continue
        parameters = node.get("parameters")
        if not isinstance(parameters, dict):
            errors.append("nodes.{}.parameters must be an object".format(definition_id))
            continue
        for parameter_id, parameter in parameters.items():
            path = "nodes.{}.parameters.{}".format(definition_id, parameter_id)
            if not isinstance(parameter, dict) or "enum" not in parameter:
                continue
            errors.extend(_validate_parameter_evidence(path, parameter))
    return errors


def _validate_parameter_evidence(path: str, parameter: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(parameter, dict):
        return ["{} must be an object".format(path)]
    enum = parameter.get("enum")
    if not isinstance(enum, dict):
        errors.append("{}.enum must be an object".format(path))
        return errors
    options = enum.get("options")
    if not isinstance(options, list) or not options:
        errors.append("{}.enum.options must be a non-empty list".format(path))
        return errors
    seen_values: set[str] = set()
    seen_ids: set[str] = set()
    for index, option in enumerate(options):
        option_path = "{}.enum.options[{}]".format(path, index)
        if not isinstance(option, dict):
            errors.append("{} must be an object".format(option_path))
            continue
        if "value" not in option:
            errors.append("{}.value is required".format(option_path))
        label = option.get("label")
        if not isinstance(label, str) or not label:
            errors.append("{}.label must be a non-empty string".format(option_path))
        value_key = json.dumps(option.get("value"), sort_keys=True)
        if value_key in seen_values:
            errors.append("{}.value duplicates another option".format(option_path))
        seen_values.add(value_key)
        option_id = option.get("id")
        if option_id is not None:
            if not isinstance(option_id, str) or not option_id:
                errors.append("{}.id must be a non-empty string when present".format(option_path))
            elif option_id in seen_ids:
                errors.append("{}.id duplicates another option".format(option_path))
            seen_ids.add(option_id)
    return errors


def merge_evidence(catalogs: dict[str, Catalog], evidence: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    changes: list[dict[str, Any]] = []
    errors: list[str] = []
    definition_index = _definition_index(catalogs)
    sd_version = sd_version_from_evidence(evidence)
    source = str(evidence.get("source") or "live_probe")
    for definition_id, node_evidence in evidence["nodes"].items():
        target = definition_index.get(str(definition_id))
        if target is None:
            errors.append("unknown definition_id {}".format(definition_id))
            continue
        catalog, slug, node = target
        parameters = _parameters_by_id(node)
        for parameter_id, parameter_evidence in node_evidence["parameters"].items():
            if not isinstance(parameter_evidence, dict) or "enum" not in parameter_evidence:
                continue
            parameter = parameters.get(str(parameter_id))
            if parameter is None:
                continue
            enum_payload = _enum_payload(parameter, parameter_evidence, sd_version=sd_version, source=source)
            parameter_type = parameter_evidence.get("type") or parameter_evidence.get("host_type")
            if parameter.get("enum") == enum_payload and parameter.get("host_type") == parameter_type:
                continue
            if parameter_type:
                parameter["host_type"] = str(parameter_type)
            parameter["enum"] = enum_payload
            catalog.changed = True
            changes.append(
                {
                    "catalog": catalog.path,
                    "definition_id": definition_id,
                    "slug": slug,
                    "parameter": parameter_id,
                    "option_count": len(enum_payload["options"]),
                }
            )
    return changes, errors


def sd_version_from_evidence(evidence: dict[str, Any]) -> str:
    sd_version = evidence.get("sd_version")
    if isinstance(sd_version, str) and sd_version:
        return sd_version
    host = evidence.get("host")
    if isinstance(host, dict) and isinstance(host.get("sd_version"), str):
        return str(host["sd_version"])
    return ""


def _definition_index(catalogs: dict[str, Catalog]) -> dict[str, tuple[Catalog, str, dict[str, Any]]]:
    index = {}
    for catalog in catalogs.values():
        nodes = _nodes(catalog.payload)
        for slug, node in nodes.items():
            if isinstance(node, dict) and isinstance(node.get("definition_id"), str):
                index[node["definition_id"]] = (catalog, str(slug), node)
    return index


def _nodes(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = payload.get("node_definitions")
    if isinstance(nodes, dict):
        return nodes
    nodes = payload.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _parameters_by_id(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    parameters = node.get("parameters")
    if isinstance(parameters, dict):
        return {str(key): item for key, item in parameters.items() if isinstance(item, dict)}
    if isinstance(parameters, list):
        return {str(item["id"]): item for item in parameters if isinstance(item, dict) and item.get("id")}
    return {}


def _enum_payload(
    existing_parameter: dict[str, Any],
    parameter_evidence: dict[str, Any],
    *,
    sd_version: str,
    source: str,
) -> dict[str, Any]:
    enum = dict(parameter_evidence["enum"])
    options = [dict(option) for option in enum["options"]]
    enum["options"] = options
    if "default_value" in parameter_evidence:
        enum["default_value"] = parameter_evidence["default_value"]
    if "default_label" in parameter_evidence:
        enum["default_label"] = parameter_evidence["default_label"]
    evidence = dict(parameter_evidence.get("evidence") if isinstance(parameter_evidence.get("evidence"), dict) else {})
    evidence.setdefault("source", source)
    evidence.setdefault("sd_version", sd_version)
    evidence.setdefault("confidence", "high")
    enum["evidence"] = evidence
    diagnostics = _enum_diagnostics(existing_parameter, enum)
    if diagnostics:
        enum["diagnostics"] = diagnostics
    return enum


def _enum_diagnostics(parameter: dict[str, Any], enum: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics = []
    if "default" in parameter and "default_value" in enum and parameter.get("default") != enum.get("default_value"):
        diagnostics.append(
            {
                "code": "static_default_differs_from_enum_default",
                "static_default": parameter.get("default"),
                "enum_default": enum.get("default_value"),
            }
        )
    return diagnostics


def _change_line(change: dict[str, Any]) -> str:
    return "{}:{} {}.{} ({} options)".format(
        change["catalog"],
        change["slug"],
        change["definition_id"],
        change["parameter"],
        change["option_count"],
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("{} must contain a JSON object".format(path))
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
