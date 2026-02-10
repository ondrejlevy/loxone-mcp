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

from loxone_mcp.loxone.auth import AuthTier, LoxoneAuthenticator

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

    from loxone_mcp.config import LoxoneConfig

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
        """Authenticate via WebSocket using token-based auth.

        Returns:
            True if authentication succeeded
        """
        if not self._ws:
            return False

        try:
            # Step 1: Get public key
            await self._ws.send("jdev/sys/getkey2")
            response = await self._ws.recv()
            if isinstance(response, str):
                data = json.loads(response)
                self._auth.process_getkey_response(data)

            # Step 2: Key exchange
            key_exchange_cmd = self._auth.build_key_exchange_command()
            await self._ws.send(key_exchange_cmd)
            response = await self._ws.recv()

            # Step 3: Get token
            token_cmd = self._auth.build_token_command()
            await self._ws.send(token_cmd)
            response = await self._ws.recv()
            if isinstance(response, str):
                data = json.loads(response)
                code = data.get("LL", {}).get("Code", "")
                if str(code) == "200":
                    self._auth.process_token_response(data, AuthTier.TOKEN_WS)
                    logger.info("websocket_authenticated", tier="token-ws")
                    return True
                logger.warning("websocket_auth_failed", code=code)
                return False

        except Exception:
            logger.exception("websocket_auth_error")
            return False

        return False

    async def enable_status_updates(self) -> None:
        """Enable binary status updates from the miniserver."""
        if not self._ws:
            return
        await self._ws.send("jdev/sps/enablebinstatusupdate")
        await self._ws.recv()
        logger.info("websocket_status_updates_enabled")

    async def start(self) -> None:
        """Start the WebSocket client with receive loop and keepalive."""
        self._should_run = True
        await self.connect()

        # Start keepalive task
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        # Start receive loop
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
        """Process a binary WebSocket message (T020).

        Binary message format:
        - Header (8 bytes): type indicator, msg type, reserved, payload length
        - Payload: varies by message type

        Value state updates (type 2):
        - Each entry: 16 bytes UUID + 8 bytes double value = 24 bytes
        """
        if len(data) < BINARY_HEADER_SIZE:
            return

        # Parse header
        _, msg_type, _payload_len = struct.unpack_from("<BBxx I", data)

        payload = data[BINARY_HEADER_SIZE:]

        if msg_type in (MSG_EVENT_VALUE_STATES, MSG_EVENT_VALUE_STATES_2):
            await self._process_value_states(payload)
        elif msg_type == MSG_EVENT_TEXT_STATES:
            await self._process_text_states(payload)
        elif msg_type == MSG_KEEPALIVE:
            logger.debug("websocket_keepalive_received")

    async def _process_value_states(self, payload: bytes) -> None:
        """Process binary value state updates.

        Each entry is 24 bytes: 16 bytes UUID + 8 bytes double.
        """
        entry_size = 24
        offset = 0
        while offset + entry_size <= len(payload):
            uuid_bytes = payload[offset : offset + 16]
            value = struct.unpack_from("<d", payload, offset + 16)[0]

            uuid = UUID(bytes_le=uuid_bytes)
            uuid_str = str(uuid)

            # Look up which component and state key this belongs to
            if uuid_str in self._state_uuid_map:
                component_uuid, state_key = self._state_uuid_map[uuid_str]
                for callback in self._state_callbacks:
                    try:
                        await callback(component_uuid, state_key, value)
                    except Exception:
                        logger.exception("state_callback_error")
            else:
                # Try the UUID path format (uuid/key)
                for path, (comp_uuid, key) in self._state_uuid_map.items():
                    if path.startswith(uuid_str):
                        for callback in self._state_callbacks:
                            try:
                                await callback(comp_uuid, key, value)
                            except Exception:
                                logger.exception("state_callback_error")
                        break

            offset += entry_size

    async def _process_text_states(self, payload: bytes) -> None:
        """Process text-based state updates."""
        try:
            text = payload.decode("utf-8", errors="replace")
            # Text states come as UUID\0value pairs
            parts = text.split("\0")
            i = 0
            while i + 1 < len(parts):
                uuid_str = parts[i]
                value = parts[i + 1]
                if uuid_str in self._state_uuid_map:
                    component_uuid, state_key = self._state_uuid_map[uuid_str]
                    for callback in self._state_callbacks:
                        try:
                            await callback(component_uuid, state_key, value)
                        except Exception:
                            logger.exception("state_callback_error")
                i += 2
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
