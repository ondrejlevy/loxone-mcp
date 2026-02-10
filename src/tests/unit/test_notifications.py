"""Unit tests for MCP notification sender (mcp/notifications.py).

Tests send_resource_updated and send_resource_list_changed functions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from loxone_mcp.mcp.notifications import send_resource_list_changed, send_resource_updated


class TestSendResourceUpdated:
    async def test_with_http_app(self) -> None:
        server = MagicMock()
        server._http_app = MagicMock()

        with patch(
            "loxone_mcp.transport.http_sse.broadcast_sse_notification",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await send_resource_updated(server, "loxone://components")
            mock_broadcast.assert_awaited_once()
            call_args = mock_broadcast.call_args
            notification = call_args[0][1]
            assert notification["method"] == "notifications/resources/updated"
            assert notification["params"]["uri"] == "loxone://components"

    async def test_without_http_app(self) -> None:
        server = MagicMock(spec=[])  # no _http_app attribute
        # Should not raise
        await send_resource_updated(server, "loxone://components")


class TestSendResourceListChanged:
    async def test_with_http_app(self) -> None:
        server = MagicMock()
        server._http_app = MagicMock()

        with patch(
            "loxone_mcp.transport.http_sse.broadcast_sse_notification",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await send_resource_list_changed(server)
            mock_broadcast.assert_awaited_once()
            call_args = mock_broadcast.call_args
            notification = call_args[0][1]
            assert notification["method"] == "notifications/resources/list_changed"

    async def test_without_http_app(self) -> None:
        server = MagicMock(spec=[])
        await send_resource_list_changed(server)
