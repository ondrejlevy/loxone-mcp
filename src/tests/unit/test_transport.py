"""Unit tests for HTTP+SSE transport (transport/http_sse.py).

Tests app creation, credential extraction, MCP dispatch,
helper conversions, SSE broadcast, and CORS.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from loxone_mcp.transport.http_sse import (
    LOXONE_SERVER_KEY,
    SSE_CLIENTS_KEY,
    _dispatch_mcp_method,
    _resource_to_dict,
    _tool_to_dict,
    broadcast_sse_notification,
    create_http_app,
    extract_credentials,
    handle_cors_preflight,
)


def _mock_server() -> MagicMock:
    server = MagicMock()
    server._ws_client.is_connected = True
    server._cache.stats = {
        "structure_valid": True,
        "component_count": 5,
    }
    return server


class TestCreateHttpApp:
    def test_creates_app(self) -> None:
        server = _mock_server()
        app = create_http_app(server)
        assert isinstance(app, web.Application)
        assert app[LOXONE_SERVER_KEY] is server
        assert SSE_CLIENTS_KEY in app

    def test_routes_registered(self) -> None:
        server = _mock_server()
        app = create_http_app(server)
        routes = [
            r.resource.canonical
            for r in app.router.routes()
            if hasattr(r.resource, "canonical")
        ]
        assert "/mcp" in routes
        assert "/sse" in routes
        assert "/health" in routes
        assert "/metrics" in routes


class TestExtractCredentials:
    def _make_request(self, headers: dict[str, str]) -> MagicMock:
        """Create a mock request with real-like headers access."""
        request = MagicMock()
        # Use a real dict-like for headers
        header_obj = MagicMock()
        header_obj.get = lambda key, default="": headers.get(key, default)
        request.headers = header_obj
        return request

    def test_custom_headers(self) -> None:
        request = self._make_request({
            "X-Loxone-Username": "admin",
            "X-Loxone-Password": "secret",
        })
        u, p = extract_credentials(request)
        assert u == "admin"
        assert p == "secret"

    def test_basic_auth(self) -> None:
        encoded = base64.b64encode(b"user:pass").decode()
        request = self._make_request({
            "Authorization": f"Basic {encoded}",
        })
        u, p = extract_credentials(request)
        assert u == "user"
        assert p == "pass"

    def test_no_credentials(self) -> None:
        request = self._make_request({})
        u, p = extract_credentials(request)
        assert u is None
        assert p is None

    def test_invalid_basic_auth(self) -> None:
        request = self._make_request({
            "Authorization": "Basic !!!invalid!!!",
        })
        u, p = extract_credentials(request)
        assert u is None
        assert p is None

    def test_basic_auth_with_colon_in_password(self) -> None:
        encoded = base64.b64encode(b"user:pa:ss:word").decode()
        request = self._make_request({
            "Authorization": f"Basic {encoded}",
        })
        u, p = extract_credentials(request)
        assert u == "user"
        assert p == "pa:ss:word"


class TestDispatchMcpMethod:
    async def test_initialize(self) -> None:
        server = _mock_server()
        result = await _dispatch_mcp_method(server, "initialize", {})
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "serverInfo" in result

    async def test_ping(self) -> None:
        server = _mock_server()
        result = await _dispatch_mcp_method(server, "ping", {})
        assert result == {}

    async def test_unknown_method(self) -> None:
        server = _mock_server()
        with pytest.raises(ValueError, match="Method not found"):
            await _dispatch_mcp_method(server, "unknown/method", {})

    async def test_resources_list(self) -> None:
        server = _mock_server()
        mock_resource = MagicMock()
        mock_resource.uri = "loxone://test"
        mock_resource.name = "Test"
        mock_resource.description = "desc"
        mock_resource.mimeType = "application/json"

        with patch(
            "loxone_mcp.mcp.resources.get_resource_list",
            new_callable=AsyncMock,
            return_value=[mock_resource],
        ):
            result = await _dispatch_mcp_method(server, "resources/list", {})
            assert "resources" in result

    async def test_resources_read(self) -> None:
        server = _mock_server()
        with patch(
            "loxone_mcp.mcp.resources.handle_read_resource",
            new_callable=AsyncMock,
            return_value="content",
        ):
            result = await _dispatch_mcp_method(
                server, "resources/read", {"uri": "loxone://test"}
            )
            assert "contents" in result

    async def test_tools_list(self) -> None:
        server = _mock_server()
        mock_tool = MagicMock()
        mock_tool.name = "test"
        mock_tool.description = "desc"
        mock_tool.inputSchema = {}

        with patch(
            "loxone_mcp.mcp.tools.get_tool_list",
            new_callable=AsyncMock,
            return_value=[mock_tool],
        ):
            result = await _dispatch_mcp_method(server, "tools/list", {})
            assert "tools" in result

    async def test_tools_call(self) -> None:
        server = _mock_server()
        with patch(
            "loxone_mcp.mcp.tools.handle_call_tool",
            new_callable=AsyncMock,
            return_value="result",
        ):
            result = await _dispatch_mcp_method(
                server, "tools/call", {"name": "test_tool", "arguments": {}}
            )
            assert "content" in result


class TestResourceToDict:
    def test_basic(self) -> None:
        r = MagicMock()
        r.uri = "loxone://test"
        r.name = "Test"
        r.description = "A test"
        r.mimeType = "application/json"

        d = _resource_to_dict(r)
        assert d["uri"] == "loxone://test"
        assert d["name"] == "Test"
        assert d["description"] == "A test"
        assert d["mimeType"] == "application/json"

    def test_no_description(self) -> None:
        r = MagicMock()
        r.uri = "u"
        r.name = "n"
        r.description = None
        r.mimeType = None

        d = _resource_to_dict(r)
        assert "description" not in d
        assert "mimeType" not in d


class TestToolToDict:
    def test_basic(self) -> None:
        t = MagicMock()
        t.name = "tool"
        t.description = "desc"
        t.inputSchema = {"type": "object"}

        d = _tool_to_dict(t)
        assert d["name"] == "tool"
        assert d["description"] == "desc"
        assert d["inputSchema"] == {"type": "object"}

    def test_no_schema(self) -> None:
        t = MagicMock()
        t.name = "t"
        t.description = "d"
        t.inputSchema = None

        d = _tool_to_dict(t)
        assert "inputSchema" not in d


class TestBroadcastSseNotification:
    async def test_broadcast(self) -> None:
        app = web.Application()
        q1: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        q2: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        app[SSE_CLIENTS_KEY] = [q1, q2]

        notification = {"method": "test"}
        await broadcast_sse_notification(app, notification)

        assert not q1.empty()
        assert not q2.empty()
        assert q1.get_nowait() == notification
        assert q2.get_nowait() == notification

    async def test_full_queue_handled(self) -> None:
        app = web.Application()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        q.put_nowait({"old": True})
        app[SSE_CLIENTS_KEY] = [q]

        # Should not raise on full queue
        await broadcast_sse_notification(app, {"new": True})


class TestHandleCorsPreflightFunction:
    async def test_returns_204(self) -> None:
        request = MagicMock()
        response = await handle_cors_preflight(request)
        assert response.status == 204


class TestHandleMcpRequest:
    """Test the handle_mcp_request handler via aiohttp test client."""

    async def test_valid_request(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 1,
                },
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["result"]["serverInfo"]["name"] == "loxone-mcp"

    async def test_parse_error(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/mcp",
                data=b"not json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400

    async def test_method_not_found(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "nonexistent/method",
                    "id": 2,
                },
            )
            assert resp.status == 500

    async def test_ping(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "method": "ping", "id": 3},
            )
            assert resp.status == 200
            data = await resp.json()
            assert data["result"] == {}


class TestHandleHealth:
    async def test_health_endpoint(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert "websocket_connected" in data


class TestHandleMetrics:
    async def test_metrics_endpoint(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200


class TestCorsMiddleware:
    async def test_cors_headers_present(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/health")
            assert "Access-Control-Allow-Origin" in resp.headers

    async def test_options_preflight(self) -> None:
        from aiohttp.test_utils import TestClient, TestServer

        server = _mock_server()
        app = create_http_app(server)

        async with TestClient(TestServer(app)) as client:
            resp = await client.options("/mcp")
            assert resp.status == 204
