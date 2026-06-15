"""Probe live Substance Designer library node results for node definition catalogs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
TOOLS_ROOT = REPO_ROOT / "tools"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from dcc_mcp_substancedesigner.bridge import (  # noqa: E402
    DEFAULT_SD_BRIDGE_PORT,
    SubstanceDesignerBridgeClient,
    SubstanceDesignerBridgeError,
)
from probe_node_live_result import execute_probe  # noqa: E402


DEFAULT_NODE_DEFINITION_DIR = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions"
DEFAULT_CATALOGS = ("library.json",)


@dataclass(frozen=True)
class ProbeTarget:
    catalog: str
    slug: str
    definition_id: str
    resource_url: str | None
    package_hint: Any
    creation_method: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-definition-dir", type=Path, default=DEFAULT_NODE_DEFINITION_DIR)
    parser.add_argument(
        "--catalog",
        action="append",
        dest="catalogs",
        help="Catalog file name to scan. May be repeated. Default: library.json",
    )
    parser.add_argument("--definition-id", action="append", default=[], help="Only probe this definition id")
    parser.add_argument("--slug", action="append", default=[], help="Only probe this node slug")
    parser.add_argument("--limit", type=int, help="Maximum number of targets to probe")
    parser.add_argument("--output", type=Path, required=True, help="Write library_node_live_probe_results JSON here")
    parser.add_argument("--graph-identifier", help="Graph identifier for temporary node creation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_SD_BRIDGE_PORT)
    parser.add_argument("--fail-fast", action="store_true", help="Stop at the first probe failure")
    parser.add_argument(
        "--no-incremental-write",
        action="store_true",
        help="Only write the output after all targets finish",
    )
    args = parser.parse_args()

    catalogs = tuple(args.catalogs or DEFAULT_CATALOGS)
    targets = select_targets(
        load_targets(args.node_definition_dir, catalogs),
        definition_ids=set(args.definition_id),
        slugs=set(args.slug),
        limit=args.limit,
    )
    payload = empty_payload(target_total=len(targets), catalogs=catalogs)
    client = SubstanceDesignerBridgeClient(host=args.host, port=args.port)
    try:
        payload["sd_version"] = bridge_sd_version(client)
    except SubstanceDesignerBridgeError as exc:
        print("Bridge check failed: {}".format(exc), file=sys.stderr)
        return 1

    created_graph_identifier = None
    try:
        if not args.graph_identifier:
            created_graph_identifier = ensure_probe_graph(client)
            args.graph_identifier = created_graph_identifier

        for index, target in enumerate(targets, start=1):
            node_id = None
            try:
                request = creation_request(target, graph_identifier=args.graph_identifier)
                created = create_probe_node(client, target, request)
                node_id = str(created["node_id"])
                evidence = execute_probe(client, node_id=node_id, graph_identifier=args.graph_identifier)
                payload["sd_version"] = payload.get("sd_version") or evidence.get("sd_version")
                merge_node_payload(payload, target, request, created, evidence)
                bump_success_summary(payload, evidence)
                print(
                    "[{}/{}] {}: {} parameter(s), {} enum parameter(s)".format(
                        index,
                        len(targets),
                        target.definition_id,
                        len(evidence.get("parameters", [])),
                        enum_parameter_count(evidence),
                    )
                )
            except Exception as exc:
                error = compact_error(exc)
                payload["summary"]["failure"] += 1
                payload["failures"].append(
                    {
                        **target_payload(target),
                        "request": compact_request(creation_request(target, graph_identifier=args.graph_identifier)),
                        "error": error,
                    }
                )
                print("[{}/{}] {}: FAILED: {}".format(index, len(targets), target.definition_id, error))
                if args.fail_fast:
                    write_payload(args.output, payload)
                    return 1
            finally:
                if node_id:
                    try:
                        client.command(
                            "delete_node", compact({"node_id": node_id, "graph_identifier": args.graph_identifier})
                        )
                    except Exception as exc:
                        payload["delete_failures"].append(
                            {
                                **target_payload(target),
                                "node_id": node_id,
                                "error": compact_error(exc),
                            }
                        )
                if not args.no_incremental_write:
                    write_payload(args.output, payload)
    finally:
        if created_graph_identifier:
            try:
                client.command("delete_graph", {"graph_identifier": created_graph_identifier})
            except Exception as exc:
                if "not found" not in str(exc).lower():
                    payload["delete_failures"].append(
                        {
                            "graph_identifier": created_graph_identifier,
                            "error": compact_error(exc),
                        }
                    )

    write_payload(args.output, payload)
    print("wrote {}".format(args.output))
    return 1 if payload["summary"]["failure"] else 0


def ensure_probe_graph(client: SubstanceDesignerBridgeClient) -> str:
    package = client.command("create_package", {})
    if not isinstance(package, dict):
        raise RuntimeError("create_package returned non-object result: {!r}".format(package))
    package_index = package.get("package_index")
    if not isinstance(package_index, int):
        package_index = 0
    graph = client.command(
        "create_graph",
        {
            "package_index": package_index,
            "graph_name": "MCP_Library_Node_Live_Probe",
        },
    )
    if not isinstance(graph, dict) or not graph.get("identifier"):
        raise RuntimeError("create_graph did not return identifier: {!r}".format(graph))
    graph_identifier = str(graph["identifier"])
    try:
        client.command("open_graph", {"graph_identifier": graph_identifier})
    except Exception:
        pass
    return graph_identifier


def load_targets(node_definition_dir: Path, catalogs: tuple[str, ...]) -> list[ProbeTarget]:
    targets: list[ProbeTarget] = []
    for catalog in catalogs:
        path = node_definition_dir / catalog
        payload = load_json(path)
        nodes = payload.get("node_definitions")
        if not isinstance(nodes, dict):
            nodes = payload.get("nodes")
        if not isinstance(nodes, dict):
            continue
        for slug, node in sorted(nodes.items()):
            if not isinstance(node, dict):
                continue
            definition_id = node.get("definition_id")
            if not isinstance(definition_id, str) or not definition_id:
                continue
            creation = node.get("creation")
            resource_url = creation.get("resource_url") if isinstance(creation, dict) else None
            method = creation.get("method") if isinstance(creation, dict) else "create_node"
            if method == "create_instance_node" and not isinstance(resource_url, str):
                continue
            targets.append(
                ProbeTarget(
                    catalog=catalog,
                    slug=str(slug),
                    definition_id=definition_id,
                    resource_url=resource_url if isinstance(resource_url, str) else None,
                    package_hint=creation.get("package") if isinstance(creation, dict) else None,
                    creation_method=str(method or "create_node"),
                )
            )
    return targets


def select_targets(
    targets: list[ProbeTarget],
    *,
    definition_ids: set[str],
    slugs: set[str],
    limit: int | None,
) -> list[ProbeTarget]:
    selected = [
        target
        for target in targets
        if (not definition_ids or target.definition_id in definition_ids)
        and (not slugs or target.slug in slugs)
    ]
    return selected[:limit] if limit is not None else selected


def create_probe_node(
    client: SubstanceDesignerBridgeClient,
    target: ProbeTarget,
    request: dict[str, Any],
) -> dict[str, Any]:
    if target.creation_method == "create_instance_node":
        result = client.command("create_instance_node", request)
    else:
        result = client.command("create_node", request)
    if not isinstance(result, dict) or not result.get("node_id"):
        raise RuntimeError("node creation did not return node_id: {!r}".format(result))
    return result


def creation_request(target: ProbeTarget, *, graph_identifier: str | None) -> dict[str, Any]:
    request = compact({"graph_identifier": graph_identifier, "position": [-640, -360]})
    if target.creation_method == "create_instance_node":
        if not target.resource_url:
            raise ValueError("{} has no resource_url".format(target.definition_id))
        request["resource_url"] = target.resource_url
        if target.package_hint is not None:
            request["package_hint"] = target.package_hint
    else:
        request["definition_id"] = target.definition_id
    return request


def empty_payload(*, target_total: int, catalogs: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "resource_kind": "library_node_live_probe_results",
        "sd_version": None,
        "catalogs": list(catalogs),
        "nodes": {},
        "failures": [],
        "delete_failures": [],
        "summary": {
            "target_total": target_total,
            "success": 0,
            "failure": 0,
            "duplicate_definition_id_targets": 0,
            "parameter_total": 0,
            "enum_parameter_total": 0,
            "nodes_with_parameters": 0,
            "nodes_with_enum_parameters": 0,
        },
    }


def merge_node_payload(
    payload: dict[str, Any],
    target: ProbeTarget,
    request: dict[str, Any],
    created: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    node_payload = node_authoring_payload(target, request, created, evidence)
    existing = payload["nodes"].get(target.definition_id)
    if not isinstance(existing, dict):
        payload["nodes"][target.definition_id] = node_payload
        return

    aliases = existing.setdefault("aliases", [])
    aliases.append(alias_payload(target))
    existing.setdefault("alias_observations", []).append(
        {
            **alias_payload(target),
            "create": node_payload["create"],
            "parameters": node_payload["parameters"],
            **({"ports": node_payload["ports"]} if node_payload.get("ports") else {}),
            **({"diagnostics": node_payload["diagnostics"]} if node_payload.get("diagnostics") else {}),
        }
    )
    existing.setdefault("parameters", {}).update(node_payload["parameters"])
    payload["summary"]["duplicate_definition_id_targets"] += 1


def node_authoring_payload(
    target: ProbeTarget,
    request: dict[str, Any],
    created: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "catalog": target.catalog,
        "slug": target.slug,
        "create": compact(
            {
                "method": target.creation_method if target.creation_method != "create_instance_node" else None,
                **compact_request(request),
            }
        ),
        "parameters": parameters_payload(evidence),
    }
    resolved_definition = evidence.get("resolved_definition")
    if resolved_definition and resolved_definition != target.definition_id:
        payload["resolved_definition"] = resolved_definition
    ports = ports_payload(evidence.get("ports"))
    if ports:
        payload["ports"] = ports
    diagnostics = evidence.get("diagnostics")
    if diagnostics:
        payload["diagnostics"] = diagnostics
    return payload


def parameters_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    parameters = {}
    for parameter in evidence.get("parameters", []):
        if not isinstance(parameter, dict) or not parameter.get("id"):
            continue
        parameter_id = str(parameter["id"])
        item = {
            "direction": parameter_direction(parameter.get("category")),
            "label": parameter.get("display_name", ""),
            "type": parameter.get("host_type"),
            "value": parameter.get("value"),
        }
        if parameter.get("connectable"):
            item["connectable"] = True
        if parameter.get("read_only"):
            item["read_only"] = True
        enum = parameter.get("enum")
        if isinstance(enum, dict) and enum.get("options"):
            item["enum"] = {
                **enum,
                "default_value": parameter.get("value"),
                "default_label": parameter.get("current_label"),
            }
        item = {key: value for key, value in item.items() if value not in (None, "", {}, [])}
        parameters[parameter_id] = item
    return parameters


def parameter_direction(category: Any) -> str:
    if category == "Output":
        return "output"
    if category == "Annotation":
        return "annotation"
    return "input"


def ports_payload(raw_ports: Any) -> dict[str, Any]:
    if not isinstance(raw_ports, dict):
        return {}
    result = {}
    for group in ("inputs", "outputs"):
        ports = raw_ports.get(group)
        if not isinstance(ports, dict) or not ports:
            continue
        result[group] = {
            port_id: {
                key: value
                for key, value in {
                    "label": port.get("display_name"),
                    "type": port.get("host_type"),
                    "read_only": port.get("read_only") or None,
                }.items()
                if value not in (None, "", {}, [])
            }
            for port_id, port in ports.items()
            if isinstance(port, dict)
        }
    return result


def bump_success_summary(payload: dict[str, Any], evidence: dict[str, Any]) -> None:
    parameter_count = len([p for p in evidence.get("parameters", []) if isinstance(p, dict) and p.get("id")])
    enum_count = enum_parameter_count(evidence)
    payload["summary"]["success"] += 1
    payload["summary"]["parameter_total"] += parameter_count
    payload["summary"]["enum_parameter_total"] += enum_count
    if parameter_count:
        payload["summary"]["nodes_with_parameters"] += 1
    if enum_count:
        payload["summary"]["nodes_with_enum_parameters"] += 1


def enum_parameter_count(evidence: dict[str, Any]) -> int:
    return sum(
        1
        for parameter in evidence.get("parameters", [])
        if isinstance(parameter, dict)
        and isinstance(parameter.get("enum"), dict)
        and bool(parameter["enum"].get("options"))
    )


def target_payload(target: ProbeTarget) -> dict[str, Any]:
    return {
        "catalog": target.catalog,
        "slug": target.slug,
        "definition_id": target.definition_id,
    }


def alias_payload(target: ProbeTarget) -> dict[str, Any]:
    return {
        "catalog": target.catalog,
        "slug": target.slug,
        "create": compact(
            {
                "method": target.creation_method if target.creation_method != "create_instance_node" else None,
                "resource_url": target.resource_url,
                "package": package_payload(target.package_hint),
            }
        ),
    }


def compact_request(request: dict[str, Any]) -> dict[str, Any]:
    return compact(
        {
            "definition_id": request.get("definition_id"),
            "resource_url": request.get("resource_url"),
            "package": package_payload(request.get("package_hint")),
        }
    )


def package_payload(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload = compact(
        {
            "kind": raw.get("kind"),
            "file_name": raw.get("file_name"),
            "path": raw.get("path"),
            "resource_url": raw.get("resource_url"),
        }
    )
    return payload or None


def compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def compact_error(exc: Exception) -> str:
    message = str(exc)
    if " not found." in message and " loaded_packages=" in message:
        return message.split(" dependency=", 1)[0]
    return message


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if not result.get("failures"):
        result.pop("failures", None)
    if not result.get("delete_failures"):
        result.pop("delete_failures", None)
    return result


def bridge_sd_version(client: SubstanceDesignerBridgeClient) -> str:
    result = client.command("diagnostic")
    if not isinstance(result, dict):
        raise SubstanceDesignerBridgeError("diagnostic response must be an object")
    if result.get("sd_running") is False:
        raise SubstanceDesignerBridgeError("Substance Designer is not running according to diagnostics")
    sd_version = result.get("sd_version")
    if not sd_version:
        raise SubstanceDesignerBridgeError("diagnostic response did not include sd_version")
    return str(sd_version)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("{} must contain a JSON object".format(path))
    return payload


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(public_payload(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
