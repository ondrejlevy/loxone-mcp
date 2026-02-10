"""Unit tests for MCP server lifecycle and error handling (server.py).

Tests LoxoneMCPServer init, properties, state UUID map building,
error classes, and format_error_response.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loxone_mcp.server import (
    AccessDeniedError,
    LoxoneConnectionError,
    LoxoneMCPServer,
    MCPError,
    ResourceNotFoundError,
    ToolExecutionError,
    ToolNotFoundError,
    format_error_response,
)


def _make_config() -> MagicMock:
    """Create a mock RootConfig."""
    config = MagicMock()
    config.loxone.host = "192.168.1.100"
    config.loxone.port = 80
    config.loxone.username = "admin"
    config.loxone.password = "pass"
    config.loxone.use_tls = False
    config.structure_cache.ttl_seconds = 3600
    config.structure_cache.change_detection_interval = 300
    config.server.debug = False
    return config


# --- Error Classes ---


class TestMCPError:
    def test_default_code(self) -> None:
        err = MCPError("something broke")
        assert err.message == "something broke"
        assert err.code == -32603

    def test_custom_code(self) -> None:
        err = MCPError("custom", code=-32000)
        assert err.code == -32000

    def test_str(self) -> None:
        err = MCPError("test error")
        assert str(err) == "test error"


class TestResourceNotFoundError:
    def test_init(self) -> None:
        err = ResourceNotFoundError("loxone://missing")
        assert "Resource not found" in err.message
        assert err.uri == "loxone://missing"
        assert err.code == -32002


class TestToolNotFoundError:
    def test_init(self) -> None:
        err = ToolNotFoundError("unknown_tool")
        assert "Tool not found" in err.message
        assert err.name == "unknown_tool"
        assert err.code == -32601


class TestToolExecutionError:
    def test_init(self) -> None:
        err = ToolExecutionError("my_tool", "it crashed")
        assert "my_tool" in err.message
        assert "it crashed" in err.message
        assert err.tool_name == "my_tool"
        assert err.detail == "it crashed"
        assert err.code == -32603


class TestAccessDeniedError:
    def test_init(self) -> None:
        err = AccessDeniedError("control", "read-only")
        assert "Access denied" in err.message
        assert err.operation == "control"
        assert err.mode == "read-only"
        assert err.code == -32003


class TestLoxoneConnectionError:
    def test_init(self) -> None:
        err = LoxoneConnectionError("timeout")
        assert "connection error" in err.message.lower()
        assert err.code == -32004


class TestFormatErrorResponse:
    def test_format(self) -> None:
        err = MCPError("test")
        result = format_error_response(err)
        assert len(result) == 1
        assert result[0].type == "text"
        assert "test" in result[0].text

    def test_format_resource_not_found(self) -> None:
        err = ResourceNotFoundError("loxone://x")
        result = format_error_response(err)
        assert "Resource not found" in result[0].text


# --- Server Init and Properties ---


class TestLoxoneMCPServerInit:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    def test_init(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        assert server.config is config
        assert server.mcp_server is not None
        assert server.state_manager is not None

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    def test_stdio_write_stream_initially_none(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        assert server._stdio_write_stream is None


class TestBuildStateUuidMap:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    def test_empty_structure(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._cache = MagicMock()
        server._cache.structure = None

        result = server._build_state_uuid_map()
        assert result == {}

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    def test_with_components(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)

        mock_comp = MagicMock()
        mock_comp.uuid = "comp-uuid-1"
        mock_comp.states = {"value": "state-uuid-1", "text": "state-uuid-2/0"}

        mock_structure = MagicMock()
        mock_structure.controls = {"comp-uuid-1": mock_comp}

        server._cache = MagicMock()
        server._cache.structure = mock_structure

        result = server._build_state_uuid_map()
        assert "state-uuid-1" in result
        assert result["state-uuid-1"] == ("comp-uuid-1", "value")
        # Path with "/" should extract the first part
        assert "state-uuid-2" in result
        assert result["state-uuid-2"] == ("comp-uuid-1", "text")


class TestShutdown:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_shutdown(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._ws_client = AsyncMock()
        server._http_client = AsyncMock()
        server._state_manager = AsyncMock()
        server._structure_poll_task = None
        server._notification_flush_task = None

        await server.shutdown()

        server._ws_client.stop.assert_awaited_once()
        server._http_client.close.assert_awaited_once()

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_shutdown_with_running_tasks(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)
        server._ws_client = AsyncMock()
        server._http_client = AsyncMock()
        server._state_manager = AsyncMock()
        server._structure_poll_task = asyncio.create_task(asyncio.sleep(100))
        server._notification_flush_task = asyncio.create_task(asyncio.sleep(100))

        await server.shutdown()

        assert server._structure_poll_task.cancelled() or server._structure_poll_task.done()
        assert server._notification_flush_task.cancelled() or server._notification_flush_task.done()


class TestInitialize:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_initialize_success(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        mock_structure = MagicMock()
        mock_structure.controls = {"c1": MagicMock(uuid="u1", states={})}
        mock_structure.rooms = {}
        mock_structure.categories = {}

        # Use MagicMock base + set only async methods to avoid unawaited coroutines
        http_client = MagicMock()
        http_client.fetch_structure_file = AsyncMock(return_value=mock_structure)
        server._http_client = http_client

        ws_client = MagicMock()
        ws_client.connect = AsyncMock()
        ws_client.authenticate = AsyncMock(return_value=True)
        ws_client.enable_status_updates = AsyncMock()
        server._ws_client = ws_client

        state_mgr = MagicMock()
        state_mgr.on_structure_loaded = AsyncMock()
        server._state_manager = state_mgr

        authenticator = MagicMock()
        authenticator.start_token_refresh = AsyncMock()
        server._authenticator = authenticator

        server._cache = MagicMock()
        server._cache.structure = mock_structure

        await server.initialize()

        http_client.fetch_structure_file.assert_awaited_once()
        ws_client.connect.assert_awaited_once()
        ws_client.authenticate.assert_awaited_once()
        ws_client.enable_status_updates.assert_awaited_once()

        # Cleanup background tasks
        if server._structure_poll_task:
            server._structure_poll_task.cancel()
        if server._notification_flush_task:
            server._notification_flush_task.cancel()
        await asyncio.sleep(0)

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_initialize_ws_auth_fail(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        mock_structure = MagicMock()
        mock_structure.controls = {}
        mock_structure.rooms = {}
        mock_structure.categories = {}

        http_client = MagicMock()
        http_client.fetch_structure_file = AsyncMock(return_value=mock_structure)
        server._http_client = http_client

        ws_client = MagicMock()
        ws_client.connect = AsyncMock()
        ws_client.authenticate = AsyncMock(return_value=False)
        server._ws_client = ws_client

        state_mgr = MagicMock()
        state_mgr.on_structure_loaded = AsyncMock()
        server._state_manager = state_mgr

        server._cache = MagicMock()
        server._cache.structure = mock_structure

        await server.initialize()
        # Should continue even if WebSocket auth fails

        if server._structure_poll_task:
            server._structure_poll_task.cancel()
        if server._notification_flush_task:
            server._notification_flush_task.cancel()
        await asyncio.sleep(0)

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_initialize_structure_load_fails(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._http_client = AsyncMock()
        server._http_client.fetch_structure_file = AsyncMock(
            side_effect=ConnectionError("fail")
        )

        with pytest.raises(ConnectionError):
            await server.initialize()


class TestOnStateUpdate:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_on_state_update(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._state_manager = AsyncMock()

        await server._on_state_update("comp-1", "value", 42.0)
        server._state_manager.on_state_update.assert_awaited_once_with("comp-1", "value", 42.0)


class TestOnWsReconnect:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_on_ws_reconnect(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._state_manager = AsyncMock()

        mock_structure = MagicMock()
        mock_structure.controls = {}
        server._http_client = AsyncMock()
        server._http_client.fetch_structure_file = AsyncMock(return_value=mock_structure)
        server._ws_client = MagicMock()
        server._cache = MagicMock()
        server._cache.structure = mock_structure

        await server._on_ws_reconnect()
        server._state_manager.on_websocket_reconnect.assert_awaited_once()
        server._http_client.fetch_structure_file.assert_awaited_once()


class TestSendMcpNotification:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_send_notification(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        # Should not raise
        await server._send_mcp_notification("loxone://components")


class TestRefreshTokenCallback:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_refresh_success(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import json

        config = _make_config()
        server = LoxoneMCPServer(config)

        mock_ws_conn = AsyncMock()
        mock_ws_conn.send = AsyncMock()
        mock_ws_conn.recv = AsyncMock(
            return_value=json.dumps({"LL": {"Code": "200", "value": {"token": "new"}}})
        )
        server._ws_client = MagicMock()
        server._ws_client.is_connected = True
        server._ws_client._ws = mock_ws_conn
        server._authenticator = MagicMock()
        server._authenticator.build_refresh_command = MagicMock(return_value="refresh/cmd")

        result = await server._refresh_token_callback()
        assert result is True

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_refresh_not_connected(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._ws_client = MagicMock()
        server._ws_client.is_connected = False

        result = await server._refresh_token_callback()
        assert result is False

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_refresh_exception(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        config = _make_config()
        server = LoxoneMCPServer(config)
        server._ws_client = MagicMock()
        server._ws_client.is_connected = True
        server._ws_client._ws = AsyncMock()
        server._ws_client._ws.send = AsyncMock(side_effect=Exception("fail"))
        server._authenticator = MagicMock()
        server._authenticator.build_refresh_command = MagicMock(return_value="cmd")

        result = await server._refresh_token_callback()
        assert result is False


class TestPollStructureChanges:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_poll_detects_change(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        mock_structure = MagicMock()
        mock_structure.controls = {}

        http_client = MagicMock()
        call_count = 0

        async def check_changed() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return True
            raise asyncio.CancelledError()

        http_client.check_structure_changed = check_changed
        http_client.fetch_structure_file = AsyncMock(return_value=mock_structure)
        server._http_client = http_client

        state_mgr = MagicMock()
        state_mgr.on_structure_loaded = AsyncMock()
        server._state_manager = state_mgr

        server._ws_client = MagicMock()
        server._cache = MagicMock()
        server._cache.structure = mock_structure

        with patch("loxone_mcp.server.asyncio.sleep", new_callable=AsyncMock):
            await server._poll_structure_changes()

        assert call_count >= 1

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_poll_exception_continues(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        call_count = 0

        async def check_changed() -> bool:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("network error")
            raise asyncio.CancelledError()

        http_client = MagicMock()
        http_client.check_structure_changed = check_changed
        server._http_client = http_client

        with patch("loxone_mcp.server.asyncio.sleep", new_callable=AsyncMock):
            await server._poll_structure_changes()


class TestFlushNotificationsLoop:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_flush_loop_cancelled(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)
        server._state_manager = AsyncMock()

        with patch(
            "loxone_mcp.server.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            await server._flush_notifications_loop()

    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_flush_loop_exception(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        call_count = 0

        async def flush() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("flush error")
            raise asyncio.CancelledError()

        state_mgr = MagicMock()
        state_mgr.flush_notifications = flush
        server._state_manager = state_mgr

        with patch("loxone_mcp.server.asyncio.sleep", new_callable=AsyncMock):
            await server._flush_notifications_loop()


class TestFullShutdown:
    @patch("loxone_mcp.server.LoxoneWebSocket")
    @patch("loxone_mcp.server.LoxoneClient")
    @patch("loxone_mcp.server.LoxoneAuthenticator")
    @patch("loxone_mcp.server.StateCache")
    @patch("loxone_mcp.server.StateManager")
    async def test_shutdown_full(
        self,
        mock_state_mgr: MagicMock,
        mock_cache: MagicMock,
        mock_auth: MagicMock,
        mock_client: MagicMock,
        mock_ws: MagicMock,
    ) -> None:
        import asyncio

        config = _make_config()
        server = LoxoneMCPServer(config)

        ws_client = MagicMock()
        ws_client.stop = AsyncMock()
        server._ws_client = ws_client

        http_client = MagicMock()
        http_client.close = AsyncMock()
        server._http_client = http_client

        state_mgr = MagicMock()
        state_mgr.flush_notifications = AsyncMock()
        server._state_manager = state_mgr

        server._structure_poll_task = asyncio.create_task(asyncio.sleep(100))
        server._notification_flush_task = asyncio.create_task(asyncio.sleep(100))

        await server.shutdown()

        ws_client.stop.assert_awaited_once()
        http_client.close.assert_awaited_once()
        state_mgr.flush_notifications.assert_awaited_once()
