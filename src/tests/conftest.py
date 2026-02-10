"""Shared pytest fixtures and test utilities for loxone-mcp tests."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import pytest

from tests.fixtures.loxone_responses import (
    BATHROOM_UUID,
    BEDROOM_UUID,
    BLINDS_UUID,
    CLIMATE_CAT_UUID,
    DIMMER_UUID,
    KITCHEN_UUID,
    LIGHT_UUID,
    LIGHTING_CAT_UUID,
    LIVING_ROOM_UUID,
    SHADING_CAT_UUID,
    SWITCH_UUID,
    THERMOSTAT_UUID,
    load_structure_file,
    make_state_values,
)

if TYPE_CHECKING:
    from uuid import UUID

# --- Fixture: Raw structure data ---


@pytest.fixture
def raw_structure_data() -> dict[str, Any]:
    """Load the raw Loxone structure file data."""
    return load_structure_file()


@pytest.fixture
def component_states() -> dict[str, dict[str, Any]]:
    """Provide mock component state values."""
    return make_state_values()


# --- Fixture: Well-known UUIDs ---


@pytest.fixture
def room_uuids() -> dict[str, UUID]:
    """Well-known room UUIDs for tests."""
    return {
        "living_room": LIVING_ROOM_UUID,
        "kitchen": KITCHEN_UUID,
        "bedroom": BEDROOM_UUID,
        "bathroom": BATHROOM_UUID,
    }


@pytest.fixture
def category_uuids() -> dict[str, UUID]:
    """Well-known category UUIDs for tests."""
    return {
        "lighting": LIGHTING_CAT_UUID,
        "shading": SHADING_CAT_UUID,
        "climate": CLIMATE_CAT_UUID,
    }


@pytest.fixture
def component_uuids() -> dict[str, UUID]:
    """Well-known component UUIDs for tests."""
    return {
        "light": LIGHT_UUID,
        "switch": SWITCH_UUID,
        "blinds": BLINDS_UUID,
        "dimmer": DIMMER_UUID,
        "thermostat": THERMOSTAT_UUID,
    }


# --- Fixture: Mock WebSocket ---


class MockWebSocket:
    """Mock WebSocket connection for testing."""

    def __init__(self) -> None:
        self.sent_messages: list[str | bytes] = []
        self._receive_queue: asyncio.Queue[str | bytes] = asyncio.Queue()
        self.closed = False
        self.close_code: int | None = None

    async def send(self, message: str | bytes) -> None:
        """Record sent messages."""
        self.sent_messages.append(message)

    async def recv(self) -> str | bytes:
        """Return next queued message, or raise if closed."""
        if self.closed:
            raise ConnectionError("WebSocket is closed")
        return await self._receive_queue.get()

    def queue_message(self, message: str | bytes) -> None:
        """Queue a message to be received."""
        self._receive_queue.put_nowait(message)

    async def close(self, code: int = 1000) -> None:
        """Mark connection as closed."""
        self.closed = True
        self.close_code = code

    async def __aenter__(self) -> MockWebSocket:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


@pytest.fixture
def mock_websocket() -> MockWebSocket:
    """Provide a mock WebSocket connection."""
    return MockWebSocket()


# --- Fixture: Mock HTTP Server ---


class MockHTTPResponse:
    """Mock HTTP response."""

    def __init__(
        self,
        status: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text = text

    async def json(self) -> dict[str, Any]:
        if self._json_data is not None:
            return self._json_data
        result: dict[str, Any] = json.loads(self._text)
        return result

    async def text(self) -> str:
        if self._text:
            return self._text
        return json.dumps(self._json_data)

    async def __aenter__(self) -> MockHTTPResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class MockHTTPSession:
    """Mock aiohttp ClientSession for testing."""

    def __init__(self) -> None:
        self.responses: dict[str, MockHTTPResponse] = {}
        self.requests: list[dict[str, Any]] = []
        self._closed = False

    def add_response(
        self,
        url: str,
        status: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        """Register a mock response for a URL."""
        self.responses[url] = MockHTTPResponse(status, json_data, text)

    def get(self, url: str, **kwargs: Any) -> MockHTTPResponse:
        """Mock GET request."""
        self.requests.append({"method": "GET", "url": url, **kwargs})
        if url in self.responses:
            return self.responses[url]
        return MockHTTPResponse(404, json_data={"error": "Not found"})

    async def close(self) -> None:
        self._closed = True

    async def __aenter__(self) -> MockHTTPSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


@pytest.fixture
def mock_http_session() -> MockHTTPSession:
    """Provide a mock HTTP session."""
    return MockHTTPSession()


# --- Fixture: Default config ---


@pytest.fixture
def default_config() -> dict[str, Any]:
    """Provide a default configuration dictionary for tests."""
    return {
        "server": {
            "host": "0.0.0.0",
            "port": 8080,
            "transport": "http",
            "log_level": "INFO",
        },
        "loxone": {
            "host": "192.168.1.100",
            "port": 80,
            "username": "testuser",
            "password": "testpass",
            "use_tls": False,
        },
        "access_control": {
            "mode": "read-write",
        },
        "metrics": {
            "enabled": True,
            "endpoint": "/metrics",
        },
        "audit": {
            "enabled": True,
            "log_file": "logs/audit.jsonl",
            "retention_days": 90,
        },
        "structure_cache": {
            "ttl_seconds": 3600,
            "change_detection_interval": 300,
        },
    }
