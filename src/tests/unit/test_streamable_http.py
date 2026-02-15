"""Unit tests for Streamable HTTP transport (transport/streamable_http.py).

Tests credential extraction, health/metrics endpoints, CORS,
MCP endpoint (delegated to SDK), and notification broadcasting.
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

from starlette.testclient import TestClient

from loxone_mcp.transport.streamable_http import (
    _active_write_streams,
    broadcast_notification,
    extract_credentials,
)


def _mock_server() -> MagicMock:
    server = MagicMock()
    server._ws_client.is_connected = True
    server._cache.stats = {
        "structure_valid": True,
        "component_count": 5,
    }
    # Mock mcp_server with enough for create_starlette_app
    mcp_server = MagicMock()
    mcp_server.run = AsyncMock()
    server.mcp_server = mcp_server
    return server


def _make_starlette_request(headers: dict[str, str]) -> MagicMock:
    """Create a mock Starlette Request with dict-like headers."""
    request = MagicMock()
    # Starlette headers are case-insensitive; use lowercase keys
    lower_headers = {k.lower(): v for k, v in headers.items()}
    request.headers = MagicMock()
    request.headers.get = lambda key, default="": lower_headers.get(key.lower(), default)
    return request


# --- Credential Extraction Tests ---


class TestExtractCredentials:
    def test_custom_headers(self) -> None:
        request = _make_starlette_request(
            {
                "X-Loxone-Username": "admin",
                "X-Loxone-Password": "secret",
            }
        )
        u, p = extract_credentials(request)
        assert u == "admin"
        assert p == "secret"

    def test_basic_auth(self) -> None:
        encoded = base64.b64encode(b"user:pass").decode()
        request = _make_starlette_request({"Authorization": f"Basic {encoded}"})
        u, p = extract_credentials(request)
        assert u == "user"
        assert p == "pass"

    def test_no_credentials(self) -> None:
        request = _make_starlette_request({})
        u, p = extract_credentials(request)
        assert u is None
        assert p is None

    def test_invalid_basic_auth(self) -> None:
        request = _make_starlette_request({"Authorization": "Basic !!!invalid!!!"})
        u, p = extract_credentials(request)
        assert u is None
        assert p is None

    def test_basic_auth_with_colon_in_password(self) -> None:
        encoded = base64.b64encode(b"user:pa:ss:word").decode()
        request = _make_starlette_request({"Authorization": f"Basic {encoded}"})
        u, p = extract_credentials(request)
        assert u == "user"
        assert p == "pa:ss:word"


# --- Notification Broadcasting Tests ---


class TestBroadcastNotification:
    async def test_broadcast_no_streams(self) -> None:
        """Broadcasting with no active streams should be a no-op."""
        _active_write_streams.clear()
        await broadcast_notification("notifications/resources/updated", {"uri": "loxone://test"})
        # Should not raise

    async def test_broadcast_sends_to_all(self) -> None:
        """Broadcasting should send to all active write streams."""
        _active_write_streams.clear()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        _active_write_streams.add(mock_ws1)
        _active_write_streams.add(mock_ws2)

        try:
            await broadcast_notification(
                "notifications/resources/updated", {"uri": "loxone://test"}
            )

            mock_ws1.send.assert_called_once()
            mock_ws2.send.assert_called_once()

            # Verify the message structure
            msg = mock_ws1.send.call_args[0][0]
            assert msg.message.root.method == "notifications/resources/updated"
        finally:
            _active_write_streams.clear()

    async def test_broadcast_removes_dead_streams(self) -> None:
        """Failed write streams should be removed."""
        _active_write_streams.clear()

        mock_good = AsyncMock()
        mock_dead = AsyncMock()
        mock_dead.send.side_effect = Exception("closed")
        _active_write_streams.add(mock_good)
        _active_write_streams.add(mock_dead)

        try:
            await broadcast_notification("notifications/resources/list_changed")

            mock_good.send.assert_called_once()
            mock_dead.send.assert_called_once()
            # Dead stream should be removed
            assert mock_dead not in _active_write_streams
            assert mock_good in _active_write_streams
        finally:
            _active_write_streams.clear()

    async def test_broadcast_without_params(self) -> None:
        """Broadcasting without params should work."""
        _active_write_streams.clear()

        mock_ws = AsyncMock()
        _active_write_streams.add(mock_ws)

        try:
            await broadcast_notification("notifications/resources/list_changed")

            msg = mock_ws.send.call_args[0][0]
            assert msg.message.root.method == "notifications/resources/list_changed"
        finally:
            _active_write_streams.clear()


# --- Health Endpoint Tests ---


class TestHandleHealth:
    def test_health_endpoint(self) -> None:
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert "websocket_connected" in data


# --- Metrics Endpoint Tests ---


class TestHandleMetrics:
    def test_metrics_endpoint(self) -> None:
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            assert "text/plain" in resp.headers["content-type"]


# --- CORS Tests ---


class TestCorsMiddleware:
    def test_cors_headers_present(self) -> None:
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
            assert "access-control-allow-origin" in resp.headers

    def test_options_preflight(self) -> None:
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.options(
                "/mcp",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert resp.status_code == 200
            assert "access-control-allow-origin" in resp.headers


# --- MCP Endpoint Tests ---


class TestMcpEndpoint:
    """Test that the /mcp endpoint is mounted and delegates to the SDK."""

    def test_mcp_post_without_init_returns_error(self) -> None:
        """POST to /mcp without initialization should get a protocol error."""
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": 1,
                },
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
            )
            # SDK should return an error (no init, no session) — not crash
            assert resp.status_code in (400, 200)

    def test_mcp_get_without_session_returns_error(self) -> None:
        """GET to /mcp without session should return an error."""
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = _mock_server()
        app = create_starlette_app(server)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/mcp")
            # SDK returns 4xx for GET without valid session
            assert resp.status_code >= 400
