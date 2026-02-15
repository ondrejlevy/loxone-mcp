"""Stdio transport for MCP protocol.

Provides stdin/stdout JSON-RPC transport for local AI systems
running on the same machine as the MCP server, avoiding HTTP overhead.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()


async def run_stdio_transport(server: LoxoneMCPServer) -> None:
    """Run the MCP server over stdio transport (T066).

    Reads JSON-RPC requests from stdin, processes them through the
    MCP server, and writes responses to stdout.

    Handles graceful shutdown on EOF (T068).

    Args:
        server: LoxoneMCPServer instance
    """
    from mcp.server.stdio import stdio_server

    logger.info("stdio_transport_starting")

    try:
        async with stdio_server() as (read_stream, write_stream):
            # Store write stream for notifications (T069)
            server._stdio_write_stream = write_stream

            init_options = server.mcp_server.create_initialization_options()
            await server.mcp_server.run(read_stream, write_stream, init_options)
    except asyncio.CancelledError:
        logger.info("stdio_transport_cancelled")
    except Exception:
        logger.exception("stdio_transport_error")
    finally:
        server._stdio_write_stream = None
        logger.info("stdio_transport_stopped")


async def send_stdio_notification(
    server: LoxoneMCPServer,
    notification: dict[str, Any],
) -> None:
    """Send an MCP notification via stdout (T069).

    Constructs a proper SessionMessage and sends it through the MCP SDK
    write stream so it's serialized as a valid JSON-RPC notification.

    Args:
        server: LoxoneMCPServer instance
        notification: JSON-RPC notification dict with 'method' and 'params'
    """
    write_stream = getattr(server, "_stdio_write_stream", None)
    if write_stream is None:
        return

    try:
        from mcp.shared.session import SessionMessage  # type: ignore[attr-defined]
        from mcp.types import JSONRPCMessage, JSONRPCNotification

        # Build a proper JSON-RPC notification via the SDK types
        jsonrpc_notification = JSONRPCNotification(
            jsonrpc="2.0",
            method=notification.get("method", ""),
            params=notification.get("params"),
        )
        message = JSONRPCMessage(root=jsonrpc_notification)
        session_message = SessionMessage(message=message)

        await write_stream.send(session_message)
        logger.debug("stdio_notification_sent", method=notification.get("method"))
    except Exception:
        logger.exception("stdio_notification_error")
