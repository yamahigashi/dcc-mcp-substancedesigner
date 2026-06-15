"""Build packaged Substance Designer authoring node definition catalogs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATOMIC_SOURCE = ROOT / "docs" / "substance_designer_atomic_node_definitions.json"
DEFAULT_LIBRARY_SOURCE = ROOT / "docs" / "substance_designer_library_node_definitions.json"
DEFAULT_FUNCTION_ATOMIC_SOURCE = ROOT / "docs" / "substance_designer_function_atomic_node_definitions.json"
DEFAULT_FUNCTION_LIBRARY_SOURCE = ROOT / "docs" / "substance_designer_function_library_node_definitions.json"
DEFAULT_LIBRARY_LIVE_PROBE_SOURCE = ROOT / "docs" / "substance_designer_library_node_live_probe_results.json"
DEFAULT_OUTPUT_DIR = ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions"
CATALOGS = (
    ("atomic", "atomic.json", DEFAULT_ATOMIC_SOURCE),
    ("library", "library.json", DEFAULT_LIBRARY_SOURCE),
    ("function-atomic", "function_atomic.json", DEFAULT_FUNCTION_ATOMIC_SOURCE),
    ("function-library", "function_library.json", DEFAULT_FUNCTION_LIBRARY_SOURCE),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atomic-source", type=Path, default=DEFAULT_ATOMIC_SOURCE)
    parser.add_argument("--library-source", type=Path, default=DEFAULT_LIBRARY_SOURCE)
    parser.add_argument("--function-atomic-source", type=Path, default=DEFAULT_FUNCTION_ATOMIC_SOURCE)
    parser.add_argument("--function-library-source", type=Path, default=DEFAULT_FUNCTION_LIBRARY_SOURCE)
    parser.add_argument("--library-live-probe-source", type=Path, default=DEFAULT_LIBRARY_LIVE_PROBE_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "atomic": args.atomic_source,
        "library": args.library_source,
        "function-atomic": args.function_atomic_source,
        "function-library": args.function_library_source,
    }
    for kind, output_name, _default_source in CATALOGS:
        catalog = build_catalog(sources[kind], kind=kind)
        if kind == "library" and args.library_live_probe_source.is_file():
            merge_library_live_probe(catalog, args.library_live_probe_source)
        output_path = args.output_dir / output_name
        write_json(output_path, catalog)
        print(f"wrote {output_path} ({catalog_count(catalog)} nodes)")
    return 0


def build_catalog(source_path: Path, *, kind: str) -> dict[str, Any]:
    raw_nodes = json.loads(source_path.read_text(encoding="utf-8"))
    if _is_packaged_node_definition_set(raw_nodes, kind=kind):
        return normalize_packaged_catalog(raw_nodes)
    if not isinstance(raw_nodes, dict):
        raise ValueError(f"{source_path} must contain an object keyed by node slug")

    nodes = {slug: normalize_node(slug, node, kind=kind) for slug, node in sorted(raw_nodes.items())}
    definition_id_index: dict[str, list[str]] = {}
    for slug, node in nodes.items():
        definition_id_index.setdefault(str(node["definition_id"]), []).append(slug)

    return {
        "schema_version": "1.0",
        "resource_kind": "node_definition_set",
        "source": "static-docs",
        "generated_from": source_path.name,
        "kind": kind,
        "count": len(nodes),
        "definition_id_index": definition_id_index,
        "nodes": nodes,
    }


def normalize_node(slug: str, raw: Any, *, kind: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{kind}/{slug} must be an object")
    definition_id = required_text(raw, "definition_id", slug)
    display_name = str(raw.get("display_name") or slug)
    ports = {
        "inputs": normalize_ports(raw.get("inputs", {}), section="inputs"),
        "outputs": normalize_ports(raw.get("outputs", {}), section="outputs"),
    }
    add_host_port_aliases(definition_id, ports)
    node = {
        "slug": slug,
        "kind": kind,
        "definition_id": definition_id,
        "display_name": display_name,
        "title": display_name,
        "category": str(raw.get("category") or ""),
        "description": str(raw.get("description") or ""),
        "graph_scopes": graph_scopes_for_definition(definition_id, kind),
        "context_scopes": context_scopes_for_definition(definition_id, kind),
        "availability": availability_for_definition(definition_id, kind),
        "ports": ports,
        "parameters": normalize_parameters(raw.get("parameters", {}), definition_id=definition_id),
        "funcDatas": [],
        "tips": list(raw.get("tips") or []),
        "root": root_contract(definition_id, kind),
    }
    if isinstance(raw.get("creation"), dict):
        node["creation"] = normalize_creation_metadata(raw["creation"])
    return node


def add_host_port_aliases(definition_id: str, ports: dict[str, list[dict[str, Any]]]) -> None:
    if definition_id != "sbs::compositing::output":
        return
    for port in ports.get("inputs", []):
        if port.get("id") == "inputNodeOutput":
            aliases = port.setdefault("aliases", [])
            if isinstance(aliases, list) and "input1" not in aliases:
                aliases.append("input1")


def normalize_packaged_catalog(raw: dict[str, Any]) -> dict[str, Any]:
    catalog = dict(raw)
    nodes = raw.get("node_definitions")
    if isinstance(nodes, dict):
        catalog["node_definitions"] = {
            slug: normalize_packaged_node(node) if isinstance(node, dict) else node for slug, node in nodes.items()
        }
    return catalog


def normalize_packaged_node(raw: dict[str, Any]) -> dict[str, Any]:
    node = dict(raw)
    creation = raw.get("creation")
    if isinstance(creation, dict):
        node["creation"] = normalize_creation_metadata(creation)
    return node


def normalize_creation_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    creation = dict(raw)
    package = raw.get("package")
    if isinstance(package, dict):
        creation["package"] = normalize_package_metadata(package)
    candidates = raw.get("standard_package_candidates")
    if isinstance(candidates, list):
        creation["standard_package_candidates"] = [
            normalize_package_metadata(candidate) if isinstance(candidate, dict) else candidate
            for candidate in candidates
        ]
    return creation


def normalize_package_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    package = dict(raw)
    file_name = package.pop("file_name", None)
    if isinstance(file_name, str) and file_name and "path" not in package:
        package["path"] = file_name
    return package


def merge_library_live_probe(catalog: dict[str, Any], evidence_path: Path) -> None:
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict) or evidence.get("resource_kind") != "library_node_live_probe_results":
        return
    nodes = _catalog_nodes(catalog)
    by_definition = {
        node["definition_id"]: node
        for node in nodes.values()
        if isinstance(node, dict) and isinstance(node.get("definition_id"), str)
    }
    sd_version = str(evidence.get("sd_version") or "")
    for definition_id, node_evidence in (evidence.get("nodes") or {}).items():
        node = by_definition.get(str(definition_id))
        if not isinstance(node, dict) or not isinstance(node_evidence, dict):
            continue
        parameters = _parameters_by_id(node)
        for parameter_id, parameter_evidence in (node_evidence.get("parameters") or {}).items():
            parameter = parameters.get(str(parameter_id))
            enum = parameter_evidence.get("enum") if isinstance(parameter_evidence, dict) else None
            if not isinstance(parameter, dict) or not isinstance(enum, dict) or not enum.get("options"):
                continue
            parameter_type = parameter_evidence.get("type")
            if parameter_type:
                parameter["host_type"] = str(parameter_type)
            parameter["enum"] = normalize_enum_metadata(enum, parameter_evidence, sd_version=sd_version)


def normalize_enum_metadata(
    enum: dict[str, Any], parameter_evidence: dict[str, Any], *, sd_version: str
) -> dict[str, Any]:
    payload = dict(enum)
    payload["options"] = [dict(option) for option in enum["options"]]
    if "default_value" in parameter_evidence:
        payload["default_value"] = parameter_evidence["default_value"]
    if "default_label" in parameter_evidence:
        payload["default_label"] = parameter_evidence["default_label"]
    payload["evidence"] = {"source": "live_probe", "sd_version": sd_version, "confidence": "high"}
    return payload


def _catalog_nodes(catalog: dict[str, Any]) -> dict[str, Any]:
    nodes = catalog.get("node_definitions")
    if isinstance(nodes, dict):
        return nodes
    nodes = catalog.get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _parameters_by_id(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    parameters = node.get("parameters")
    if isinstance(parameters, dict):
        return {str(key): item for key, item in parameters.items() if isinstance(item, dict)}
    if isinstance(parameters, list):
        return {str(item["id"]): item for item in parameters if isinstance(item, dict) and item.get("id")}
    return {}


def _is_packaged_node_definition_set(raw: Any, *, kind: str) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("resource_kind") != "node_definition_set" or raw.get("kind") != kind:
        return False
    return isinstance(raw.get("node_definitions"), dict)


def catalog_count(catalog: dict[str, Any]) -> int:
    if isinstance(catalog.get("count"), int):
        return int(catalog["count"])
    if isinstance(catalog.get("nodes"), dict):
        return len(catalog["nodes"])
    if isinstance(catalog.get("node_definitions"), dict):
        return len(catalog["node_definitions"])
    return 0


def normalize_ports(raw_ports: Any, *, section: str) -> list[dict[str, Any]]:
    if not isinstance(raw_ports, dict):
        raise ValueError(f"{section} must be an object")
    result = []
    for port_id, raw in raw_ports.items():
        if not isinstance(raw, dict):
            raise ValueError(f"{section}.{port_id} must be an object")
        result.append(
            {
                "id": str(port_id),
                "type": normalize_type(raw.get("type")),
                "display_name": str(raw.get("display_name") or ""),
                "description": str(raw.get("description") or ""),
                "default": raw.get("default"),
                "connectable": bool(raw.get("connectable", False)),
                "read_only": bool(raw.get("read_only", False)),
                "variadic": bool(raw.get("variadic", False)),
                "primary": bool(raw.get("primary", False)),
                "required": section == "inputs" and raw.get("default") is None,
            }
        )
    return result


def normalize_parameters(raw_parameters: Any, *, definition_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw_parameters, dict):
        raise ValueError("parameters must be an object")
    result = []
    for parameter_id, raw in raw_parameters.items():
        if not isinstance(raw, dict):
            raise ValueError(f"parameters.{parameter_id} must be an object")
        result.append(
            {
                "id": str(parameter_id),
                "type": normalize_type(raw.get("type")),
                "display_name": str(raw.get("display_name") or ""),
                "description": str(raw.get("description") or ""),
                "default": raw.get("default"),
                "connectable": bool(raw.get("connectable", False)),
                "read_only": bool(raw.get("read_only", False)),
                "variadic": bool(raw.get("variadic", False)),
                "primary": bool(raw.get("primary", False)),
                "required": parameter_required(str(parameter_id), definition_id),
            }
        )
    return result


def normalize_type(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def parameter_required(parameter_id: str, definition_id: str) -> bool:
    return False


def graph_scopes_for_definition(definition_id: str, kind: str) -> list[str]:
    if definition_id.startswith("sbs::function::") or definition_id.startswith("sbs::function-library::"):
        return ["SDSBSFunctionGraph"]
    if definition_id.startswith("sbs::compositing::") or definition_id.startswith("sbs::library::"):
        return ["SDSBSCompGraph"]
    return ["SDSBSCompGraph"] if kind == "library" else []


def context_scopes_for_definition(definition_id: str, kind: str) -> list[dict[str, Any]]:
    if definition_id.startswith("sbs::function-library::3d_sdf_"):
        return [{"id": "3d_viewer", "label": "3D View function context", "required": True}]
    if definition_id.startswith("sbs::function-library::"):
        return [{"id": "unknown_function_context", "label": "Unknown function-library context", "required": True}]
    if definition_id.startswith("sbs::function::"):
        return [{"id": "generic_function", "label": "Generic function graph context", "required": False}]
    return []


def availability_for_definition(definition_id: str, kind: str) -> dict[str, Any]:
    if definition_id.startswith("sbs::function-library::3d_sdf_"):
        return {"default": False, "requires_context": ["3d_viewer"]}
    if definition_id.startswith("sbs::function-library::"):
        return {"default": False, "requires_context": ["unknown_function_context"]}
    if definition_id.startswith("sbs::function::"):
        return {"default": True}
    return {"default": True}


def root_contract(definition_id: str, kind: str) -> dict[str, Any]:
    if definition_id.startswith("sbs::function::") or definition_id.startswith("sbs::function-library::"):
        return {
            "can_be_root": True,
            "state_field": "output.node",
            "default_output": "unique_filter_output",
        }
    return {"can_be_root": False}


def required_text(raw: dict[str, Any], key: str, slug: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{slug}.{key} must be a non-empty string")
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
