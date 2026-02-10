"""MCP server initialization and lifecycle management.

Sets up the MCP server with Resources, Tools, and transport layers.
Manages the Loxone integration lifecycle (connect, auth, state updates).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.lowlevel import Server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)

from loxone_mcp.loxone.auth import LoxoneAuthenticator
from loxone_mcp.loxone.client import LoxoneClient
from loxone_mcp.loxone.structure import parse_structure_file
from loxone_mcp.loxone.websocket import LoxoneWebSocket
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager

if TYPE_CHECKING:
    from loxone_mcp.config import RootConfig

logger = structlog.get_logger()


class LoxoneMCPServer:
    """Orchestrates the MCP server and Loxone integration.

    Lifecycle:
    1. Load configuration
    2. Initialize MCP server with handlers
    3. Connect to Loxone miniserver (WebSocket)
    4. Authenticate and fetch structure file
    5. Enable binary status updates
    6. Serve MCP requests until shutdown
    7. Gracefully close all connections
    """

    def __init__(self, config: RootConfig) -> None:
        self._config = config
        self._cache = StateCache(
            structure_ttl=config.structure_cache.ttl_seconds,
        )
        self._state_manager = StateManager(self._cache)
        self._authenticator = LoxoneAuthenticator(config.loxone)
        self._http_client = LoxoneClient(config.loxone)
        self._ws_client = LoxoneWebSocket(config.loxone, self._authenticator)
        self._mcp_server = self._create_mcp_server()
        self._structure_poll_task: asyncio.Task[None] | None = None
        self._notification_flush_task: asyncio.Task[None] | None = None

    @property
    def mcp_server(self) -> Server:
        """Get the underlying MCP low-level server."""
        return self._mcp_server

    @property
    def state_manager(self) -> StateManager:
        """Access the state manager."""
        return self._state_manager

    @property
    def config(self) -> RootConfig:
        """Access the root configuration."""
        return self._config

    def _create_mcp_server(self) -> Server:
        """Create and configure the MCP low-level server."""
        server = Server("loxone-mcp")

        @server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available MCP resources."""
            # Defer to resource handlers module (registered in Phase 3)
            from loxone_mcp.mcp.resources import get_resource_list

            if self._config.server.debug:
                logger.debug("mcp_request", method="resources/list")
            result = await get_resource_list(self)
            if self._config.server.debug:
                logger.debug("mcp_response", method="resources/list", count=len(result))
            return result

        @server.read_resource()
        async def read_resource(uri: str) -> Any:
            """Read a specific MCP resource."""
            from loxone_mcp.mcp.resources import handle_read_resource

            if self._config.server.debug:
                logger.debug("mcp_request", method="resources/read", uri=str(uri))
            result = await handle_read_resource(self, str(uri))
            if self._config.server.debug:
                logger.debug("mcp_response", method="resources/read", uri=str(uri))
            return result

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available MCP tools."""
            from loxone_mcp.mcp.tools import get_tool_list

            if self._config.server.debug:
                logger.debug("mcp_request", method="tools/list")
            result = await get_tool_list(self)
            if self._config.server.debug:
                logger.debug("mcp_response", method="tools/list", count=len(result))
            return result

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> Any:
            """Execute an MCP tool."""
            from loxone_mcp.mcp.tools import handle_call_tool

            if self._config.server.debug:
                logger.debug("mcp_request", method="tools/call", tool=name, args=arguments)
            result = await handle_call_tool(self, name, arguments or {})
            if self._config.server.debug:
                logger.debug("mcp_response", method="tools/call", tool=name)
            return result

        return server

    async def initialize(self) -> None:
        """Initialize all services and connect to Loxone.

        Fetches structure file, connects WebSocket, and starts background tasks.
        """
        logger.info("server_initializing")

        # Fetch structure file via HTTP
        try:
            structure_data = await self._http_client.fetch_structure_file()
            structure = parse_structure_file(structure_data)
            await self._state_manager.on_structure_loaded(structure)
            logger.info(
                "structure_loaded",
                controls=len(structure.controls),
                rooms=len(structure.rooms),
                categories=len(structure.categories),
            )
        except Exception:
            logger.exception("structure_load_failed")
            raise

        # Build state UUID map for WebSocket binary updates
        state_map = self._build_state_uuid_map()
        self._ws_client.set_state_uuid_map(state_map)

        # Register WebSocket callbacks
        self._ws_client.register_state_callback(self._on_state_update)
        self._ws_client.register_reconnect_callback(self._on_ws_reconnect)

        # Register notification callback on state manager
        self._state_manager.register_notification_callback(self._send_mcp_notification)

        # Connect WebSocket
        try:
            await self._ws_client.connect()
            authenticated = await self._ws_client.authenticate()
            if authenticated:
                await self._ws_client.enable_status_updates()
                self._authenticator.start_token_refresh(self._refresh_token_callback)
                # Metrics (T057)
                from loxone_mcp.metrics.collector import set_websocket_status

                set_websocket_status(True)
            else:
                logger.warning("websocket_auth_failed_continuing_http_only")
        except Exception:
            logger.exception("websocket_connect_failed_continuing_http_only")

        # Start background tasks
        self._structure_poll_task = asyncio.create_task(self._poll_structure_changes())
        self._notification_flush_task = asyncio.create_task(self._flush_notifications_loop())

        logger.info("server_initialized")

    def _build_state_uuid_map(self) -> dict[str, tuple[str, str]]:
        """Build a mapping from state UUIDs to (component_uuid, state_key).

        Used by the WebSocket client to route binary state updates.
        """
        state_map: dict[str, tuple[str, str]] = {}
        structure = self._cache.structure
        if not structure:
            return state_map

        for comp in structure.controls.values():
            for state_key, state_path in comp.states.items():
                # State paths are UUIDs or UUID/suffix patterns
                state_uuid = state_path.split("/")[0] if "/" in state_path else state_path
                state_map[state_uuid] = (comp.uuid, state_key)

        return state_map

    async def _on_state_update(self, component_uuid: str, state_key: str, value: Any) -> None:
        """Handle WebSocket state update → route to state manager."""
        await self._state_manager.on_state_update(component_uuid, state_key, value)

    async def _on_ws_reconnect(self) -> None:
        """Handle WebSocket reconnection → reload structure."""
        await self._state_manager.on_websocket_reconnect()

        # Re-fetch structure file
        try:
            structure_data = await self._http_client.fetch_structure_file()
            structure = parse_structure_file(structure_data)
            await self._state_manager.on_structure_loaded(structure)

            # Rebuild state UUID map
            state_map = self._build_state_uuid_map()
            self._ws_client.set_state_uuid_map(state_map)
            logger.info("structure_reloaded_after_reconnect")
        except Exception:
            logger.exception("structure_reload_failed_after_reconnect")

    async def _send_mcp_notification(self, uri: str) -> None:
        """Send MCP resource change notification to connected clients.

        This is registered with StateManager and called when resources change.
        """
        # The actual notification delivery depends on the transport layer.
        # For HTTP+SSE, notifications are pushed to the SSE stream.
        # For stdio, notifications are written to stdout.
        # This will be fully wired in Phase 3 (T033-T034).
        logger.debug("mcp_notification_sent", uri=uri)

    async def _poll_structure_changes(self) -> None:
        """Periodically check for structure file changes (T035a)."""
        interval = self._config.structure_cache.change_detection_interval
        while True:
            try:
                await asyncio.sleep(interval)
                changed = await self._http_client.check_structure_changed()
                if changed:
                    logger.info("structure_change_detected")
                    structure_data = await self._http_client.fetch_structure_file()
                    structure = parse_structure_file(structure_data)
                    await self._state_manager.on_structure_loaded(structure)
                    state_map = self._build_state_uuid_map()
                    self._ws_client.set_state_uuid_map(state_map)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("structure_poll_error")

    async def _flush_notifications_loop(self) -> None:
        """Periodically flush accumulated state change notifications."""
        while True:
            try:
                await asyncio.sleep(1.0)
                await self._state_manager.flush_notifications()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("notification_flush_error")

    async def _refresh_token_callback(self) -> bool:
        """Callback for token refresh - sends refresh command via WebSocket."""
        if not self._ws_client.is_connected or not self._ws_client._ws:
            return False
        try:
            refresh_cmd = self._authenticator.build_refresh_command()
            await self._ws_client._ws.send(refresh_cmd)
            response = await self._ws_client._ws.recv()
            if isinstance(response, str):
                import json

                data = json.loads(response)
                self._authenticator.process_refresh_response(data)
                return True
        except Exception:
            logger.exception("token_refresh_failed")
        return False

    async def shutdown(self) -> None:
        """Gracefully shut down all services.

        Shutdown order:
        1. Cancel background tasks (structure poll, notification flush)
        2. Flush pending notifications
        3. Close WebSocket connection
        4. Close HTTP client
        5. Flush audit logs
        6. Reset metrics gauges
        """
        logger.info("server_shutting_down")

        # 1. Cancel background tasks
        for task in [self._structure_poll_task, self._notification_flush_task]:
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # 2. Flush pending notifications
        try:
            await self._state_manager.flush_notifications()
        except Exception:
            logger.exception("notification_flush_error_on_shutdown")

        # 3. Stop WebSocket
        await self._ws_client.stop()

        # 4. Close HTTP client
        await self._http_client.close()

        # 5. Flush audit logs
        try:
            from loxone_mcp.audit.logger import get_audit_logger

            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.close()
        except Exception:
            logger.exception("audit_flush_error_on_shutdown")

        # 6. Reset metrics gauges
        try:
            from loxone_mcp.metrics.collector import set_websocket_status

            set_websocket_status(False)
        except Exception:
            pass

        logger.info("server_shutdown_complete")


# --- Global Error Handling (T024) ---


class MCPError(Exception):
    """Base exception for MCP server errors."""

    def __init__(self, message: str, code: int = -32603) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class ResourceNotFoundError(MCPError):
    """Resource URI not found."""

    def __init__(self, uri: str) -> None:
        super().__init__(f"Resource not found: {uri}", code=-32002)
        self.uri = uri


class ToolNotFoundError(MCPError):
    """Tool name not found."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Tool not found: {name}", code=-32601)
        self.name = name


class ToolExecutionError(MCPError):
    """Tool execution failed."""

    def __init__(self, name: str, detail: str) -> None:
        super().__init__(f"Tool execution failed: {name} - {detail}", code=-32603)
        self.tool_name = name
        self.detail = detail


class AccessDeniedError(MCPError):
    """Operation denied by access control."""

    def __init__(self, operation: str, mode: str) -> None:
        super().__init__(
            f"Access denied: {operation} not allowed in {mode} mode",
            code=-32003,
        )
        self.operation = operation
        self.mode = mode


class LoxoneConnectionError(MCPError):
    """Loxone miniserver connection error."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"Loxone connection error: {detail}", code=-32004)


def format_error_response(error: MCPError) -> list[TextContent]:
    """Format an MCPError into MCP-compatible error response."""
    return [TextContent(type="text", text=f"Error: {error.message}")]
