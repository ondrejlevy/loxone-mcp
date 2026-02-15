"""Unit tests for MCP notification sender (mcp/notifications.py).

Tests send_resource_updated and send_resource_list_changed functions.
Verifies routing to both Streamable HTTP and stdio transports.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from loxone_mcp.mcp.notifications import send_resource_list_changed, send_resource_updated


class TestSendResourceUpdated:
    async def test_broadcasts_via_streamable_http(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = None

        with patch(
            "loxone_mcp.transport.streamable_http.broadcast_notification",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await send_resource_updated(server, "loxone://components")
            mock_broadcast.assert_awaited_once_with(
                "notifications/resources/updated",
                {"uri": "loxone://components"},
            )

    async def test_without_transport(self) -> None:
        server = MagicMock(spec=[])  # no attributes
        # Should not raise
        await send_resource_updated(server, "loxone://components")

    async def test_routes_to_stdio(self) -> None:
        """Notifications should also be routed to stdio transport."""
        server = MagicMock()

        with patch(
            "loxone_mcp.transport.stdio.send_stdio_notification",
            new_callable=AsyncMock,
        ) as mock_stdio:
            await send_resource_updated(server, "loxone://components")
            mock_stdio.assert_awaited_once()
            call_args = mock_stdio.call_args
            assert call_args[0][0] is server
            notification = call_args[0][1]
            assert notification["method"] == "notifications/resources/updated"


class TestSendResourceListChanged:
    async def test_broadcasts_via_streamable_http(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = None

        with patch(
            "loxone_mcp.transport.streamable_http.broadcast_notification",
            new_callable=AsyncMock,
        ) as mock_broadcast:
            await send_resource_list_changed(server)
            mock_broadcast.assert_awaited_once_with(
                "notifications/resources/list_changed",
            )

    async def test_without_transport(self) -> None:
        server = MagicMock(spec=[])
        await send_resource_list_changed(server)

    async def test_routes_to_stdio(self) -> None:
        """List changed notifications should also be routed to stdio transport."""
        server = MagicMock()

        with patch(
            "loxone_mcp.transport.stdio.send_stdio_notification",
            new_callable=AsyncMock,
        ) as mock_stdio:
            await send_resource_list_changed(server)
            mock_stdio.assert_awaited_once()
            call_args = mock_stdio.call_args
            notification = call_args[0][1]
            assert notification["method"] == "notifications/resources/list_changed"
