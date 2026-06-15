from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPO_ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from merge_library_node_live_results import sd_version_from_evidence, validate_evidence_set  # noqa: E402
from probe_library_node_live_results import (  # noqa: E402
    ProbeTarget,
    empty_payload,
    load_targets,
    merge_node_payload,
    parameters_payload,
    select_targets,
    write_payload,
)
from probe_node_live_result import execute_probe  # noqa: E402


class CapturingClient:
    def __init__(self) -> None:
        self.code = ""

    def command(self, name: str, params: dict[str, object]) -> dict[str, object]:
        assert name == "execute_python"
        self.code = str(params["code"])
        return {"executed": True, "result": {"parameters": []}}


def test_load_targets_uses_creation_resource_url_and_package_hint(tmp_path: Path) -> None:
    node_definition_dir = tmp_path / "node_definitions"
    node_definition_dir.mkdir()
    (node_definition_dir / "library.json").write_text(
        json.dumps(
            {
                "node_definitions": {
                    "shape_splatter_v2": {
                        "definition_id": "sbs::library::shape_splatter_v2",
                        "creation": {
                            "method": "create_instance_node",
                            "package": {"kind": "builtin_standard_library", "path": "shape_splatter_v2.sbs"},
                            "resource_url": "pkg:///shape_splatter_v2",
                        },
                    },
                    "broken": {
                        "definition_id": "sbs::library::broken",
                        "creation": {"method": "create_instance_node"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    targets = load_targets(node_definition_dir, ("library.json",))

    assert targets == [
        ProbeTarget(
            catalog="library.json",
            slug="shape_splatter_v2",
            definition_id="sbs::library::shape_splatter_v2",
            resource_url="pkg:///shape_splatter_v2",
            package_hint={"kind": "builtin_standard_library", "path": "shape_splatter_v2.sbs"},
            creation_method="create_instance_node",
        )
    ]


def test_select_targets_filters_by_definition_slug_and_limit() -> None:
    targets = [
        ProbeTarget("library.json", "a", "sbs::library::a", "pkg:///a", None, "create_instance_node"),
        ProbeTarget("library.json", "b", "sbs::library::b", "pkg:///b", None, "create_instance_node"),
        ProbeTarget("library.json", "c", "sbs::library::c", "pkg:///c", None, "create_instance_node"),
    ]

    assert select_targets(targets, definition_ids={"sbs::library::b"}, slugs=set(), limit=None) == [targets[1]]
    assert select_targets(targets, definition_ids=set(), slugs={"c"}, limit=None) == [targets[2]]
    assert select_targets(targets, definition_ids=set(), slugs=set(), limit=2) == targets[:2]


def test_parameters_payload_keeps_non_enum_parameters_and_embeds_enum_metadata() -> None:
    evidence = {
        "sd_version": "16.0.3",
        "parameters": [
            {
                "id": "amount",
                "display_name": "Amount",
                "category": "Input",
                "host_type": "float",
                "value": 0.5,
                "connectable": False,
                "read_only": False,
            },
            {
                "id": "shape_type",
                "display_name": "Shape type",
                "category": "Input",
                "host_type": "sbs::compositing::shape_type",
                "value": 2,
                "current_label": "Cube",
                "connectable": False,
                "read_only": False,
                "enum": {"value_type": "int", "options": [{"value": 2, "id": "cube", "label": "Cube"}]},
            },
            {
                "id": "result",
                "display_name": "Result",
                "category": "Output",
                "host_type": "float4",
                "value": None,
                "connectable": True,
                "read_only": True,
            },
        ],
    }

    parameters = parameters_payload(evidence)

    assert set(parameters) == {"amount", "shape_type", "result"}
    assert "enum" not in parameters["amount"]
    assert parameters["amount"] == {"direction": "input", "label": "Amount", "type": "float", "value": 0.5}
    assert parameters["shape_type"]["enum"]["default_value"] == 2
    assert parameters["shape_type"]["enum"]["default_label"] == "Cube"
    assert parameters["result"] == {
        "connectable": True,
        "direction": "output",
        "label": "Result",
        "read_only": True,
        "type": "float4",
    }


def test_write_payload_creates_library_node_live_probe_results_file(tmp_path: Path) -> None:
    output = tmp_path / "library_node_live_probe_results.json"
    payload = empty_payload(target_total=1, catalogs=("library.json",))
    payload["sd_version"] = "16.0.3"
    payload["nodes"]["sbs::library::shape_splatter_v2"] = {
        "catalog": "library.json",
        "slug": "shape_splatter_v2",
        "parameters": {},
    }

    write_payload(output, payload)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["resource_kind"] == "library_node_live_probe_results"
    assert "failures" not in saved
    assert "delete_failures" not in saved
    assert saved["nodes"]["sbs::library::shape_splatter_v2"]["slug"] == "shape_splatter_v2"


def test_execute_probe_embeds_python_none_for_missing_graph_identifier() -> None:
    client = CapturingClient()

    execute_probe(client, node_id="probe_node", graph_identifier=None)  # type: ignore[arg-type]

    assert "graph_identifier = None" in client.code
    assert "graph_identifier = null" not in client.code


def test_merge_node_payload_preserves_duplicate_definition_slug_alias() -> None:
    payload = empty_payload(target_total=2, catalogs=("library.json",))
    first = ProbeTarget("library.json", "clamp", "sbs::library::clamp", "pkg:///clamp", None, "create_instance_node")
    second = ProbeTarget("library.json", "clamp_2", "sbs::library::clamp", "pkg:///clamp_2", None, "create_instance_node")
    first_evidence = {
        "sd_version": "16.0.3",
        "definition": "sbs::library::clamp",
        "resolved_definition": "sbs::library::clamp",
        "parameters": [{"id": "$format", "category": "Input", "value": 1}],
        "diagnostics": [],
    }
    second_evidence = {
        "sd_version": "16.0.3",
        "definition": "sbs::library::clamp",
        "resolved_definition": "sbs::library::clamp",
        "parameters": [{"id": "$tiling", "category": "Input", "value": 3}],
        "diagnostics": [],
    }

    merge_node_payload(payload, first, {"resource_url": "pkg:///clamp"}, {"node_id": "a"}, first_evidence)
    merge_node_payload(payload, second, {"resource_url": "pkg:///clamp_2"}, {"node_id": "b"}, second_evidence)

    node = payload["nodes"]["sbs::library::clamp"]
    assert node["slug"] == "clamp"
    assert node["aliases"][0]["slug"] == "clamp_2"
    assert set(node["parameters"]) == {"$format", "$tiling"}
    assert payload["summary"]["duplicate_definition_id_targets"] == 1


def test_merge_validator_accepts_live_probe_results_with_non_enum_parameters() -> None:
    evidence = {
        "schema_version": "1.0",
        "resource_kind": "library_node_live_probe_results",
        "sd_version": "16.0.3",
        "nodes": {
            "sbs::library::shape_splatter_v2": {
                "parameters": {
                    "amount": {"id": "amount", "value": 4},
                    "shape_type": {
                        "id": "shape_type",
                        "enum": {
                            "value_type": "int",
                            "options": [{"value": 2, "id": "cube", "label": "Cube"}],
                        },
                    },
                }
            }
        },
    }

    assert validate_evidence_set(evidence) == []
    assert sd_version_from_evidence(evidence) == "16.0.3"
