"""Loxone WebSocket client for real-time state updates.

Handles connection, binary state update parsing, keepalive,
and automatic reconnection with exponential backoff.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import struct
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
import websockets

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

    from loxone_mcp.config import LoxoneConfig
    from loxone_mcp.loxone.auth import LoxoneAuthenticator

logger = structlog.get_logger()

# Binary message types
MSG_TEXT_EVENT = 0
MSG_BINARY_FILE = 1
MSG_EVENT_VALUE_STATES = 2
MSG_EVENT_TEXT_STATES = 3
MSG_EVENT_DAYTIMER_STATES = 4
MSG_EVENT_WEATHER_STATES = 5
MSG_KEEPALIVE = 6
MSG_EVENT_VALUE_STATES_2 = 7

# Reconnection settings
RECONNECT_BASE_DELAY = 1.0
RECONNECT_MAX_DELAY = 60.0
RECONNECT_MAX_FAILURES = 10

# WebSocket header size (bytes)
BINARY_HEADER_SIZE = 8
# First byte of every valid Loxone binary header
BINARY_HEADER_MARKER = 0x03

# Keepalive interval
KEEPALIVE_INTERVAL = 240  # 4 minutes

# Callback type for state updates
StateUpdateCallback = Callable[[str, str, Any], Coroutine[Any, Any, None]]
# Callback type for reconnect events
ReconnectCallback = Callable[[], Coroutine[Any, Any, None]]


class LoxoneWebSocket:
    """WebSocket client for Loxone miniserver real-time updates.

    Connects to the miniserver, authenticates, enables binary status
    updates, and processes incoming state changes.
    """

    def __init__(
        self,
        config: LoxoneConfig,
        authenticator: LoxoneAuthenticator,
    ) -> None:
        self._config = config
        self._auth = authenticator
        self._ws: ClientConnection | None = None
        self._connected = False
        self._state_callbacks: list[StateUpdateCallback] = []
        self._reconnect_callbacks: list[ReconnectCallback] = []
        self._reconnect_count = 0
        self._keepalive_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._should_run = False
        # Maps state UUID path -> (component_uuid, state_key)
        self._state_uuid_map: dict[str, tuple[str, str]] = {}
        self._circuit_breaker_open = False
        # Loxone sends binary messages as two separate WebSocket frames:
        # first an 8-byte header, then the payload. We store the parsed
        # header here while waiting for the payload frame.
        self._pending_binary_header: tuple[int, int] | None = None  # (msg_type, payload_len)

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self._ws is not None

    def register_state_callback(self, callback: StateUpdateCallback) -> None:
        """Register a callback for state updates."""
        self._state_callbacks.append(callback)

    def register_reconnect_callback(self, callback: ReconnectCallback) -> None:
        """Register a callback for reconnect events."""
        self._reconnect_callbacks.append(callback)

    def set_state_uuid_map(self, state_map: dict[str, tuple[str, str]]) -> None:
        """Set the mapping from state UUID paths to component UUIDs and state keys.

        This is built from the structure file's component state definitions.
        """
        self._state_uuid_map = state_map

    @property
    def ws_url(self) -> str:
        """Get the WebSocket URL for the miniserver."""
        scheme = "wss" if self._config.use_tls else "ws"
        return f"{scheme}://{self._config.host}:{self._config.port}/ws/rfc6455"

    async def connect(self) -> None:
        """Connect to the Loxone miniserver WebSocket."""
        try:
            self._ws = await websockets.connect(self.ws_url)
            self._connected = True
            self._reconnect_count = 0
            logger.info("websocket_connected", url=self.ws_url)
        except Exception as e:
            self._connected = False
            logger.error("websocket_connect_failed", error=str(e))
            raise

    async def authenticate(self) -> bool:
        """Authenticate via WebSocket using the 3-tier auth flow.

        Uses the standalone ``authenticate()`` function which implements:
        1. Token-based auth with WS-provided RSA public key
        2. Token-based auth with HTTP-provided RSA public key (fallback)
        3. Hash-based HMAC-SHA1 auth (legacy fallback)

        The ``_recv_text()`` helper in auth.py transparently consumes
        binary header frames that Loxone sends before each text response.

        Returns:
            True if authentication succeeded
        """
        if not self._ws:
            return False

        try:
            result = await self._auth.authenticate_ws(self._ws)
            if result:
                logger.info("websocket_authenticated")
            else:
                logger.warning("websocket_auth_failed")
            return result
        except Exception as exc:
            logger.error(
                "websocket_auth_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False

    async def enable_status_updates(self) -> None:
        """Enable binary status updates from the miniserver.

        Sends the enablebinstatusupdate command.  The response (a text
        message) and the subsequent binary state dump are consumed by the
        receive loop — we must NOT call ``recv()`` here because that
        could accidentally swallow a binary header and corrupt the
        initial state burst.
        """
        if not self._ws:
            return
        await self._ws.send("jdev/sps/enablebinstatusupdate")
        logger.info("websocket_status_updates_requested")

    async def start(self) -> None:
        """Start the WebSocket client with receive loop and keepalive."""
        self._should_run = True
        await self.connect()

        # Start keepalive task
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Start receive loop
        self._receive_task = asyncio.create_task(self._receive_loop())

    def start_processing(self) -> None:
        """Start the receive loop and keepalive on an already-connected WebSocket.

        Use this when connect() and authenticate() were called separately
        (e.g., during server initialization) and the receive loop needs to
        be started afterwards.
        """
        self._should_run = True
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def stop(self) -> None:
        """Stop the WebSocket client gracefully."""
        self._should_run = False

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
            self._connected = False

        self._pending_binary_header = None
        self._auth.stop_token_refresh()
        logger.info("websocket_stopped")

    async def _receive_loop(self) -> None:
        """Main loop for receiving WebSocket messages."""
        while self._should_run:
            try:
                if not self._ws:
                    await self._reconnect()
                    continue

                message = await self._ws.recv()

                if isinstance(message, bytes):
                    await self._handle_binary_message(message)
                elif isinstance(message, str):
                    await self._handle_text_message(message)

            except websockets.ConnectionClosed:
                logger.warning("websocket_connection_closed")
                self._connected = False
                if self._should_run:
                    await self._reconnect()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("websocket_receive_error")
                if self._should_run:
                    await asyncio.sleep(1)

    async def _handle_binary_message(self, data: bytes) -> None:
        """Process a binary WebSocket message.

        Loxone sends binary data as two separate WebSocket messages:
        1. Header (8 bytes): cBinType=0x03, msg type, info, reserved, payload length
        2. Payload: the actual state data

        Handles:
        - Two-part protocol (header then payload as separate messages)
        - Estimated headers (estimated header → exact header → payload)
        - Combined header+payload in a single message (for compatibility)

        Loxone header format:
            BYTE cBinType;    // 0x03
            BYTE cIdentifier; // message type (0-7)
            BYTE cInfo;       // bit 7 = estimated flag
            BYTE cReserved;
            UINT nLen;        // 32-bit payload length (LE)
        """
        # Check if this is a payload for a previously received header
        if self._pending_binary_header is not None:
            msg_type, expected_len = self._pending_binary_header

            # If we receive another 8-byte message while waiting for payload,
            # it's likely the exact header following an estimated header.
            # Loxone protocol: estimated_header(8) → exact_header(8) → payload(N)
            #
            # Edge case: if expected payload IS 8 bytes, use the 0x03 marker
            # (first byte of every valid Loxone binary header) to distinguish.
            if len(data) == BINARY_HEADER_SIZE:
                is_header = (
                    expected_len != BINARY_HEADER_SIZE  # expected ≠ 8 → must be header
                    or data[0] == 0x03                 # expected = 8: check marker
                )
                if is_header:
                    new_type, payload_len, _is_estimated = self._parse_header(data)
                    if new_type == MSG_KEEPALIVE:
                        self._pending_binary_header = None
                        logger.debug("websocket_keepalive_received")
                    elif payload_len > 0:
                        # Update pending with the new (exact) header
                        self._pending_binary_header = (new_type, payload_len)
                    else:
                        self._pending_binary_header = None
                    return
                # else: expected_len == 8 and data[0] != 0x03 → it IS the payload
                # fall through to payload processing below

            # This is the actual payload
            self._pending_binary_header = None
            if len(data) != expected_len:
                logger.warning(
                    "websocket_payload_size_mismatch",
                    expected=expected_len,
                    actual=len(data),
                    msg_type=msg_type,
                )
            await self._dispatch_binary_payload(msg_type, data)
            return

        if len(data) < BINARY_HEADER_SIZE:
            return

        # Check if this is an 8-byte header-only frame
        if len(data) == BINARY_HEADER_SIZE:
            if data[0] != BINARY_HEADER_MARKER:
                logger.debug("websocket_invalid_header_marker", first_byte=data[0])
                return
            msg_type, payload_len, _is_estimated = self._parse_header(data)
            if msg_type == MSG_KEEPALIVE:
                logger.debug("websocket_keepalive_received")
            elif payload_len > 0:
                # Store header and wait for the payload in the next message
                self._pending_binary_header = (msg_type, payload_len)
            return

        # Fallback: combined header + payload in one message
        msg_type, _payload_len, _is_estimated = self._parse_header(data)
        payload = data[BINARY_HEADER_SIZE:]
        await self._dispatch_binary_payload(msg_type, payload)

    @staticmethod
    def _parse_header(data: bytes) -> tuple[int, int, bool]:
        """Parse a Loxone binary message header.

        Returns:
            (msg_type, payload_length, is_estimated)
        """
        _bin_type, msg_type, info, _reserved, payload_len = struct.unpack_from(
            "<BBBBI", data
        )
        is_estimated = (info >> 7) == 1
        return msg_type, payload_len, is_estimated

    async def _dispatch_binary_payload(self, msg_type: int, payload: bytes) -> None:
        """Route a binary payload to the appropriate processor."""
        logger.debug(
            "websocket_binary_payload",
            msg_type=msg_type,
            payload_bytes=len(payload),
        )
        if msg_type in (MSG_EVENT_VALUE_STATES, MSG_EVENT_VALUE_STATES_2):
            await self._process_value_states(payload)
        elif msg_type == MSG_EVENT_TEXT_STATES:
            await self._process_text_states(payload)
        elif msg_type == MSG_KEEPALIVE:
            logger.debug("websocket_keepalive_received")

    async def _process_value_states(self, payload: bytes) -> None:
        """Process binary value state updates.

        Each entry is 24 bytes: 16 bytes UUID + 8 bytes double.
        UUIDs are tried in both Python format (8-4-4-4-12) and
        Loxone format (8-4-4-16) for state map lookup.
        """
        entry_size = 24
        offset = 0
        matched_count = 0
        total_entries = 0
        while offset + entry_size <= len(payload):
            uuid_bytes = payload[offset : offset + 16]
            value = struct.unpack_from("<d", payload, offset + 16)[0]

            uuid_obj = UUID(bytes_le=uuid_bytes)
            uuid_python = str(uuid_obj)  # Python format: 8-4-4-4-12

            # Also build Loxone format: 8-4-4-16 (combine last two groups)
            hex_str = uuid_obj.hex
            uuid_loxone = (
                f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:]}"
            )

            # Try Python format first, then Loxone format
            matched = False
            for try_key in (uuid_python, uuid_loxone):
                if try_key in self._state_uuid_map:
                    component_uuid, state_key = self._state_uuid_map[try_key]
                    for callback in self._state_callbacks:
                        try:
                            await callback(component_uuid, state_key, value)
                        except Exception:
                            logger.exception("state_callback_error")
                    matched = True
                    matched_count += 1
                    break

            if not matched:
                logger.debug(
                    "value_state_unmapped",
                    uuid_python=uuid_python,
                    uuid_loxone=uuid_loxone,
                    value=value,
                )

            total_entries += 1
            offset += entry_size

        if total_entries > 0:
            logger.info(
                "value_states_processed",
                total=total_entries,
                matched=matched_count,
                unmatched=total_entries - matched_count,
                payload_bytes=len(payload),
            )

    async def _process_text_states(self, payload: bytes) -> None:
        """Process text state updates from binary payload.

        Loxone text state format is a packed binary struct (NOT text pairs):
            typedef struct {
                PUUID uuid;           // 128-bit UUID (bytes_le)
                PUUID uuidIcon;       // 128-bit icon UUID (bytes_le)
                uint32_t textLength;  // 32-bit unsigned int (LE)
                char text[];          // textLength bytes, padded to 4-byte boundary
            } PACKED EvDataText;

        Each entry's total size is: ceil((16 + 16 + 4 + textLength) / 4) * 4
        """
        import math

        try:
            offset = 0
            matched_count = 0
            total_entries = 0
            while offset + 36 <= len(payload):  # minimum: 16+16+4 = 36 bytes
                # Parse UUID (16 bytes, little-endian)
                uuid_obj = UUID(bytes_le=payload[offset:offset + 16])
                offset += 16

                # Skip icon UUID (16 bytes)
                offset += 16

                # Parse text length (4 bytes, little-endian)
                if offset + 4 > len(payload):
                    break
                text_length = struct.unpack_from("<I", payload, offset)[0]
                offset += 4

                # Read text data
                if offset + text_length > len(payload):
                    break
                text_value = payload[offset:offset + text_length].decode(
                    "utf-8", errors="replace"
                ).rstrip("\x00")

                # Advance past text + padding to next 4-byte boundary
                # Total entry size = ceil((16 + 16 + 4 + textLength) / 4) * 4
                entry_data_size = 16 + 16 + 4 + text_length
                total_entry_size = (math.floor((entry_data_size - 1) / 4) + 1) * 4
                offset = (offset - 36) + total_entry_size  # reset to entry start + total

                # Look up in state map — try both Python and Loxone UUID formats
                uuid_str = str(uuid_obj)  # Python format: 8-4-4-4-12

                # Also build Loxone format: 8-4-4-16 (combine last two groups)
                hex_str = uuid_obj.hex
                loxone_uuid = (
                    f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:]}"
                )

                matched = False
                for try_key in (uuid_str, loxone_uuid):
                    if try_key in self._state_uuid_map:
                        component_uuid, state_key = self._state_uuid_map[try_key]
                        for callback in self._state_callbacks:
                            try:
                                await callback(component_uuid, state_key, text_value)
                            except Exception:
                                logger.exception("state_callback_error")
                        matched = True
                        matched_count += 1
                        break

                if not matched:
                    logger.debug(
                        "text_state_unmapped",
                        uuid=uuid_str,
                        loxone_uuid=loxone_uuid,
                        value=text_value[:50],
                    )

                total_entries += 1

            if total_entries > 0:
                logger.info(
                    "text_states_processed",
                    total=total_entries,
                    matched=matched_count,
                    unmatched=total_entries - matched_count,
                    payload_bytes=len(payload),
                )
        except Exception:
            logger.exception("text_state_parse_error")

    async def _handle_text_message(self, data: str) -> None:
        """Process a text WebSocket message."""
        try:
            parsed = json.loads(data)
            code = parsed.get("LL", {}).get("Code", "")
            control = parsed.get("LL", {}).get("control", "")
            logger.debug("websocket_text_message", control=control, code=code)
        except json.JSONDecodeError:
            logger.debug("websocket_text_raw", data=data[:100])

    async def _keepalive_loop(self) -> None:
        """Send periodic keepalive messages."""
        while self._should_run:
            try:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                if self._ws and self._connected:
                    await self._ws.send("keepalive")
                    logger.debug("websocket_keepalive_sent")
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("websocket_keepalive_error")

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff (T021).

        Delays: 1s, 2s, 4s, 8s, ... max 60s
        Max failures: 10 before giving up
        """
        self._reconnect_count += 1

        if self._reconnect_count > RECONNECT_MAX_FAILURES:
            logger.error(
                "websocket_max_reconnect_failures",
                count=self._reconnect_count,
                action="circuit_breaker_open",
                hint="Restart the server to reset the circuit breaker",
            )
            self._should_run = False
            self._circuit_breaker_open = True
            return

        delay = min(
            RECONNECT_BASE_DELAY * (2 ** (self._reconnect_count - 1)),
            RECONNECT_MAX_DELAY,
        )
        logger.info(
            "websocket_reconnecting",
            attempt=self._reconnect_count,
            delay=delay,
        )
        await asyncio.sleep(delay)

        self._pending_binary_header = None

        try:
            await self.connect()
            authenticated = await self.authenticate()
            if authenticated:
                await self.enable_status_updates()
                # Notify reconnect handlers
                for callback in self._reconnect_callbacks:
                    try:
                        await callback()
                    except Exception:
                        logger.exception("reconnect_callback_error")
            else:
                logger.warning("websocket_reconnect_auth_failed")
        except Exception:
            logger.exception("websocket_reconnect_failed")
