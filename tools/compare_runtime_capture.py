"""Compare saved inspect_node captures with packaged authoring node definitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_DEFINITION_DIR = REPO_ROOT / "src" / "dcc_mcp_substancedesigner" / "node_definitions"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="JSON file containing one capture or a list of captures.")
    parser.add_argument("--definitions-dir", type=Path, default=NODE_DEFINITION_DIR)
    args = parser.parse_args()

    definitions = _load_definitions(args.definitions_dir)
    captures = _load_captures(args.capture)
    report = [_compare_capture(capture, definitions) for capture in captures]
    print(json.dumps({"count": len(report), "results": report}, indent=2, sort_keys=True))
    return 1 if any(item["comparison"]["status"] == "mismatch" for item in report) else 0


def _load_definitions(definitions_dir: Path) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for kind, filename in (
        ("atomic", "atomic.json"),
        ("library", "library.json"),
        ("function-atomic", "function_atomic.json"),
        ("function-library", "function_library.json"),
    ):
        payload = json.loads((definitions_dir / filename).read_text(encoding="utf-8"))
        for slug, node in payload.get("nodes", {}).items():
            nodes[f"{kind}:{slug}"] = node
            definition_id = node.get("definition_id")
            if isinstance(definition_id, str):
                nodes[f"definition:{definition_id}"] = node
    return nodes


def _load_captures(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return [item for item in payload["results"] if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("capture must be an object, list, or {results: [...]}")


def _compare_capture(capture: dict[str, Any], definitions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    target = capture.get("target", {}) if isinstance(capture.get("target"), dict) else {}
    runtime = capture.get("runtime", capture)
    node = _match_node(target, runtime, definitions)
    comparison = _compare(runtime, node)
    return {
        "target": target,
        "matched": node is not None,
        "definition_id": node.get("definition_id") if node else None,
        "comparison": comparison,
    }


def _match_node(
    target: dict[str, Any],
    runtime: dict[str, Any],
    definitions: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    definition_id = target.get("definition_id") or runtime.get("definition")
    if isinstance(definition_id, str) and f"definition:{definition_id}" in definitions:
        return definitions[f"definition:{definition_id}"]
    resource_url = target.get("resource_url")
    if isinstance(resource_url, str):
        slug = _slug_from_resource_url(resource_url)
        return definitions.get(f"library:{slug}")
    return None


def _slug_from_resource_url(resource_url: str) -> str:
    parsed = urlparse(resource_url)
    return (parsed.path.rsplit("/", 1)[-1] or parsed.netloc or resource_url).lower()


def _compare(runtime: dict[str, Any], node: dict[str, Any] | None) -> dict[str, Any]:
    if node is None:
        return {"status": "static_not_found", "differences": []}
    static_ports = node.get("ports", {}) if isinstance(node.get("ports"), dict) else {}
    runtime_ports = runtime.get("ports", {}) if isinstance(runtime.get("ports"), dict) else {}
    differences = []
    differences.extend(
        _missing_extra("ports.inputs", _ids(static_ports.get("inputs")), _ids(runtime_ports.get("inputs")))
    )
    differences.extend(
        _missing_extra("ports.outputs", _ids(static_ports.get("outputs")), _ids(runtime_ports.get("outputs")))
    )
    differences.extend(_missing_extra("parameters", _ids(node.get("parameters")), _ids(runtime.get("parameters"))))
    return {"status": "match" if not differences else "mismatch", "differences": differences}


def _ids(items: Any) -> set[str]:
    return (
        {str(item["id"]) for item in items if isinstance(item, dict) and item.get("id") is not None}
        if isinstance(items, list)
        else set()
    )


def _missing_extra(path: str, expected: set[str], actual: set[str]) -> list[dict[str, str]]:
    return [
        *({"path": path, "id": item, "static": "present", "runtime": "missing"} for item in sorted(expected - actual)),
        *({"path": path, "id": item, "static": "missing", "runtime": "present"} for item in sorted(actual - expected)),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
