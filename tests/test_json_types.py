from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

from dcc_mcp_substancedesigner import json_types as runtime_json

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_plugin_json_types() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("plugin.json_types", REPO_ROOT / "plugin" / "json_types.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plugin_json = _load_plugin_json_types()


@pytest.mark.parametrize("module", [runtime_json, plugin_json])
def test_cast_json_map_accepts_string_keyed_objects(module) -> None:
    payload = {"name": "node", "nested": {"id": "child"}}

    assert module.cast_json_map(payload) == payload


@pytest.mark.parametrize("module", [runtime_json, plugin_json])
def test_cast_json_map_rejects_non_string_keys(module) -> None:
    with pytest.raises(ValueError, match="payload must be a JSON object"):
        module.cast_json_map({1: "bad"}, "payload")


@pytest.mark.parametrize("module", [runtime_json, plugin_json])
def test_as_str_and_as_int_reject_wrong_shapes(module) -> None:
    assert module.as_str("abc", "field") == "abc"
    assert module.as_int(3, "count") == 3

    with pytest.raises(ValueError, match="field must be a string"):
        module.as_str(3, "field")
    with pytest.raises(ValueError, match="count must be an integer"):
        module.as_int(True, "count")


@pytest.mark.parametrize("module", [runtime_json, plugin_json])
def test_as_list_of_maps_rejects_non_object_items(module) -> None:
    assert module.as_list_of_maps([{"id": "a"}], "items") == [{"id": "a"}]

    with pytest.raises(ValueError, match="items\\[1\\] must be a JSON object"):
        module.as_list_of_maps([{"id": "a"}, "bad"], "items")
