"""Basic tests for dcc-mcp-substancedesigner."""

from __future__ import annotations


def test_import() -> None:
    """The package should import without a live Substance Designer or dcc-mcp-core."""
    import dcc_mcp_substancedesigner

    assert hasattr(dcc_mcp_substancedesigner, "__version__")
    assert hasattr(dcc_mcp_substancedesigner, "SubstanceDesignerMcpServer")


def test_version() -> None:
    """Version is a non-empty string."""
    from dcc_mcp_substancedesigner import __version__

    assert isinstance(__version__, str)
    assert __version__


def test_server_options_defaults() -> None:
    """Server options should expose MCP and Substance Designer bridge defaults."""
    from dcc_mcp_substancedesigner.server import SubstanceDesignerServerOptions

    opts = SubstanceDesignerServerOptions()
    assert opts.port == 8766
    assert opts.gateway_port == 9765
    assert opts.sd_port == 9881
    assert opts.server_name == "dcc-mcp-substancedesigner"
    assert opts.enable_gateway_failover is True


def test_bridge_client_from_options() -> None:
    """Options create a bridge client without opening a socket."""
    from dcc_mcp_substancedesigner.server import SubstanceDesignerServerOptions

    client = SubstanceDesignerServerOptions(sd_host="localhost", sd_port=9999).make_bridge_client()
    assert client.host == "localhost"
    assert client.port == 9999


def test_bridge_client_from_environment_validates_configuration(monkeypatch) -> None:
    """Environment bridge settings should fail with adapter-owned validation errors."""
    import pytest

    from dcc_mcp_substancedesigner.commands import (
        ENV_SD_BRIDGE_HOST,
        ENV_SD_BRIDGE_PORT,
        SubstanceDesignerValidationError,
        client_from_env,
    )

    monkeypatch.setenv(ENV_SD_BRIDGE_HOST, "127.0.0.1")
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, "19999")
    client = client_from_env()
    assert client.host == "127.0.0.1"
    assert client.port == 19999

    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, "not-a-port")
    with pytest.raises(SubstanceDesignerValidationError, match=ENV_SD_BRIDGE_PORT):
        client_from_env()

    monkeypatch.setenv(ENV_SD_BRIDGE_HOST, " ")
    monkeypatch.setenv(ENV_SD_BRIDGE_PORT, "9881")
    with pytest.raises(SubstanceDesignerValidationError, match=ENV_SD_BRIDGE_HOST):
        client_from_env()
