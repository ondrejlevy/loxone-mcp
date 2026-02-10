"""MCP notification sender.

Sends resources/updated notifications to connected clients when
Loxone component states change.
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
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/updated",
        "params": {"uri": uri},
    }

    # Broadcast via SSE to HTTP clients
    try:
        from loxone_mcp.transport.http_sse import broadcast_sse_notification

        # Only broadcast if HTTP app is available
        if hasattr(server, "_http_app") and server._http_app:
            await broadcast_sse_notification(server._http_app, notification)
    except ImportError:
        pass

    logger.debug("mcp_resource_updated", uri=uri)


async def send_resource_list_changed(server: LoxoneMCPServer) -> None:
    """Send a resources/list_changed MCP notification.

    Indicates that the list of available resources has changed.
    """
    notification = {
        "jsonrpc": "2.0",
        "method": "notifications/resources/list_changed",
    }

    try:
        from loxone_mcp.transport.http_sse import broadcast_sse_notification

        if hasattr(server, "_http_app") and server._http_app:
            await broadcast_sse_notification(server._http_app, notification)
    except ImportError:
        pass

    logger.debug("mcp_resource_list_changed")
