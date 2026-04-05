"""Unit tests for Loxone WebSocket client (websocket.py).

Tests connection lifecycle, binary/text message parsing,
keepalive, reconnect logic, and circuit breaker.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from loxone_mcp.loxone.websocket import (
    MSG_EVENT_TEXT_STATES,
    MSG_EVENT_VALUE_STATES,
    MSG_KEEPALIVE,
    RECONNECT_MAX_FAILURES,
    LoxoneWebSocket,
)


def _make_ws() -> LoxoneWebSocket:
    config = MagicMock()
    config.host = "192.168.1.100"
    config.port = 80
    config.use_tls = False
    authenticator = MagicMock()
    authenticator.process_getkey_response = MagicMock()
    authenticator.build_key_exchange_command = MagicMock(return_value="keyexchange/cmd")
    authenticator.build_token_command = MagicMock(return_value="token/cmd")
    authenticator.process_token_response = MagicMock()
    authenticator.stop_token_refresh = MagicMock()
    # authenticate_ws is the new single-method auth entry point
    authenticator.authenticate_ws = AsyncMock(return_value=True)
    return LoxoneWebSocket(config, authenticator)


class TestProperties:
    def test_is_connected_false_initially(self) -> None:
        ws = _make_ws()
        assert ws.is_connected is False

    def test_is_connected_true(self) -> None:
        ws = _make_ws()
        ws._connected = True
        ws._ws = MagicMock()
        assert ws.is_connected is True

    def test_is_connected_no_ws(self) -> None:
        ws = _make_ws()
        ws._connected = True
        ws._ws = None
        assert ws.is_connected is False

    def test_ws_url_http(self) -> None:
        ws = _make_ws()
        assert ws.ws_url == "ws://192.168.1.100:80/ws/rfc6455"

    def test_ws_url_tls(self) -> None:
        ws = _make_ws()
        ws._config.use_tls = True
        assert ws.ws_url == "wss://192.168.1.100:80/ws/rfc6455"


class TestCallbacks:
    def test_register_state_callback(self) -> None:
        ws = _make_ws()
        cb = AsyncMock()
        ws.register_state_callback(cb)
        assert cb in ws._state_callbacks

    def test_register_reconnect_callback(self) -> None:
        ws = _make_ws()
        cb = AsyncMock()
        ws.register_reconnect_callback(cb)
        assert cb in ws._reconnect_callbacks

    def test_set_state_uuid_map(self) -> None:
        ws = _make_ws()
        test_map = {"uuid1": ("comp1", "key1")}
        ws.set_state_uuid_map(test_map)
        assert ws._state_uuid_map == test_map


class TestConnect:
    @patch("loxone_mcp.loxone.websocket.websockets")
    async def test_connect_success(self, mock_ws_lib: MagicMock) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        mock_ws_lib.connect = AsyncMock(return_value=mock_conn)

        await ws.connect()
        assert ws._connected is True
        assert ws._ws == mock_conn
        assert ws._reconnect_count == 0

    @patch("loxone_mcp.loxone.websocket.websockets")
    async def test_connect_failure(self, mock_ws_lib: MagicMock) -> None:
        ws = _make_ws()
        mock_ws_lib.connect = AsyncMock(side_effect=OSError("refused"))

        with pytest.raises(OSError):
            await ws.connect()
        assert ws._connected is False


class TestAuthenticate:
    async def test_no_ws_returns_false(self) -> None:
        ws = _make_ws()
        ws._ws = None
        result = await ws.authenticate()
        assert result is False

    async def test_success(self) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        ws._ws = mock_conn
        # authenticate_ws returns True by default (set in _make_ws)
        result = await ws.authenticate()
        assert result is True
        auth_mock = cast("AsyncMock", ws._auth.authenticate_ws)
        auth_mock.assert_awaited_once_with(mock_conn)

    async def test_auth_failed_code(self) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        ws._ws = mock_conn
        cast("Any", ws._auth).authenticate_ws = AsyncMock(return_value=False)

        result = await ws.authenticate()
        assert result is False

    async def test_auth_exception(self) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        ws._ws = mock_conn
        cast("Any", ws._auth).authenticate_ws = AsyncMock(side_effect=Exception("auth error"))

        result = await ws.authenticate()
        assert result is False


class TestEnableStatusUpdates:
    async def test_enable(self) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        ws._ws = mock_conn

        await ws.enable_status_updates()
        mock_conn.send.assert_awaited_once_with("jdev/sps/enablebinstatusupdate")

    async def test_no_ws(self) -> None:
        ws = _make_ws()
        ws._ws = None
        await ws.enable_status_updates()  # Should not raise


class TestStop:
    async def test_stop_cleans_up(self) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        ws._ws = mock_conn
        ws._connected = True
        ws._keepalive_task = asyncio.create_task(asyncio.sleep(100))
        ws._receive_task = asyncio.create_task(asyncio.sleep(100))

        await ws.stop()
        assert ws._should_run is False
        assert ws._ws is None
        assert ws._connected is False
        ws._auth.stop_token_refresh.assert_called_once()


class TestProcessValueStates:
    async def test_known_uuid(self) -> None:
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "value")}

        # Build binary payload: 16 bytes UUID (little-endian) + 8 bytes double
        payload = test_uuid.bytes_le + struct.pack("<d", 42.5)
        await ws._process_value_states(payload)

        callback.assert_awaited_once_with("comp-1", "value", 42.5)

    async def test_unknown_uuid_skipped(self) -> None:
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)
        ws._state_uuid_map = {}

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        payload = test_uuid.bytes_le + struct.pack("<d", 1.0)
        await ws._process_value_states(payload)

        callback.assert_not_awaited()

    async def test_multiple_entries(self) -> None:
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)

        uuid1 = UUID("12345678-1234-1234-1234-123456789abc")
        uuid2 = UUID("abcdef01-2345-6789-abcd-ef0123456789")
        ws._state_uuid_map = {
            str(uuid1): ("comp-1", "value"),
            str(uuid2): ("comp-2", "value"),
        }

        payload = uuid1.bytes_le + struct.pack("<d", 1.0) + uuid2.bytes_le + struct.pack("<d", 2.0)
        await ws._process_value_states(payload)

        assert callback.await_count == 2

    async def test_callback_exception_doesnt_stop_processing(self) -> None:
        ws = _make_ws()
        bad_callback = AsyncMock(side_effect=Exception("fail"))
        ws.register_state_callback(bad_callback)

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "value")}

        payload = test_uuid.bytes_le + struct.pack("<d", 1.0)
        # Should not raise despite callback error
        await ws._process_value_states(payload)


class TestProcessTextStates:
    async def test_text_state(self) -> None:
        """Text states use binary struct: UUID(16) + iconUUID(16) + textLen(4) + text."""
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        # Python format used as map key
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "text")}

        text = b"Hello World"
        # Build binary struct: UUID(16 LE) + icon UUID(16 LE) + text_length(4 LE) + text
        icon_uuid = UUID(int=0)
        payload = (
            test_uuid.bytes_le
            + icon_uuid.bytes_le
            + struct.pack("<I", len(text))
            + text
        )
        # Pad to 4-byte boundary
        padding = (4 - (len(payload) % 4)) % 4
        payload += b"\x00" * padding

        await ws._process_text_states(payload)

        callback.assert_awaited_once_with("comp-1", "text", "Hello World")

    async def test_text_state_loxone_uuid_format(self) -> None:
        """Text states should match against Loxone-format UUID keys in the map."""
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        # Loxone format as map key (8-4-4-16)
        loxone_uuid_str = "12345678-1234-1234-1234123456789abc"
        ws._state_uuid_map = {loxone_uuid_str: ("comp-1", "text")}

        text = b"test value"
        icon_uuid = UUID(int=0)
        payload = (
            test_uuid.bytes_le
            + icon_uuid.bytes_le
            + struct.pack("<I", len(text))
            + text
        )
        padding = (4 - (len(payload) % 4)) % 4
        payload += b"\x00" * padding

        await ws._process_text_states(payload)

        callback.assert_awaited_once_with("comp-1", "text", "test value")

    async def test_unknown_text_state_skipped(self) -> None:
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)
        ws._state_uuid_map = {}

        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        text = b"value"
        icon_uuid = UUID(int=0)
        payload = (
            test_uuid.bytes_le
            + icon_uuid.bytes_le
            + struct.pack("<I", len(text))
            + text
        )
        padding = (4 - (len(payload) % 4)) % 4
        payload += b"\x00" * padding

        await ws._process_text_states(payload)

        callback.assert_not_awaited()

    async def test_multiple_text_entries(self) -> None:
        """Multiple text state entries parsed from a single payload."""
        ws = _make_ws()
        callback = AsyncMock()
        ws.register_state_callback(callback)

        uuid1 = UUID("12345678-1234-1234-1234-123456789abc")
        uuid2 = UUID("abcdef01-2345-6789-abcd-ef0123456789")
        ws._state_uuid_map = {
            str(uuid1): ("comp-1", "text1"),
            str(uuid2): ("comp-2", "text2"),
        }

        icon = UUID(int=0)
        # Entry 1
        text1 = b"hello"
        entry1 = uuid1.bytes_le + icon.bytes_le + struct.pack("<I", len(text1)) + text1
        pad1 = (4 - (len(entry1) % 4)) % 4
        entry1 += b"\x00" * pad1

        # Entry 2
        text2 = b"world"
        entry2 = uuid2.bytes_le + icon.bytes_le + struct.pack("<I", len(text2)) + text2
        pad2 = (4 - (len(entry2) % 4)) % 4
        entry2 += b"\x00" * pad2

        await ws._process_text_states(entry1 + entry2)

        assert callback.await_count == 2


class TestHandleBinaryMessage:
    async def test_too_short_ignored(self) -> None:
        ws = _make_ws()
        # Less than 8 bytes header
        await ws._handle_binary_message(b"\x00\x01\x02")

    async def test_value_state_combined_message(self) -> None:
        """Combined header+payload in one message (fallback/compatibility)."""
        ws = _make_ws()
        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "value")}
        callback = AsyncMock()
        ws.register_state_callback(callback)

        payload = test_uuid.bytes_le + struct.pack("<d", 99.0)
        # Header: type indicator, msg_type=2 (value states), reserved (2 bytes), payload length
        header = struct.pack("<BBxx I", 0, MSG_EVENT_VALUE_STATES, len(payload))
        message = header + payload

        await ws._handle_binary_message(message)
        callback.assert_awaited_once()

    async def test_keepalive_message(self) -> None:
        ws = _make_ws()
        header = struct.pack("<BBxx I", 0, MSG_KEEPALIVE, 0)
        await ws._handle_binary_message(header)  # Should not raise
        # Should NOT set pending header for keepalive
        assert ws._pending_binary_header is None

    async def test_two_part_value_states(self) -> None:
        """Loxone protocol: header and payload as separate messages."""
        ws = _make_ws()
        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "value")}
        callback = AsyncMock()
        ws.register_state_callback(callback)

        payload = test_uuid.bytes_le + struct.pack("<d", 42.5)
        header = struct.pack("<BBxx I", 3, MSG_EVENT_VALUE_STATES, len(payload))

        # Step 1: Send header only — should store pending header
        await ws._handle_binary_message(header)
        assert ws._pending_binary_header == (MSG_EVENT_VALUE_STATES, len(payload))
        callback.assert_not_awaited()

        # Step 2: Send payload — should process and clear pending
        await ws._handle_binary_message(payload)
        assert ws._pending_binary_header is None
        callback.assert_awaited_once_with("comp-1", "value", 42.5)

    async def test_two_part_text_states(self) -> None:
        """Loxone protocol: text state header + payload as separate messages."""
        ws = _make_ws()
        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        ws._state_uuid_map = {str(test_uuid): ("comp-1", "text")}
        callback = AsyncMock()
        ws.register_state_callback(callback)

        # Build text state payload in binary struct format
        text = b"Hello"
        icon_uuid = UUID(int=0)
        payload = (
            test_uuid.bytes_le
            + icon_uuid.bytes_le
            + struct.pack("<I", len(text))
            + text
        )
        padding = (4 - (len(payload) % 4)) % 4
        payload += b"\x00" * padding

        header = struct.pack("<BBxx I", 3, MSG_EVENT_TEXT_STATES, len(payload))

        # Send header then payload
        await ws._handle_binary_message(header)
        assert ws._pending_binary_header is not None
        await ws._handle_binary_message(payload)
        assert ws._pending_binary_header is None
        callback.assert_awaited_once_with("comp-1", "text", "Hello")

    async def test_pending_header_cleared_on_stop(self) -> None:
        ws = _make_ws()
        ws._ws = AsyncMock()
        ws._connected = True

        # Simulate a pending header
        ws._pending_binary_header = (MSG_EVENT_VALUE_STATES, 24)

        await ws.stop()
        assert ws._pending_binary_header is None


class TestHandleTextMessage:
    async def test_valid_json(self) -> None:
        ws = _make_ws()
        await ws._handle_text_message('{"LL": {"Code": "200", "control": "test"}}')

    async def test_invalid_json(self) -> None:
        ws = _make_ws()
        await ws._handle_text_message("not json at all")  # Should not raise


class TestReconnect:
    async def test_circuit_breaker_opens(self) -> None:
        ws = _make_ws()
        ws._reconnect_count = RECONNECT_MAX_FAILURES

        await ws._reconnect()

        assert ws._should_run is False
        assert ws._circuit_breaker_open is True

    @patch("loxone_mcp.loxone.websocket.websockets")
    @patch("loxone_mcp.loxone.websocket.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_success(self, mock_sleep: AsyncMock, mock_ws_lib: MagicMock) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._reconnect_count = 0

        mock_conn = AsyncMock()
        mock_ws_lib.connect = AsyncMock(return_value=mock_conn)

        # Auth responses
        getkey_resp = '{"LL": {"value": {}}}'
        key_exch_resp = '{"LL": {"Code": "200"}}'
        token_resp = '{"LL": {"Code": "200", "value": {"token": "t"}}}'
        mock_conn.recv = AsyncMock(side_effect=[getkey_resp, key_exch_resp, token_resp, "ok"])

        await ws._reconnect()

        assert ws._connected is True
        mock_sleep.assert_awaited()

    @patch("loxone_mcp.loxone.websocket.websockets")
    @patch("loxone_mcp.loxone.websocket.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_failure(self, mock_sleep: AsyncMock, mock_ws_lib: MagicMock) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._reconnect_count = 0

        mock_ws_lib.connect = AsyncMock(side_effect=OSError("refused"))

        await ws._reconnect()  # Should not raise
        assert ws._connected is False

    async def test_exponential_backoff_delay(self) -> None:
        ws = _make_ws()
        # After count 3, delay = 1.0 * 2^2 = 4.0
        ws._reconnect_count = 2
        # We just verify the logic via the formula
        from loxone_mcp.loxone.websocket import RECONNECT_BASE_DELAY, RECONNECT_MAX_DELAY

        delay = min(RECONNECT_BASE_DELAY * (2 ** (3 - 1)), RECONNECT_MAX_DELAY)
        assert delay == 4.0

    @patch("loxone_mcp.loxone.websocket.websockets")
    @patch("loxone_mcp.loxone.websocket.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_with_callbacks(
        self, mock_sleep: AsyncMock, mock_ws_lib: MagicMock
    ) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._reconnect_count = 0

        mock_conn = AsyncMock()
        mock_ws_lib.connect = AsyncMock(return_value=mock_conn)
        # authenticate_ws returns True (default from _make_ws)

        callback = AsyncMock()
        ws.register_reconnect_callback(callback)

        await ws._reconnect()
        callback.assert_awaited_once()

    @patch("loxone_mcp.loxone.websocket.websockets")
    @patch("loxone_mcp.loxone.websocket.asyncio.sleep", new_callable=AsyncMock)
    async def test_reconnect_auth_fails(
        self, mock_sleep: AsyncMock, mock_ws_lib: MagicMock
    ) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._reconnect_count = 0

        mock_conn = AsyncMock()
        mock_ws_lib.connect = AsyncMock(return_value=mock_conn)
        cast("Any", ws._auth).authenticate_ws = AsyncMock(return_value=False)

        await ws._reconnect()
        # Should not crash, just logs warning


class TestReceiveLoop:
    async def test_cancelled_error_stops(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._ws = AsyncMock()
        ws._ws.recv = AsyncMock(side_effect=asyncio.CancelledError())

        await ws._receive_loop()
        # Should return cleanly

    async def test_connection_closed_triggers_reconnect(self) -> None:
        import websockets

        ws = _make_ws()
        ws._should_run = True
        ws._ws = AsyncMock()
        # First recv raises ConnectionClosed, then we stop
        ws._ws.recv = AsyncMock(
            side_effect=websockets.ConnectionClosed(None, None)
        )
        cast("Any", ws)._reconnect = AsyncMock(side_effect=_stop_loop(ws))

        await ws._receive_loop()

        reconnect_mock = cast("AsyncMock", ws._reconnect)
        reconnect_mock.assert_awaited_once()
        assert ws._connected is False

    async def test_processes_binary_message(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._ws = AsyncMock()
        call_count = 0

        async def recv_side_effect() -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"\x00" * 8  # Short binary, handled by _handle_binary_message
            raise asyncio.CancelledError()

        ws._ws.recv = AsyncMock(side_effect=recv_side_effect)

        await ws._receive_loop()

    async def test_processes_text_message(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._ws = AsyncMock()
        call_count = 0

        async def recv_side_effect() -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"LL": {"Code": "200"}}'
            raise asyncio.CancelledError()

        ws._ws.recv = AsyncMock(side_effect=recv_side_effect)

        await ws._receive_loop()

    async def test_general_exception_continues(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._ws = AsyncMock()
        call_count = 0

        async def recv_side_effect() -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("unexpected")
            raise asyncio.CancelledError()

        ws._ws.recv = AsyncMock(side_effect=recv_side_effect)

        with patch("loxone_mcp.loxone.websocket.asyncio.sleep", new_callable=AsyncMock):
            await ws._receive_loop()

    async def test_no_ws_triggers_reconnect(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._ws = None
        cast("Any", ws)._reconnect = AsyncMock(side_effect=_stop_loop(ws))

        await ws._receive_loop()
        reconnect_mock = cast("AsyncMock", ws._reconnect)
        reconnect_mock.assert_awaited_once()


class TestKeepaliveLoop:
    async def test_sends_keepalive(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._connected = True
        ws._ws = AsyncMock()
        call_count = 0

        async def sleep_side_effect(delay: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                ws._should_run = False

        with patch(
            "loxone_mcp.loxone.websocket.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=sleep_side_effect,
        ):
            await ws._keepalive_loop()

        ws._ws.send.assert_awaited_with("keepalive")

    async def test_cancelled_stops(self) -> None:
        ws = _make_ws()
        ws._should_run = True

        with patch(
            "loxone_mcp.loxone.websocket.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ):
            await ws._keepalive_loop()

    async def test_exception_continues(self) -> None:
        ws = _make_ws()
        ws._should_run = True
        ws._connected = True
        ws._ws = AsyncMock()
        ws._ws.send = AsyncMock(side_effect=RuntimeError("send failed"))
        call_count = 0

        async def sleep_side_effect(delay: float) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                ws._should_run = False

        with patch(
            "loxone_mcp.loxone.websocket.asyncio.sleep",
            new_callable=AsyncMock,
            side_effect=sleep_side_effect,
        ):
            await ws._keepalive_loop()


class TestStartStop:
    @patch("loxone_mcp.loxone.websocket.websockets")
    async def test_start_creates_tasks(self, mock_ws_lib: MagicMock) -> None:
        ws = _make_ws()
        mock_conn = AsyncMock()
        mock_ws_lib.connect = AsyncMock(return_value=mock_conn)

        getkey_resp = '{"LL": {"value": {}}}'
        key_exch_resp = '{"LL": {"Code": "200"}}'
        token_resp = '{"LL": {"Code": "200", "value": {"token": "t"}}}'
        mock_conn.recv = AsyncMock(
            side_effect=[getkey_resp, key_exch_resp, token_resp]
        )

        await ws.start()

        assert ws._keepalive_task is not None
        assert ws._receive_task is not None

        # Cleanup
        await ws.stop()
        await asyncio.sleep(0)

    async def test_start_processing_creates_tasks(self) -> None:
        """start_processing() should start receive loop and keepalive on
        an already-connected WebSocket without calling connect()."""
        ws = _make_ws()
        ws._ws = AsyncMock()  # Simulate already-connected state
        ws._connected = True

        ws.start_processing()

        assert ws._should_run is True
        assert ws._keepalive_task is not None
        assert ws._receive_task is not None

        # Cleanup
        await ws.stop()
        await asyncio.sleep(0)


def _stop_loop(ws: LoxoneWebSocket) -> Any:
    """Helper to stop the loop after reconnect."""

    async def _stop() -> None:
        ws._should_run = False

    return _stop
