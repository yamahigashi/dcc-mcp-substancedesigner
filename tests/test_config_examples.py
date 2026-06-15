"""Tests for MCP client configuration examples."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"


def test_mcp_client_config_examples_are_valid_json() -> None:
    for path in CONFIG_DIR.glob("*_example.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        server = payload["mcpServers"]["substancedesigner"]

        assert server["command"] == "uv"
        assert server["args"][:2] == ["run", "--directory"]
        assert "dcc-mcp-substancedesigner" in server["args"]
        assert server["env"]["DCC_MCP_ADMIN_UI_PREBUILT"] == "1"
