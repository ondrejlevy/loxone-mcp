"""Integration tests for User Story 3: Secure Remote Access.

Tests Streamable HTTP transport, authentication, credential passthrough,
health/metrics endpoints, and notification broadcasting.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from loxone_mcp.config import (
    AccessControlConfig,
    AuditConfig,
    LoxoneConfig,
    MetricsConfig,
    RootConfig,
    ServerConfig,
    StructureCacheConfig,
)
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager
from loxone_mcp.transport.streamable_http import (
    _active_write_streams,
    broadcast_notification,
    create_starlette_app,
    extract_credentials,
)

# --- Fixtures ---


def make_mock_server() -> MagicMock:
    """Create a mock LoxoneMCPServer."""
    server = MagicMock()
    server.config = RootConfig(
        server=ServerConfig(),
        loxone=LoxoneConfig(host="192.168.1.100", username="test", password="test"),
        access_control=AccessControlConfig(),
        metrics=MetricsConfig(),
        audit=AuditConfig(),
        structure_cache=StructureCacheConfig(),
    )
    cache = StateCache()
    server.state_manager = StateManager(cache)
    server._cache = cache
    server._ws_client = MagicMock()
    server._ws_client.is_connected = True
    server._http_client = AsyncMock()

    # Mock mcp_server for StreamableHTTPSessionManager
    mcp_server = MagicMock()
    mcp_server.run = AsyncMock()
    server.mcp_server = mcp_server
    return server


# --- Credential Extraction Tests (T024b) ---


class TestCredentialExtraction:
    """Tests for HTTP header authentication extraction."""

    def _make_request(self, headers: dict[str, str]) -> MagicMock:
        """Create a mock Starlette Request with headers."""
        request = MagicMock()
        lower_headers = {k.lower(): v for k, v in headers.items()}
        request.headers = MagicMock()
        request.headers.get = lambda key, default="": lower_headers.get(key.lower(), default)
        return request

    def test_custom_headers(self) -> None:
        request = self._make_request(
            {
                "X-Loxone-Username": "admin",
                "X-Loxone-Password": "secret123",
            }
        )
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "secret123"

    def test_basic_auth_header(self) -> None:
        credentials = base64.b64encode(b"admin:secret123").decode("utf-8")
        request = self._make_request({"Authorization": f"Basic {credentials}"})
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "secret123"

    def test_basic_auth_with_colon_in_password(self) -> None:
        credentials = base64.b64encode(b"admin:pass:word:123").decode("utf-8")
        request = self._make_request({"Authorization": f"Basic {credentials}"})
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "pass:word:123"

    def test_no_credentials(self) -> None:
        request = self._make_request({})
        username, password = extract_credentials(request)
        assert username is None
        assert password is None

    def test_invalid_basic_auth(self) -> None:
        request = self._make_request({"Authorization": "Basic invalid-base64!!!"})
        username, password = extract_credentials(request)
        assert username is None
        assert password is None

    def test_custom_headers_take_priority(self) -> None:
        credentials = base64.b64encode(b"basic_user:basic_pass").decode("utf-8")
        request = self._make_request(
            {
                "X-Loxone-Username": "custom_user",
                "X-Loxone-Password": "custom_pass",
                "Authorization": f"Basic {credentials}",
            }
        )
        username, password = extract_credentials(request)
        assert username == "custom_user"
        assert password == "custom_pass"


# --- HTTP Transport Tests ---


class TestHTTPTransport:
    """Tests for Streamable HTTP endpoint handling."""

    @pytest.fixture
    def app_client(self) -> TestClient:
        server = make_mock_server()
        app = create_starlette_app(server)
        return TestClient(app, raise_server_exceptions=False)

    def test_health_endpoint(self, app_client: TestClient) -> None:
        response = app_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "websocket_connected" in data

    def test_mcp_post_without_session(self, app_client: TestClient) -> None:
        """POST to /mcp without initialize should get protocol error from SDK."""
        response = app_client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
        # SDK handles the error — returns 4xx
        assert response.status_code >= 400

    def test_mcp_post_invalid_content_type(self, app_client: TestClient) -> None:
        """POST with wrong content type should return error."""
        response = app_client.post(
            "/mcp",
            content="not-json",
            headers={
                "Content-Type": "text/plain",
                "Accept": "application/json, text/event-stream",
            },
        )
        assert response.status_code >= 400

    def test_cors_preflight(self, app_client: TestClient) -> None:
        response = app_client.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_metrics_endpoint(self, app_client: TestClient) -> None:
        response = app_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_mcp_get_without_session_returns_error(self, app_client: TestClient) -> None:
        """GET to /mcp without valid session returns error."""
        response = app_client.get("/mcp")
        assert response.status_code >= 400

    def test_mcp_delete_without_session_returns_error(self, app_client: TestClient) -> None:
        """DELETE to /mcp without valid session returns error."""
        response = app_client.delete(
            "/mcp",
            headers={"Mcp-Session-Id": "nonexistent"},
        )
        assert response.status_code >= 400


# --- Notification Broadcasting Tests ---


class TestNotificationBroadcast:
    """Tests for server-initiated notification broadcasting."""

    async def test_broadcast_to_empty_sessions(self) -> None:
        """Broadcasting with no active sessions should not raise."""
        _active_write_streams.clear()
        await broadcast_notification("notifications/resources/updated", {"uri": "loxone://test"})

    async def test_broadcast_queues_notification(self) -> None:
        """Notification should be sent to all active write streams."""
        _active_write_streams.clear()

        mock_ws = AsyncMock()
        _active_write_streams.add(mock_ws)

        try:
            await broadcast_notification(
                "notifications/resources/updated",
                {"uri": "loxone://components"},
            )
            mock_ws.send.assert_called_once()
            msg = mock_ws.send.call_args[0][0]
            assert msg.message.root.method == "notifications/resources/updated"
        finally:
            _active_write_streams.clear()

    async def test_broadcast_to_multiple_sessions(self) -> None:
        """Notification should reach all sessions."""
        _active_write_streams.clear()

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        _active_write_streams.add(ws1)
        _active_write_streams.add(ws2)

        try:
            await broadcast_notification("notifications/resources/list_changed")
            ws1.send.assert_called_once()
            ws2.send.assert_called_once()
        finally:
            _active_write_streams.clear()

    async def test_broadcast_dead_session_cleanup(self) -> None:
        """Dead sessions should be cleaned up without affecting live ones."""
        _active_write_streams.clear()

        good = AsyncMock()
        dead = AsyncMock()
        dead.send.side_effect = Exception("closed")
        _active_write_streams.add(good)
        _active_write_streams.add(dead)

        try:
            await broadcast_notification("notifications/resources/updated", {"uri": "test"})
            good.send.assert_called_once()
            assert dead not in _active_write_streams
            assert good in _active_write_streams
        finally:
            _active_write_streams.clear()
