"""Streamable HTTP transport for MCP protocol.

Uses the MCP SDK's StreamableHTTPSessionManager for full protocol handling.
Starlette provides the ASGI web framework, uvicorn runs the server.
All JSON-RPC framing, capability negotiation, and SSE streaming are
handled by the SDK — no custom dispatch needed.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyio.streams.memory import MemoryObjectSendStream
    from mcp.server.lowlevel import Server
    from starlette.requests import Request

    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()

# Registry of active write streams for notification broadcasting.
# Populated by _tracked_run() for each session, cleaned up on exit.
_active_write_streams: set[MemoryObjectSendStream[SessionMessage]] = set()


# --- Authentication (T024b) ---


def extract_credentials(request: Request) -> tuple[str | None, str | None]:
    """Extract Loxone credentials from HTTP request headers.

    Supports:
    1. Custom headers: X-Loxone-Username / X-Loxone-Password
    2. Basic Authorization header

    Returns:
        Tuple of (username, password) or (None, None)
    """
    # Try custom headers first
    username = request.headers.get("x-loxone-username")
    password = request.headers.get("x-loxone-password")
    if username and password:
        return username, password

    # Try Basic auth
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Basic "):
        import base64

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            if ":" in decoded:
                username, password = decoded.split(":", 1)
                return username, password
        except Exception:
            pass

    return None, None


# --- Notification Broadcasting ---


def _patch_server_for_broadcast(mcp_server: Server) -> None:
    """Wrap Server.run() to track active write_streams for broadcasting.

    Each MCP session gets its own Server.run() call with unique streams.
    By wrapping run(), we capture the write_stream when a session starts
    and remove it when it ends. This allows broadcast_notification() to
    push server-initiated notifications to all connected sessions.
    """
    original_run = mcp_server.run

    async def tracked_run(
        read_stream: Any,
        write_stream: MemoryObjectSendStream[SessionMessage],
        initialization_options: Any,
        **kwargs: Any,
    ) -> None:
        _active_write_streams.add(write_stream)
        logger.debug("session_write_stream_registered", total=len(_active_write_streams))
        try:
            await original_run(read_stream, write_stream, initialization_options, **kwargs)
        finally:
            _active_write_streams.discard(write_stream)
            logger.debug("session_write_stream_removed", total=len(_active_write_streams))

    mcp_server.run = tracked_run  # type: ignore[assignment]


async def broadcast_notification(method: str, params: dict[str, Any] | None = None) -> None:
    """Broadcast a JSON-RPC notification to all connected MCP sessions.

    Constructs a proper SessionMessage and sends it through each
    session's write_stream — the same path the SDK uses internally.

    Args:
        method: Notification method (e.g., "notifications/resources/updated")
        params: Optional notification parameters
    """
    if not _active_write_streams:
        return

    notification_data: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params:
        notification_data["params"] = params

    jsonrpc_notification = JSONRPCNotification(**notification_data)
    session_message = SessionMessage(
        message=JSONRPCMessage(jsonrpc_notification),
        metadata=None,
    )

    dead_streams: list[MemoryObjectSendStream[SessionMessage]] = []
    for ws in list(_active_write_streams):
        try:
            await ws.send(session_message)
        except Exception:
            logger.warning("broadcast_send_failed")
            dead_streams.append(ws)

    for dead in dead_streams:
        _active_write_streams.discard(dead)

    if _active_write_streams:
        logger.debug(
            "notification_broadcast",
            method=method,
            sessions=len(_active_write_streams),
        )


# --- Health Check (T044a) ---


async def handle_health(request: Request) -> Response:
    """Health check endpoint."""
    server: LoxoneMCPServer = request.app.state.loxone_server
    ws_connected = server._ws_client.is_connected if hasattr(server, "_ws_client") else False
    cache_stats = server._cache.stats if hasattr(server, "_cache") else {}

    return JSONResponse(
        {
            "status": "ok",
            "websocket_connected": ws_connected,
            "cache_stats": cache_stats,
        }
    )


# --- Metrics Endpoint (T052) ---


async def handle_metrics(request: Request) -> Response:
    """Expose Prometheus metrics at /metrics endpoint."""
    from loxone_mcp.metrics.collector import get_metrics

    metrics_data = get_metrics()
    return PlainTextResponse(
        content=metrics_data,
        media_type="text/plain",
    )


# --- Application Factory ---


def create_starlette_app(server: LoxoneMCPServer) -> Starlette:
    """Create a Starlette ASGI app with SDK-managed MCP transport.

    The SDK's StreamableHTTPSessionManager handles:
    - JSON-RPC framing and validation
    - MCP protocol version negotiation
    - Capability exchange (initialize/initialized)
    - Method routing to registered handlers
    - SSE streaming for responses and notifications
    - Session management and cleanup

    Args:
        server: LoxoneMCPServer instance with configured mcp_server

    Returns:
        Configured Starlette application
    """
    mcp_server = server.mcp_server

    # Patch Server.run() to track write_streams for broadcasting
    _patch_server_for_broadcast(mcp_server)

    session_manager = StreamableHTTPSessionManager(
        app=mcp_server,
        json_response=False,
        stateless=False,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            logger.info("streamable_http_session_manager_started")
            yield
        _active_write_streams.clear()
        logger.info("streamable_http_session_manager_stopped")

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Mount(
                "/mcp",
                app=session_manager.handle_request,
            ),
            Route("/health", handle_health, methods=["GET"]),
            Route("/metrics", handle_metrics, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                allow_headers=[
                    "Content-Type",
                    "Authorization",
                    "X-Loxone-Username",
                    "X-Loxone-Password",
                    "Mcp-Session-Id",
                    "Last-Event-Id",
                ],
                expose_headers=["Mcp-Session-Id"],
            ),
        ],
    )

    # Store server reference for health/metrics endpoints
    app.state.loxone_server = server

    return app


# --- Server Runner ---


async def run_http_server(
    app: Starlette,
    host: str = "0.0.0.0",
    port: int = 8080,
    tls_cert: str | None = None,
    tls_key: str | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run the Starlette app via uvicorn, optionally with TLS.

    If a shutdown_event is provided, uvicorn will be signaled to exit
    gracefully when the event is set, allowing active SSE connections
    and the ASGI lifespan to shut down cleanly without CancelledError.
    """
    import uvicorn

    protocol = "https" if tls_cert else "http"
    logger.info("http_server_starting", host=host, port=port, protocol=protocol)

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        ssl_certfile=tls_cert,
        ssl_keyfile=tls_key,
        log_level="warning",
    )
    uvi_server = uvicorn.Server(config)

    # Monitor shutdown event and signal uvicorn to exit gracefully
    shutdown_watcher: asyncio.Task[None] | None = None
    if shutdown_event:
        async def _watch_shutdown() -> None:
            await shutdown_event.wait()
            logger.debug("uvicorn_graceful_shutdown_requested")
            uvi_server.should_exit = True

        shutdown_watcher = asyncio.create_task(_watch_shutdown())

    try:
        await uvi_server.serve()
    finally:
        if shutdown_watcher and not shutdown_watcher.done():
            shutdown_watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shutdown_watcher

    logger.info("http_server_stopped")
