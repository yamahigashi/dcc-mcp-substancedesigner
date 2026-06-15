"""Probe one live Substance Designer node through the bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dcc_mcp_substancedesigner.bridge import DEFAULT_SD_BRIDGE_PORT, SubstanceDesignerBridgeClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--definition-id", help="Atomic node definition id to create and probe")
    target.add_argument(
        "--resource-url", help="Library resource URL to instantiate and probe, for example pkg:///shape_splatter_v2"
    )
    parser.add_argument("--definition-key", help="Definition id key to use in the emitted evidence JSON")
    parser.add_argument("--graph-identifier", help="Graph identifier for temporary node creation")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_SD_BRIDGE_PORT)
    parser.add_argument("--output", type=Path, help="Write node_live_probe_result JSON to this file")
    parser.add_argument("--keep-node", action="store_true", help="Leave the temporary probe node in the graph")
    args = parser.parse_args()

    client = SubstanceDesignerBridgeClient(host=args.host, port=args.port)
    created = create_probe_node(client, args)
    node_id = str(created["node_id"])
    try:
        evidence = execute_probe(client, node_id=node_id, graph_identifier=args.graph_identifier)
        definition_key = args.definition_key or evidence_definition_key(args, evidence)
        payload = build_evidence_payload(definition_key, evidence)
    finally:
        if not args.keep_node:
            client.command("delete_node", _compact({"node_id": node_id, "graph_identifier": args.graph_identifier}))

    output_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output_text, encoding="utf-8")
        print("wrote {}".format(args.output))
    else:
        sys.stdout.write(output_text)
    return 0


def create_probe_node(client: SubstanceDesignerBridgeClient, args: argparse.Namespace) -> dict[str, Any]:
    params = _compact({"graph_identifier": args.graph_identifier, "position": [-640, -360]})
    if args.resource_url:
        params["resource_url"] = args.resource_url
        result = client.command("create_instance_node", params)
    else:
        params["definition_id"] = args.definition_id
        result = client.command("create_node", params)
    if not isinstance(result, dict) or not result.get("node_id"):
        raise RuntimeError("node creation did not return node_id: {!r}".format(result))
    return result


def execute_probe(
    client: SubstanceDesignerBridgeClient, *, node_id: str, graph_identifier: str | None
) -> dict[str, Any]:
    graph_identifier_literal = "None" if graph_identifier is None else json.dumps(graph_identifier)
    code = PROBE_CODE.replace("__NODE_ID__", json.dumps(node_id)).replace(
        "__GRAPH_IDENTIFIER__", graph_identifier_literal
    )
    result = client.command("execute_python", {"code": code, "strict_json": True})
    if not isinstance(result, dict):
        raise RuntimeError("execute_python returned non-object result: {!r}".format(result))
    if result.get("status") == "error" or result.get("executed") is False:
        raise RuntimeError(result.get("message") or result.get("stderr") or "execute_python probe failed")
    python_result = result.get("result")
    if not isinstance(python_result, dict):
        raise RuntimeError("execute_python probe returned non-object python result: {!r}".format(python_result))
    return python_result


def evidence_definition_key(args: argparse.Namespace, evidence: dict[str, Any]) -> str:
    if isinstance(evidence.get("resolved_definition"), str) and evidence["resolved_definition"]:
        return str(evidence["resolved_definition"])
    if args.definition_id:
        return str(args.definition_id)
    resource_url = str(args.resource_url or "").split("?", 1)[0].rstrip("/")
    slug = resource_url.rsplit("/", 1)[-1]
    return "sbs::library::{}".format(slug) if slug else str(args.resource_url)


def build_evidence_payload(definition_key: str, evidence: dict[str, Any]) -> dict[str, Any]:
    parameters = {}
    for parameter in evidence.get("parameters", []):
        if not isinstance(parameter, dict):
            continue
        parameter_id = parameter.get("id")
        if not parameter_id:
            continue
        parameter_id = str(parameter_id)
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
    enum_parameter_count = sum(1 for parameter in parameters.values() if "enum" in parameter)
    node = {
        "parameters": parameters,
        **({"ports": compact_ports(evidence.get("ports"))} if compact_ports(evidence.get("ports")) else {}),
        **({"diagnostics": evidence.get("diagnostics", [])} if evidence.get("diagnostics") else {}),
    }
    resolved_definition = evidence.get("resolved_definition")
    if resolved_definition and resolved_definition != definition_key:
        node["resolved_definition"] = resolved_definition
    return {
        "schema_version": "1.0",
        "resource_kind": "node_live_probe_result",
        "sd_version": evidence.get("sd_version"),
        "catalogs": [],
        "nodes": {definition_key: node},
        "summary": {
            "target_total": 1,
            "success": 1,
            "failure": 0,
            "parameter_total": len(parameters),
            "enum_parameter_total": enum_parameter_count,
        },
    }


def parameter_direction(category: Any) -> str:
    if category == "Output":
        return "output"
    if category == "Annotation":
        return "annotation"
    return "input"


def compact_ports(raw_ports: Any) -> dict[str, Any]:
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


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


PROBE_CODE = r"""
node_id = __NODE_ID__
graph_identifier = __GRAPH_IDENTIFIER__

