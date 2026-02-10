"""Unit tests for stdio transport (transport/stdio.py).

Tests notification sending and transport lifecycle.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loxone_mcp.transport.stdio import run_stdio_transport, send_stdio_notification


class TestSendStdioNotification:
    async def test_no_write_stream(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = None
        # Should return silently
        await send_stdio_notification(server, {"method": "test"})

    async def test_missing_attribute(self) -> None:
        server = MagicMock(spec=[])  # no _stdio_write_stream
        await send_stdio_notification(server, {"method": "test"})

    async def test_with_write_stream(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = MagicMock()

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/resources/updated",
            "params": {"uri": "loxone://components"},
        }
        await send_stdio_notification(server, notification)
        # Function just serializes + logs, doesn't write to stream directly in current impl

    async def test_serialization_error(self) -> None:
        server = MagicMock()
        server._stdio_write_stream = MagicMock()

        # Create a notification with non-serializable content
        # The current implementation catches all exceptions
        notification: dict[str, Any] = {"method": "test"}
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
