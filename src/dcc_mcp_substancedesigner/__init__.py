"""Adobe Substance Designer adapter for DCC MCP Core."""

from dcc_mcp_substancedesigner.__version__ import __version__
from dcc_mcp_substancedesigner.bridge import (
    DEFAULT_SD_BRIDGE_PORT,
    HEADER_SIZE,
    MAX_MESSAGE_BYTES,
    SubstanceDesignerBridgeClient,
    SubstanceDesignerBridgeError,
)
from dcc_mcp_substancedesigner.commands import (
    ENV_SD_BRIDGE_HOST,
    ENV_SD_BRIDGE_PORT,
    SubstanceDesignerCommands,
    client_from_env,
    commands_from_env,
)
from dcc_mcp_substancedesigner.server import (
    DEFAULT_GATEWAY_PORT,
    DEFAULT_MCP_PORT,
    SERVER_NAME,
    SubstanceDesignerMcpServer,
    SubstanceDesignerServerOptions,
    get_server,
    start_server,
    stop_server,
)

__all__ = [
    "__version__",
    "DEFAULT_MCP_PORT",
    "DEFAULT_GATEWAY_PORT",
    "DEFAULT_SD_BRIDGE_PORT",
    "ENV_SD_BRIDGE_HOST",
    "ENV_SD_BRIDGE_PORT",
    "HEADER_SIZE",
    "MAX_MESSAGE_BYTES",
    "SERVER_NAME",
    "SubstanceDesignerBridgeClient",
    "SubstanceDesignerBridgeError",
    "SubstanceDesignerCommands",
    "SubstanceDesignerMcpServer",
    "SubstanceDesignerServerOptions",
    "client_from_env",
    "commands_from_env",
    "get_server",
    "start_server",
    "stop_server",
]
