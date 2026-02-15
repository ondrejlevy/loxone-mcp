"""MCP notification sender.

Sends resources/updated notifications to connected clients when
Loxone component states change. Routes to both HTTP/SSE and stdio
transport layers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()


async def send_resource_updated(server: LoxoneMCPServer, uri: str) -> None:
    """Send a resources/updated MCP notification.

    Called by StateManager when Loxone states change. Routes the
    notification through the appropriate transport layer.

    Args:
        server: LoxoneMCPServer instance
        uri: URI of the changed resource (e.g., "loxone://components")
    """
    # Broadcast via Streamable HTTP to connected MCP sessions
    try:
        from loxone_mcp.transport.streamable_http import broadcast_notification

        await broadcast_notification(
            "notifications/resources/updated",
            {"uri": uri},
        )
    except ImportError:
        pass

    # Send via stdio transport if connected
    try:
        from loxone_mcp.transport.stdio import send_stdio_notification

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {"uri": uri},
        }
        await send_stdio_notification(server, notification)
    except ImportError:
        pass

    logger.debug("mcp_resource_updated", uri=uri)


async def send_resource_list_changed(server: LoxoneMCPServer) -> None:
    """Send a resources/list_changed MCP notification.

    Indicates that the list of available resources has changed.
    """
    # Broadcast via Streamable HTTP to connected MCP sessions
    try:
        from loxone_mcp.transport.streamable_http import broadcast_notification

        await broadcast_notification("notifications/resources/list_changed")
    except ImportError:
        pass

    # Send via stdio transport if connected
    try:
        from loxone_mcp.transport.stdio import send_stdio_notification

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/list_changed",
        }
        await send_stdio_notification(server, notification)
    except ImportError:
        pass

    logger.debug("mcp_resource_list_changed")
