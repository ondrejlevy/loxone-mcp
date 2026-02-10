"""Unit tests for User Story 2: Control Components.

Tests control_component Tool, action validation, parameter validation,
access control, and error handling.
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
from loxone_mcp.mcp.tools import handle_call_tool
from loxone_mcp.server import (
    AccessDeniedError,
    ToolExecutionError,
)
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager


# --- Test Fixtures ---

ROOM_UUID = UUID("0a1b2c3d-0000-0000-0000-000000000001")
CATEGORY_UUID = UUID("0a1b2c3d-0000-0000-0000-000000000002")
LIGHT_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000001")
SWITCH_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000002")
DIMMER_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000003")
JALOUSIE_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000004")
THERMOSTAT_UUID = UUID("1a2b3c4d-0000-0000-0000-000000000005")


def make_structure() -> StructureFile:
    """Create a test structure file with multiple component types."""
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
            DIMMER_UUID: Component(
                uuid=DIMMER_UUID,
                name="Bedroom Dimmer",
                type="EIBDimmer",
                room=ROOM_UUID,
                category=CATEGORY_UUID,
                states={"position": "state-uuid-3"},
                capabilities=["On", "Off"],
            ),
            JALOUSIE_UUID: Component(
                uuid=JALOUSIE_UUID,
                name="Window Blind",
                type="Jalousie",
                room=ROOM_UUID,
                category=CATEGORY_UUID,
                states={"position": "state-uuid-4", "shadePosition": "state-uuid-5"},
                capabilities=["FullUp", "FullDown", "Up", "Down", "Stop", "Shade"],
            ),
            THERMOSTAT_UUID: Component(
                uuid=THERMOSTAT_UUID,
                name="Room Thermostat",
                type="IRoomControllerV2",
                room=ROOM_UUID,
                category=CATEGORY_UUID,
                states={"tempActual": "state-uuid-6", "tempTarget": "state-uuid-7"},
                capabilities=["setManualTemperature", "setComfortTemperature", "setMode"],
            ),
        },
        rooms={ROOM_UUID: Room(uuid=ROOM_UUID, name="Living Room", type=1)},
        categories={CATEGORY_UUID: Category(uuid=CATEGORY_UUID, name="Lighting", type="lights")},
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
    server._http_client.control_component = AsyncMock(return_value={"LL": {"Code": "200"}})
    return server


# --- Control Component Tests ---


class TestControlComponent:
    """Tests for control_component tool (T038)."""

    async def test_control_light_on(self) -> None:
        server = make_server(structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(LIGHT_UUID), "action": "On"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["action"] == "On"
        server._http_client.control_component.assert_called_once_with(str(LIGHT_UUID), "On")

    async def test_control_light_off(self) -> None:
        server = make_server(structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(LIGHT_UUID), "action": "Off"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        assert data["action"] == "Off"

    async def test_control_switch_pulse(self) -> None:
        server = make_server(structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(SWITCH_UUID), "action": "Pulse"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_control_jalousie_fullup(self) -> None:
        server = make_server(structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(JALOUSIE_UUID), "action": "FullUp"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_control_with_value_param(self) -> None:
        server = make_server(structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {
                "component_uuid": str(THERMOSTAT_UUID),
                "action": "setManualTemperature",
                "params": {"value": 22.5},
            },
        )
        data = json.loads(result[0].text)
        assert data["success"] is True
        server._http_client.control_component.assert_called_once_with(
            str(THERMOSTAT_UUID), "setManualTemperature/22.5"
        )


# --- Action Validation Tests (T039) ---


class TestActionValidation:
    """Tests for action validation per component type."""

    async def test_invalid_action_for_light(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="not supported"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(LIGHT_UUID), "action": "FullUp"},
            )

    async def test_invalid_action_for_switch(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="not supported"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(SWITCH_UUID), "action": "Shade"},
            )

    async def test_invalid_action_for_jalousie(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="not supported"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(JALOUSIE_UUID), "action": "On"},
            )

    async def test_valid_actions_listed_in_error(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="On.*Off"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(LIGHT_UUID), "action": "Invalid"},
            )


# --- Parameter Validation Tests (T040) ---


class TestParameterValidation:
    """Tests for control parameter validation."""

    async def test_missing_uuid_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="component_uuid is required"):
            await handle_call_tool(server, "control_component", {"action": "On"})

    async def test_missing_action_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="action is required"):
            await handle_call_tool(
                server, "control_component", {"component_uuid": str(LIGHT_UUID)}
            )

    async def test_invalid_uuid_format_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="Invalid UUID"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": "not-valid-uuid", "action": "On"},
            )

    async def test_nonexistent_component_raises(self) -> None:
        server = make_server(structure=make_structure())
        with pytest.raises(ToolExecutionError, match="Component not found"):
            await handle_call_tool(
                server,
                "control_component",
                {
                    "component_uuid": "00000000-0000-0000-0000-000000000099",
                    "action": "On",
                },
            )


# --- Access Control Tests (T041) ---


class TestControlAccessControl:
    """Tests for write access control."""

    async def test_read_only_blocks_control(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY, structure=make_structure())
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(LIGHT_UUID), "action": "On"},
            )

    async def test_read_write_allows_control(self) -> None:
        server = make_server(mode=AccessMode.READ_WRITE, structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(LIGHT_UUID), "action": "On"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True

    async def test_write_only_allows_control(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY, structure=make_structure())
        result = await handle_call_tool(
            server,
            "control_component",
            {"component_uuid": str(LIGHT_UUID), "action": "On"},
        )
        data = json.loads(result[0].text)
        assert data["success"] is True


# --- Error Handling Tests (T042) ---


class TestControlErrorHandling:
    """Tests for control operation error handling."""

    async def test_loxone_api_error(self) -> None:
        server = make_server(structure=make_structure())
        server._http_client.control_component = AsyncMock(side_effect=Exception("Connection lost"))
        with pytest.raises(ToolExecutionError, match="Connection lost"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(LIGHT_UUID), "action": "On"},
            )

    async def test_structure_not_loaded_raises(self) -> None:
        server = make_server()  # No structure loaded
        with pytest.raises(ToolExecutionError, match="Structure not loaded"):
            await handle_call_tool(
                server,
                "control_component",
                {"component_uuid": str(LIGHT_UUID), "action": "On"},
            )
