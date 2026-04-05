"""Unit tests for stdio transport (transport/stdio.py).

Tests notification sending and transport lifecycle.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.shared.message import SessionMessage

from loxone_mcp.transport.stdio import run_stdio_transport, send_stdio_notification

if TYPE_CHECKING:
    from mcp.types import JSONRPCNotification


class TestSendStdioNotification:
    async def test_no_write_stream(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = None
        # Should return silently
        await send_stdio_notification(server, {"method": "test"})

    async def test_missing_attribute(self) -> None:
        server = MagicMock(spec=[])  # no _stdio_write_stream
        await send_stdio_notification(server, {"method": "test"})

    async def test_with_write_stream_sends_session_message(self) -> None:
        """Test that notifications are properly sent as SessionMessage via write_stream."""
        server = MagicMock()
        mock_stream = AsyncMock()
        server._stdio_write_stream = mock_stream

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {"uri": "loxone://components"},
        }
        await send_stdio_notification(server, notification)

        # Should actually send via write_stream
        mock_stream.send.assert_awaited_once()
        sent_msg = mock_stream.send.call_args[0][0]
        # Verify it's a proper SessionMessage
        assert isinstance(sent_msg, SessionMessage)
        # Verify the notification method is correct
        root_message = cast("JSONRPCNotification", sent_msg.message.root)
        assert root_message.method == "notifications/resources/updated"

    async def test_send_error_handled(self) -> None:
        """Test that send errors are caught and logged."""
        server = MagicMock()
        mock_stream = AsyncMock()
        mock_stream.send.side_effect = RuntimeError("broken pipe")
        server._stdio_write_stream = mock_stream

        notification: dict[str, Any] = {
            "method": "notifications/resources/updated",
            "params": {"uri": "loxone://test"},
        }
        # Should not raise
        await send_stdio_notification(server, notification)


class TestRunStdioTransport:
    @patch("mcp.server.stdio.stdio_server")
    async def test_normal_run(self, mock_stdio_server: MagicMock) -> None:
        """Test the happy path: stdio_server context yields streams and run completes."""
        read_stream = MagicMock()
        write_stream = MagicMock()

        # Create async context manager mock
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=(read_stream, write_stream))
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio_server.return_value = cm

        server = MagicMock()
        server.mcp_server = MagicMock()
        server.mcp_server.create_initialization_options = MagicMock(return_value={})
        server.mcp_server.run = AsyncMock()

        await run_stdio_transport(server)

        server.mcp_server.run.assert_awaited_once_with(read_stream, write_stream, {})
        # write stream should be set during transport and cleared after
        assert server._stdio_write_stream is None

    @patch("mcp.server.stdio.stdio_server")
    async def test_cancelled_error(self, mock_stdio_server: MagicMock) -> None:
        """Test that CancelledError is handled gracefully."""
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=asyncio.CancelledError())
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio_server.return_value = cm

        server = MagicMock()
        server._stdio_write_stream = None

        await run_stdio_transport(server)
        assert server._stdio_write_stream is None

    @patch("mcp.server.stdio.stdio_server")
    async def test_exception_handled(self, mock_stdio_server: MagicMock) -> None:
        """Test that general exceptions are caught and logged."""
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=RuntimeError("broken"))
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_stdio_server.return_value = cm

        server = MagicMock()
        server._stdio_write_stream = None

        # Should not raise
        await run_stdio_transport(server)
        assert server._stdio_write_stream is None