def safe_call(obj, names, *args):
    for name in names:
        try:
            fn = getattr(obj, name)
        except Exception:
            continue
        try:
            return fn(*args)
        except Exception:
            pass
    return None

def json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    for keys in (("x", "y", "z", "w"), ("x", "y", "z"), ("x", "y"), ("r", "g", "b", "a"), ("r", "g", "b")):
        try:
            if all(hasattr(value, key) for key in keys):
                return [json_safe(getattr(value, key)) for key in keys]
        except Exception:
            pass
    raw = safe_call(value, ("get", "getValue"))
    if raw is not None and raw is not value:
        return json_safe(raw)
    return repr(value)

def value_type_name(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__

def type_id(prop):
    prop_type = safe_call(prop, ("getType",))
    if prop_type is None:
        return None
    return safe_call(prop_type, ("getId", "getIdentifier", "getName")) or str(prop_type)

def enum_provider(prop):
    prop_type = safe_call(prop, ("getType",))
    return (prop, prop_type)

def enum_values(prop):
    raw = None
    for provider in enum_provider(prop):
        if provider is None:
            continue
        raw = safe_call(provider, ("getEnumerators", "getEnumValues", "getValues"))
        if raw is not None:
            break
    if raw is None:
        return []
    try:
        items = list(raw)
    except Exception:
        items = []
    result = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            value = json_safe(item[0])
            label = str(item[1])
            option_id = label.lower().replace(" ", "_").replace("-", "_")
        else:
            value = safe_call(item, ("getValue", "getDefaultValue", "getIndex"))
            option_id = safe_call(item, ("getId", "getIdentifier", "getName"))
            label = safe_call(item, ("getLabel", "getTitle", "getName", "getId", "getIdentifier"))
            if value is None and isinstance(item, (str, int, float)):
                value = item
            if label is None:
                label = str(item)
            if option_id is None:
                option_id = str(label).lower().replace(" ", "_").replace("-", "_")
        result.append({"value": json_safe(value), "id": str(option_id), "label": str(label)})
    return result

def all_graphs():
    graphs = []
    current = safe_call(ui_mgr, ("getCurrentGraph", "getCurrentGraphResource"))
    if current is not None:
        graphs.append(current)
    try:
        packages = list(pkg_mgr.getPackages())
    except Exception:
        packages = []
    for package in packages:
        resources = []
        for method in ("getChildrenResources", "getResources"):
            try:
                resources = list(getattr(package, method)(True))
                break
            except Exception:
                try:
                    resources = list(getattr(package, method)())
                    break
                except Exception:
                    pass
        for resource in resources:
            class_name = safe_call(resource, ("getClassName",))
            if class_name == "SDSBSCompGraph":
                graphs.append(resource)
    unique = []
    seen = set()
    for graph in graphs:
        identifier = safe_call(graph, ("getIdentifier",)) or repr(graph)
        if identifier not in seen:
            unique.append(graph)
            seen.add(identifier)
    return unique

def find_node():
    for graph in all_graphs():
        identifier = safe_call(graph, ("getIdentifier",))
        if graph_identifier and identifier != graph_identifier:
            continue
        try:
            nodes = list(graph.getNodes())
        except Exception:
            nodes = []
        for node in nodes:
            if safe_call(node, ("getIdentifier",)) == node_id:
                return graph, node
    raise RuntimeError("Could not find probe node {} in graph {}".format(node_id, graph_identifier))

def node_definition(node):
    definition = safe_call(node, ("getDefinition",))
    if definition is None:
        return "unknown"
    return safe_call(definition, ("getId", "getIdentifier", "getName")) or str(definition)

def resolved_definition(node):
    try:
        resource = node.getReferencedResource()
    except Exception:
        resource = None
    if resource is not None:
        url = safe_call(resource, ("getUrl",))
        if isinstance(url, str) and url.startswith("pkg:///"):
            slug = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            return "sbs::library::{}".format(slug)
    return node_definition(node)

try:
    sd_version = safe_call(sd.getContext(), ("getSDApplication",))
    sd_version = safe_call(sd_version, ("getVersion",)) or safe_call(sd, ("getVersion",))
except Exception:
    sd_version = None

try:
    from sd.api.sdproperty import SDPropertyCategory
    categories = [
        ("Input", SDPropertyCategory.Input),
        ("Output", SDPropertyCategory.Output),
        ("Annotation", SDPropertyCategory.Annotation),
    ]
except Exception:
    categories = [("Input", 0), ("Output", 2), ("Annotation", 1)]

graph, node = find_node()
parameters = []
ports = {"inputs": {}, "outputs": {}}
diagnostics = []
for category_name, category in categories:
    try:
        props = list(node.getProperties(category))
    except Exception as exc:
        diagnostics.append({"code": "property_category_failed", "category": category_name, "message": str(exc)})
        props = []
    for prop in props:
        parameter_id = safe_call(prop, ("getId",))
        if not parameter_id:
            continue
        value_obj = None
        try:
            value_obj = node.getPropertyValue(prop)
        except Exception:
            pass
        options = enum_values(prop)
        current_value = json_safe(value_obj)
        current_label = None
        for option in options:
            if option.get("value") == current_value:
                current_label = option.get("label")
                break
        entry = {
            "id": str(parameter_id),
            "display_name": safe_call(prop, ("getLabel", "getIdentifier")) or "",
            "category": category_name,
            "host_type": type_id(prop),
            "value": current_value,
            "current_label": current_label,
            "connectable": bool(safe_call(prop, ("isConnectable", "getConnectable"))),
            "read_only": bool(safe_call(prop, ("isReadOnly", "getReadOnly"))),
        }
        if options:
            entry["enum"] = {"value_type": value_type_name(options[0].get("value")), "options": options}
        parameters.append(entry)
        if category_name in ("Input", "Output") and entry["connectable"]:
            port_group = "inputs" if category_name == "Input" else "outputs"
            ports[port_group][str(parameter_id)] = {
                "id": str(parameter_id),
                "display_name": entry["display_name"],
                "host_type": entry["host_type"],
                "connectable": entry["connectable"],
                "read_only": entry["read_only"],
            }

result = {
    "node_id": node_id,
    "definition": node_definition(node),
    "resolved_definition": resolved_definition(node),
    "sd_version": sd_version,
    "parameters": parameters,
    "ports": ports,
    "diagnostics": diagnostics,
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
