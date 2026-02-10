"""HTTP+SSE transport for MCP protocol.

Provides HTTP endpoints for MCP JSON-RPC and Server-Sent Events
for real-time notifications. Handles authentication via HTTP headers.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog
from aiohttp import web

if TYPE_CHECKING:
    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()

# Typed application keys (aiohttp 3.9+ best practice)
LOXONE_SERVER_KEY: web.AppKey[Any] = web.AppKey("loxone_server")
SSE_CLIENTS_KEY: web.AppKey[list[asyncio.Queue[dict[str, Any]]]] = web.AppKey("sse_clients")


def create_http_app(server: Any) -> web.Application:
    """Create the aiohttp web application with MCP endpoints.

    Args:
        server: LoxoneMCPServer instance

    Returns:
        Configured aiohttp Application
    """

    loxone_server: LoxoneMCPServer = server

    app = web.Application()
    app[LOXONE_SERVER_KEY] = loxone_server
    app[SSE_CLIENTS_KEY] = []

    # Register routes
    app.router.add_post("/mcp", handle_mcp_request)
    app.router.add_get("/sse", handle_sse)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_options("/mcp", handle_cors_preflight)

    # Add middleware
    app.middlewares.append(cors_middleware)
    app.middlewares.append(error_middleware)

    return app


# --- Middleware ---


@web.middleware
async def cors_middleware(
    request: web.Request,
    handler: Any,
) -> web.StreamResponse:
    """Add CORS headers to all responses."""
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Loxone-Username, X-Loxone-Password"
    )
    return response


@web.middleware
async def error_middleware(
    request: web.Request,
    handler: Any,
) -> web.StreamResponse:
    """Global error handling middleware."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except Exception:
        logger.exception("unhandled_http_error", path=request.path)
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": "Internal server error",
                },
                "id": None,
            },
            status=500,
        )


# --- Authentication (T024b) ---


def extract_credentials(request: web.Request) -> tuple[str | None, str | None]:
    """Extract Loxone credentials from HTTP request headers.

    Supports:
    1. Custom headers: X-Loxone-Username / X-Loxone-Password
    2. Basic Authorization header

    Returns:
        Tuple of (username, password) or (None, None)
    """
    # Try custom headers first
    username = request.headers.get("X-Loxone-Username")
    password = request.headers.get("X-Loxone-Password")
    if username and password:
        return username, password

    # Try Basic auth
    auth_header = request.headers.get("Authorization", "")
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


# --- Handlers ---


