"""Unit tests for User Story 1: Query Component States.

Tests all Resource handlers, Tools, state cache integration,
notification flow, and access control.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from loxone_mcp.config import (
    AccessControlConfig,
    AccessMode,
    AuditConfig,
    LoxoneConfig,
    MetricsConfig,
    RootConfig,
    ServerConfig,
    StructureCacheConfig,
)
from loxone_mcp.loxone.models import Category, Component, Room, StructureFile
from loxone_mcp.mcp.resources import (
    get_resource_list,
    handle_read_resource,
)
from loxone_mcp.mcp.tools import (
    get_tool_list,
    handle_call_tool,
)
from loxone_mcp.server import (
    AccessDeniedError,
    ResourceNotFoundError,
    ToolExecutionError,
    ToolNotFoundError,
)
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager

# --- Test Fixtures ---

ROOM_UUID = UUID("0a1b2c3d-0000-0000-0000-000000000001")
CATEGORY_UUID = UUID("0a1b2c3d-0000-0000-0000-000000000002")
LIGHT_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000001")
SWITCH_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000002")


def make_structure() -> StructureFile:
    """Create a test structure file."""
    return StructureFile(
        last_modified="2024-01-01",
        ms_info={"swVersion": "14.0.0"},
        controls={
            LIGHT_UUID: Component(
                uuid=LIGHT_UUID,
                name="Living Room Light",
                type="LightController",
                room=ROOM_UUID,
                category=CATEGORY_UUID,
                states={"active": "state-uuid-1"},
                capabilities=["On", "Off"],
            ),
            SWITCH_UUID: Component(
                uuid=SWITCH_UUID,
                name="Kitchen Switch",
                type="Switch",
                room=ROOM_UUID,
                category=CATEGORY_UUID,
                states={"active": "state-uuid-2"},
                capabilities=["On", "Off", "Pulse"],
            ),
        },
        rooms={
            ROOM_UUID: Room(uuid=ROOM_UUID, name="Living Room", type=1),
        },
        categories={
            CATEGORY_UUID: Category(uuid=CATEGORY_UUID, name="Lighting", type="lights"),
        },
    )


def make_server(
    mode: AccessMode = AccessMode.READ_WRITE,
    structure: StructureFile | None = None,
) -> MagicMock:
    """Create a mock LoxoneMCPServer."""
    server = MagicMock()
    server.config = RootConfig(
        server=ServerConfig(),
        loxone=LoxoneConfig(host="192.168.1.100", username="test", password="test"),
        access_control=AccessControlConfig(mode=mode),
        metrics=MetricsConfig(),
        audit=AuditConfig(),
        structure_cache=StructureCacheConfig(),
    )

    cache = StateCache()
    if structure:
        cache.set_structure(structure)
    server.state_manager = StateManager(cache)
    server._http_client = AsyncMock()
    return server


# --- Resource List Tests ---


class TestResourceList:
    """Tests for get_resource_list."""

    async def test_returns_four_resources(self) -> None:
        server = make_server()
        resources = await get_resource_list(server)
        assert len(resources) == 4

    async def test_resource_uris(self) -> None:
        server = make_server()
        resources = await get_resource_list(server)
        uris = {str(r.uri) for r in resources}
        assert uris == {
            "loxone://structure",
            "loxone://components",
            "loxone://rooms",
            "loxone://categories",
        }


# --- Read Structure Resource Tests ---


class TestReadStructure:
    """Tests for loxone://structure resource."""

    async def test_read_structure_returns_data(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://structure")
        assert len(result) == 1
        data = json.loads(result[0].text)
        assert "controls" in data
        assert "rooms" in data
        assert "categories" in data

    async def test_read_structure_empty_cache(self) -> None:
        server = make_server()
        result = await handle_read_resource(server, "loxone://structure")
        data = json.loads(result[0].text)
        assert "error" in data

    async def test_read_structure_contains_components(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://structure")
        data = json.loads(result[0].text)
        assert len(data["controls"]) == 2


# --- Read Components Resource Tests ---


class TestReadComponents:
    """Tests for loxone://components resource."""

    async def test_read_components_returns_list(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://components")
        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 2

    async def test_read_components_enriched_data(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://components")
        data = json.loads(result[0].text)
        comp = next(c for c in data if c["name"] == "Living Room Light")
        assert comp["roomName"] == "Living Room"
        assert comp["categoryName"] == "Lighting"

    async def test_read_components_includes_state(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        # Set some state
        server.state_manager.cache.update_component_state(str(LIGHT_UUID), "active", 1.0)
        result = await handle_read_resource(server, "loxone://components")
        data = json.loads(result[0].text)
        comp = next(c for c in data if c["name"] == "Living Room Light")
        assert comp["currentState"]["active"] == 1.0


# --- Read Rooms Resource Tests ---


class TestReadRooms:
    """Tests for loxone://rooms resource."""

    async def test_read_rooms_returns_list(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://rooms")
        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_read_rooms_component_count(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://rooms")
        data = json.loads(result[0].text)
        assert data[0]["componentCount"] == 2
        assert data[0]["name"] == "Living Room"


# --- Read Categories Resource Tests ---


class TestReadCategories:
    """Tests for loxone://categories resource."""

    async def test_read_categories_returns_list(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://categories")
        data = json.loads(result[0].text)
        assert isinstance(data, list)
        assert len(data) == 1

    async def test_read_categories_component_count(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_read_resource(server, "loxone://categories")
        data = json.loads(result[0].text)
        assert data[0]["componentCount"] == 2
        assert data[0]["name"] == "Lighting"


# --- Resource Not Found Tests ---


class TestResourceNotFound:
    """Tests for invalid resource URIs."""

    async def test_invalid_uri_raises_error(self) -> None:
        server = make_server()
        with pytest.raises(ResourceNotFoundError):
            await handle_read_resource(server, "loxone://nonexistent")


# --- Access Control Tests ---


class TestResourceAccessControl:
    """Tests for resource access control (T036)."""

    async def test_write_only_blocks_read(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_read_resource(server, "loxone://structure")

    async def test_read_only_allows_read(self) -> None:
        structure = make_structure()
        server = make_server(mode=AccessMode.READ_ONLY, structure=structure)
        result = await handle_read_resource(server, "loxone://structure")
        assert len(result) == 1

    async def test_read_write_allows_read(self) -> None:
        structure = make_structure()
        server = make_server(mode=AccessMode.READ_WRITE, structure=structure)
        result = await handle_read_resource(server, "loxone://structure")
        assert len(result) == 1


# --- Tool List Tests ---


class TestToolList:
    """Tests for get_tool_list."""

    async def test_returns_four_tools(self) -> None:
        server = make_server()
        tools = await get_tool_list(server)
        assert len(tools) == 4

    async def test_tool_names(self) -> None:
        server = make_server()
        tools = await get_tool_list(server)
        names = {t.name for t in tools}
        assert names == {
            "get_component_state",
            "control_component",
            "get_room_components",
            "get_components_by_type",
        }


# --- Get Component State Tool Tests ---


class TestGetComponentState:
    """Tests for get_component_state tool (T029)."""

    async def test_get_existing_component(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_call_tool(
            server, "get_component_state", {"component_uuid": str(LIGHT_UUID)}
        )
        data = json.loads(result[0].text)
        assert data["name"] == "Living Room Light"
        assert data["roomName"] == "Living Room"

    async def test_get_component_with_state(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        server.state_manager.cache.update_component_state(str(LIGHT_UUID), "active", 1.0)
        result = await handle_call_tool(
            server, "get_component_state", {"component_uuid": str(LIGHT_UUID)}
        )
        data = json.loads(result[0].text)
        assert data["currentState"]["active"] == 1.0

    async def test_missing_uuid_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(server, "get_component_state", {})

    async def test_invalid_uuid_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(
                server, "get_component_state", {"component_uuid": "not-a-uuid"}
            )

    async def test_nonexistent_component_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(
                server,
                "get_component_state",
                {"component_uuid": "00000000-0000-0000-0000-000000000099"},
            )

    async def test_write_only_blocks_read(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY, structure=make_structure())
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "get_component_state", {"component_uuid": str(LIGHT_UUID)}
            )


# --- Get Room Components Tool Tests ---


class TestGetRoomComponents:
    """Tests for get_room_components tool (T030)."""

    async def test_get_room_components(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_call_tool(
            server, "get_room_components", {"room_uuid": str(ROOM_UUID)}
        )
        data = json.loads(result[0].text)
        assert data["room"]["name"] == "Living Room"
        assert data["componentCount"] == 2

    async def test_missing_room_uuid_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(server, "get_room_components", {})

    async def test_nonexistent_room_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(
                server,
                "get_room_components",
                {"room_uuid": "00000000-0000-0000-0000-000000000099"},
            )


# --- Get Components By Type Tool Tests ---


class TestGetComponentsByType:
    """Tests for get_components_by_type tool (T031)."""

    async def test_get_by_type(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_call_tool(
            server, "get_components_by_type", {"component_type": "LightController"}
        )
        data = json.loads(result[0].text)
        assert data["type"] == "LightController"
        assert data["componentCount"] == 1
        assert data["validActions"] == ["On", "Off"]

    async def test_no_components_of_type(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        result = await handle_call_tool(
            server, "get_components_by_type", {"component_type": "NonexistentType"}
        )
        data = json.loads(result[0].text)
        assert data["componentCount"] == 0

    async def test_missing_type_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError):
            await handle_call_tool(server, "get_components_by_type", {})


# --- Tool Not Found Tests ---


class TestToolNotFound:
    """Tests for invalid tool names."""

    async def test_unknown_tool_raises(self) -> None:
        server = make_server()
        with pytest.raises(ToolNotFoundError):
            await handle_call_tool(server, "nonexistent_tool", {})


# --- State Cache Integration Tests ---


class TestStateCacheIntegration:
    """Tests for state management integration."""

    async def test_state_manager_on_state_update(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        await server.state_manager.on_state_update(str(LIGHT_UUID), "active", 1.0)
        state = server.state_manager.cache.get_component_state(str(LIGHT_UUID))
        assert state is not None
        assert state["active"] == 1.0

    async def test_state_update_reflected_in_resource(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        await server.state_manager.on_state_update(str(LIGHT_UUID), "active", 1.0)
        result = await handle_read_resource(server, "loxone://components")
        data = json.loads(result[0].text)
        comp = next(c for c in data if c["name"] == "Living Room Light")
        assert comp["currentState"]["active"] == 1.0

    async def test_notification_callback_triggered(self) -> None:
        structure = make_structure()
        server = make_server(structure=structure)
        notified = []
        server.state_manager.register_notification_callback(
            lambda uri: notified.append(uri)  # type: ignore[arg-type, return-value]
        )
        await server.state_manager.on_state_update(str(LIGHT_UUID), "active", 1.0)
        await server.state_manager.flush_notifications()
        assert "loxone://components" in notified


# --- Notification Flow Tests ---


class TestNotificationFlow:
    """Tests for MCP notification flow."""

    async def test_structure_loaded_triggers_notifications(self) -> None:
        server = make_server()
        notified: list[str] = []

        async def track(uri: str) -> None:
            notified.append(uri)

        server.state_manager.register_notification_callback(track)
        structure = make_structure()
        await server.state_manager.on_structure_loaded(structure)
        assert "loxone://structure" in notified
        assert "loxone://components" in notified
        assert "loxone://rooms" in notified
        assert "loxone://categories" in notified

    async def test_websocket_reconnect_clears_state(self) -> None:
        server = make_server()
        structure = make_structure()
        server.state_manager.cache.set_structure(structure)
        server.state_manager.cache.update_component_state(str(LIGHT_UUID), "active", 1.0)
        await server.state_manager.on_websocket_reconnect()
        # State should be cleared after reconnect
        state = server.state_manager.cache.get_component_state(str(LIGHT_UUID))
        assert state is None
