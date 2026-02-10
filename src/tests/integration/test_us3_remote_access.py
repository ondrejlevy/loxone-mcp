"""Integration tests for User Story 3: Secure Remote Access.

Tests HTTP transport, SSE streaming, authentication success/failure,
and credential passthrough.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

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
from loxone_mcp.transport.http_sse import (
    SSE_CLIENTS_KEY,
    broadcast_sse_notification,
    create_http_app,
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
    return server


# --- Credential Extraction Tests (T024b) ---


class TestCredentialExtraction:
    """Tests for HTTP header authentication extraction."""

    def test_custom_headers(self) -> None:
        request = MagicMock()
        request.headers = {
            "X-Loxone-Username": "admin",
            "X-Loxone-Password": "secret123",
        }
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "secret123"

    def test_basic_auth_header(self) -> None:
        request = MagicMock()
        credentials = base64.b64encode(b"admin:secret123").decode("utf-8")
        request.headers = {
            "Authorization": f"Basic {credentials}",
        }
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "secret123"

    def test_basic_auth_with_colon_in_password(self) -> None:
        request = MagicMock()
        credentials = base64.b64encode(b"admin:pass:word:123").decode("utf-8")
        request.headers = {
            "Authorization": f"Basic {credentials}",
        }
        username, password = extract_credentials(request)
        assert username == "admin"
        assert password == "pass:word:123"

    def test_no_credentials(self) -> None:
        request = MagicMock()
        request.headers = {}
        username, password = extract_credentials(request)
        assert username is None
        assert password is None

    def test_invalid_basic_auth(self) -> None:
        request = MagicMock()
        request.headers = {"Authorization": "Basic invalid-base64!!!"}
        username, password = extract_credentials(request)
        assert username is None
        assert password is None

    def test_custom_headers_take_priority(self) -> None:
        request = MagicMock()
        credentials = base64.b64encode(b"basic_user:basic_pass").decode("utf-8")
        request.headers = {
            "X-Loxone-Username": "custom_user",
            "X-Loxone-Password": "custom_pass",
            "Authorization": f"Basic {credentials}",
        }
        username, password = extract_credentials(request)
        assert username == "custom_user"
        assert password == "custom_pass"


# --- HTTP Transport Tests ---


class TestHTTPTransport:
    """Tests for HTTP endpoint handling."""

    @pytest.fixture
    def app(self) -> web.Application:
        server = make_mock_server()
        return create_http_app(server)

    async def test_health_endpoint(self, aiohttp_client: Any, app: web.Application) -> None:
        client = await aiohttp_client(app)
        response = await client.get("/health")
        assert response.status == 200
        data = await response.json()
        assert data["status"] == "ok"
        assert "websocket_connected" in data

    async def test_mcp_post_invalid_json(
        self, aiohttp_client: Any, app: web.Application
    ) -> None:
        client = await aiohttp_client(app)
        response = await client.post(
            "/mcp", data="not-json", headers={"Content-Type": "application/json"}
        )
        assert response.status == 400
        data = await response.json()
        assert data["error"]["code"] == -32700

    async def test_mcp_ping(self, aiohttp_client: Any, app: web.Application) -> None:
        client = await aiohttp_client(app)
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1},
        )
        assert response.status == 200
        data = await response.json()
        assert data["id"] == 1

    async def test_mcp_initialize(self, aiohttp_client: Any, app: web.Application) -> None:
        client = await aiohttp_client(app)
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "initialize", "id": 1},
        )
        assert response.status == 200
        data = await response.json()
        assert data["result"]["serverInfo"]["name"] == "loxone-mcp"
        assert "resources" in data["result"]["capabilities"]

    async def test_cors_preflight(self, aiohttp_client: Any, app: web.Application) -> None:
        client = await aiohttp_client(app)
        response = await client.options("/mcp")
        assert response.status == 204

    async def test_mcp_unknown_method(
        self, aiohttp_client: Any, app: web.Application
    ) -> None:
        client = await aiohttp_client(app)
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "nonexistent/method", "id": 99},
        )
        assert response.status == 500
        data = await response.json()
        assert data["error"]["code"] == -32603


# --- SSE Tests ---


class TestSSEBroadcast:
    """Tests for SSE notification broadcasting."""

    async def test_broadcast_to_empty_clients(self) -> None:
        app = web.Application()
        app[SSE_CLIENTS_KEY] = []
        await broadcast_sse_notification(app, {"method": "test"})
        # Should not raise

    async def test_broadcast_queues_notification(self) -> None:
        app = web.Application()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        app[SSE_CLIENTS_KEY] = [queue]
        await broadcast_sse_notification(app, {"method": "notifications/resources/updated"})
        assert not queue.empty()
        notification = await queue.get()
        assert notification["method"] == "notifications/resources/updated"

    async def test_broadcast_to_multiple_clients(self) -> None:
        app = web.Application()
        q1: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        q2: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        app[SSE_CLIENTS_KEY] = [q1, q2]
        await broadcast_sse_notification(app, {"method": "test_multi"})
        assert (await q1.get())["method"] == "test_multi"
        assert (await q2.get())["method"] == "test_multi"

    async def test_broadcast_full_queue_does_not_raise(self) -> None:
        app = web.Application()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        queue.put_nowait({"method": "existing"})  # fill the queue
        app[SSE_CLIENTS_KEY] = [queue]
        # Should not raise even though queue is full
        await broadcast_sse_notification(app, {"method": "dropped"})