async def handle_mcp_request(request: web.Request) -> web.Response:
    """Handle MCP JSON-RPC requests over HTTP (T024a).

    Receives JSON-RPC request, processes it through the MCP server,
    and returns the JSON-RPC response.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None,
            },
            status=400,
        )

    server = request.app[LOXONE_SERVER_KEY]

    # Extract credentials for per-request passthrough (T024c)
    username, password = extract_credentials(request)

    # Process through MCP server
    method = body.get("method", "")
    params = body.get("params", {})
    request_id = body.get("id")

    try:
        result = await _dispatch_mcp_method(server, method, params, username, password)
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id,
            }
        )
    except Exception as e:
        logger.exception("mcp_request_error", method=method)
        return web.json_response(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e),
                },
                "id": request_id,
            },
            status=500,
        )


async def _dispatch_mcp_method(
    server: Any,
    method: str,
    params: dict[str, Any],
    username: str | None = None,
    password: str | None = None,
) -> Any:
    """Dispatch an MCP method to the appropriate handler.

    Args:
        server: LoxoneMCPServer instance
        method: MCP method name (e.g., "resources/list")
        params: Method parameters
        username: Optional per-request username
        password: Optional per-request password

    Returns:
        Method result
    """
    from loxone_mcp.mcp.resources import get_resource_list, handle_read_resource
    from loxone_mcp.mcp.tools import get_tool_list, handle_call_tool

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "resources": {"subscribe": True, "listChanged": True},
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": "loxone-mcp",
                "version": "0.1.0",
            },
        }

    if method == "resources/list":
        resources = await get_resource_list(server)
        return {"resources": [_resource_to_dict(r) for r in resources]}

    if method == "resources/read":
        uri = params.get("uri", "")
        content = await handle_read_resource(server, uri)
        return {"contents": content}

    if method == "tools/list":
        tools = await get_tool_list(server)
        return {"tools": [_tool_to_dict(t) for t in tools]}

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await handle_call_tool(server, name, arguments)
        return {"content": result}

    if method == "ping":
        return {}

    msg = f"Method not found: {method}"
    raise ValueError(msg)


def _resource_to_dict(resource: Any) -> dict[str, Any]:
    """Convert a Resource object to a serializable dict."""
    result: dict[str, Any] = {
        "uri": str(resource.uri),
        "name": resource.name,
    }
    if hasattr(resource, "description") and resource.description:
        result["description"] = resource.description
    if hasattr(resource, "mimeType") and resource.mimeType:
        result["mimeType"] = resource.mimeType
    return result


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    """Convert a Tool object to a serializable dict."""
    result: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description or "",
    }
    if hasattr(tool, "inputSchema") and tool.inputSchema:
        result["inputSchema"] = tool.inputSchema
    return result


# --- SSE Transport (T024d) ---


async def handle_sse(request: web.Request) -> web.StreamResponse:
    """Handle Server-Sent Events connections for MCP notifications.

    Clients connect here to receive real-time notifications when
    Loxone component states change.
    """
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await response.prepare(request)

    # Register this client for notifications
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    sse_clients: list[asyncio.Queue[dict[str, Any]]] = request.app[SSE_CLIENTS_KEY]
    sse_clients.append(queue)

    logger.info("sse_client_connected")

    try:
        while True:
            # Wait for notifications
            notification = await queue.get()
            event_data = json.dumps(notification)
            await response.write(f"data: {event_data}\n\n".encode())
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        sse_clients.remove(queue)
        logger.info("sse_client_disconnected")

    return response


async def broadcast_sse_notification(app: web.Application, notification: dict[str, Any]) -> None:
    """Broadcast a notification to all connected SSE clients."""
    sse_clients: list[asyncio.Queue[dict[str, Any]]] = app[SSE_CLIENTS_KEY]
    for queue in sse_clients:
        try:
            queue.put_nowait(notification)
        except asyncio.QueueFull:
            logger.warning("sse_client_queue_full")


# --- Health Check (T044a) ---


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    server = request.app[LOXONE_SERVER_KEY]
    ws_connected = server._ws_client.is_connected if hasattr(server, "_ws_client") else False
    cache_stats = server._cache.stats if hasattr(server, "_cache") else {}

    return web.json_response(
        {
            "status": "ok",
            "websocket_connected": ws_connected,
            "cache_stats": cache_stats,
        }
    )


# --- Metrics Endpoint (T052) ---


async def handle_metrics(request: web.Request) -> web.Response:
    """Expose Prometheus metrics at /metrics endpoint."""
    from loxone_mcp.metrics.collector import get_metrics

    metrics_data = get_metrics()
    return web.Response(
        body=metrics_data,
        content_type="text/plain",
        charset="utf-8",
    )


# --- CORS ---


async def handle_cors_preflight(request: web.Request) -> web.Response:
    """Handle CORS preflight OPTIONS request."""
    return web.Response(status=204)


# --- Server Runner ---


async def run_http_server(
    app: web.Application,
    host: str = "0.0.0.0",
    port: int = 8080,
    tls_cert: str | None = None,
    tls_key: str | None = None,
) -> None:
    """Run the HTTP server, optionally with TLS."""
    import ssl

    ssl_context: ssl.SSLContext | None = None
    if tls_cert and tls_key:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(tls_cert, tls_key)
        logger.info("tls_enabled", cert=tls_cert)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port, ssl_context=ssl_context)
    await site.start()
    protocol = "https" if ssl_context else "http"
    logger.info("http_server_started", host=host, port=port, protocol=protocol)

    # Keep running until cancelled
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
        logger.info("http_server_stopped")
