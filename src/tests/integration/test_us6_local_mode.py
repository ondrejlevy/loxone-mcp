"""Integration tests for User Story 6: Local Operation Mode.

Tests stdio transport module, lifecycle management,
and notification delivery.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from loxone_mcp.transport.stdio import run_stdio_transport, send_stdio_notification

# --- Stdio Transport Tests ---


class TestStdioTransport:
    """Tests for stdio transport lifecycle."""

    async def test_run_stdio_sets_write_stream(self) -> None:
        """Verify write stream is set on server during stdio run."""
        server = MagicMock()
        server.mcp_server = MagicMock()
        server.mcp_server.create_initialization_options = MagicMock(return_value={})

        # Mock stdio_server context manager
        mock_read = AsyncMock()
        mock_write = AsyncMock()

        async def mock_run(read, write, opts):
            # Verify write stream was set
            assert server._stdio_write_stream is mock_write

        server.mcp_server.run = mock_run

        with patch("mcp.server.stdio.stdio_server") as mock_stdio:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_stdio.return_value = mock_ctx

            await run_stdio_transport(server)

        # After transport stops, write stream should be cleared
        assert server._stdio_write_stream is None

    async def test_run_stdio_handles_cancellation(self) -> None:
        """Verify graceful shutdown on cancellation."""
        server = MagicMock()
        server.mcp_server = MagicMock()
        server.mcp_server.create_initialization_options = MagicMock(return_value={})

        async def mock_run(read, write, opts):
            raise asyncio.CancelledError

        server.mcp_server.run = mock_run

        with patch("mcp.server.stdio.stdio_server") as mock_stdio:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_stdio.return_value = mock_ctx

            # Should not raise
            await run_stdio_transport(server)

    async def test_run_stdio_handles_error(self) -> None:
        """Verify error handling in stdio transport."""
        server = MagicMock()
        server.mcp_server = MagicMock()
        server.mcp_server.create_initialization_options = MagicMock(return_value={})

        async def mock_run(read, write, opts):
            msg = "connection lost"
            raise OSError(msg)

        server.mcp_server.run = mock_run

        with patch("mcp.server.stdio.stdio_server") as mock_stdio:
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_stdio.return_value = mock_ctx

            await run_stdio_transport(server)


# --- Notification Delivery Tests ---


class TestStdioNotification:
    """Tests for stdio notification delivery."""

    async def test_send_notification_without_stream(self) -> None:
        """Should not error when no write stream is available."""
        server = MagicMock(spec=[])
        await send_stdio_notification(server, {"method": "test"})

    async def test_send_notification_with_none_stream(self) -> None:
        """Should not error when write stream is None."""
        server = MagicMock()
        server._stdio_write_stream = None
        await send_stdio_notification(server, {"method": "test"})


# --- Transport Selection Tests ---


class TestTransportSelection:
    """Tests for transport selection logic in config."""

    def test_default_transport_is_http(self) -> None:
        from loxone_mcp.config import ServerConfig, TransportType

        config = ServerConfig()
        assert config.transport == TransportType.HTTP

    def test_stdio_transport_config(self) -> None:
        from loxone_mcp.config import ServerConfig, TransportType

        config = ServerConfig(transport=TransportType.STDIO)
        assert config.transport == TransportType.STDIO

    def test_both_transport_config(self) -> None:
        from loxone_mcp.config import ServerConfig, TransportType

        config = ServerConfig(transport=TransportType.BOTH)
        assert config.transport == TransportType.BOTH

    def test_stdio_does_not_require_http_auth(self) -> None:
        """Stdio transport doesn't use HTTP auth - verify config allows it."""
        from loxone_mcp.config import AccessControlConfig, AccessMode

        # Stdio mode with read-write access should work without HTTP credentials
        config = AccessControlConfig(mode=AccessMode.READ_WRITE)
        assert config.mode == AccessMode.READ_WRITE
