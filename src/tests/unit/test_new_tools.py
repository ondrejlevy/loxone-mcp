"""Unit tests for new MCP tools.

Tests: list_rooms, get_room_by_name, get_lights_status, control_room_lights,
       get_temperatures, get_presence_status, get_window_door_status,
       get_alarm_status, control_alarm, get_energy_status.
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
from loxone_mcp.loxone.structure import parse_structure_file
from loxone_mcp.mcp.tools import handle_call_tool
from loxone_mcp.server import (
    AccessDeniedError,
    ToolExecutionError,
)
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager
from tests.fixtures.loxone_responses import (
    load_structure_file,
    make_state_values,
)

# --- Helpers ---


def make_server(
    mode: AccessMode = AccessMode.READ_WRITE,
) -> MagicMock:
    """Create a mock LoxoneMCPServer with full structure and states."""
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
    raw_data = load_structure_file()
    structure = parse_structure_file(raw_data)
    cache.set_structure(structure)

    # Load state values
    for uuid_str, states in make_state_values().items():
        for key, value in states.items():
            cache.update_component_state(uuid_str, key, value)

    manager = StateManager(cache)
    server.state_manager = manager

    # Mock HTTP client for control operations
    server._http_client = MagicMock()
    server._http_client.control_component = AsyncMock(
        return_value={"LL": {"Code": "200", "value": "OK"}}
    )
    server._http_client.fetch_component_states = AsyncMock(return_value={})
    server._http_client.fetch_state_value = AsyncMock(return_value=None)

    return server


# --- list_rooms ---


class TestListRooms:
    """Tests for list_rooms tool."""

    async def test_returns_all_rooms(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "list_rooms", {})
        result = json.loads(result_raw[0].text)
        assert result["roomCount"] == 4
        room_names = {r["name"] for r in result["rooms"]}
        assert room_names == {"Living Room", "Kitchen", "Bedroom", "Bathroom"}

    async def test_rooms_have_component_counts(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "list_rooms", {})
        result = json.loads(result_raw[0].text)
        for room in result["rooms"]:
            assert "componentCount" in room
            assert isinstance(room["componentCount"], int)

    async def test_rooms_have_uuids(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "list_rooms", {})
        result = json.loads(result_raw[0].text)
        for room in result["rooms"]:
            assert "uuid" in room
            # Validate UUID format
            UUID(room["uuid"])

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(server, "list_rooms", {})


# --- get_room_by_name ---


class TestGetRoomByName:
    """Tests for get_room_by_name tool."""

    async def test_find_room_exact_match(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_room_by_name", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        assert result["room"]["name"] == "Living Room"
        assert result["componentCount"] > 0

    async def test_find_room_case_insensitive(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_room_by_name", {"room_name": "living room"}
        )
        result = json.loads(result_raw[0].text)
        assert result["room"]["name"] == "Living Room"

    async def test_find_room_partial_match(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_room_by_name", {"room_name": "Kitchen"}
        )
        result = json.loads(result_raw[0].text)
        assert result["room"]["name"] == "Kitchen"

    async def test_room_not_found(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="not found"):
            await handle_call_tool(
                server, "get_room_by_name", {"room_name": "Nonexistent"}
            )

    async def test_room_name_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "get_room_by_name", {})

    async def test_components_have_states(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_room_by_name", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        for comp in result["components"]:
            assert "currentState" in comp


# --- get_lights_status ---


class TestGetLightsStatus:
    """Tests for get_lights_status tool."""

    async def test_all_lights(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_lights_status", {})
        result = json.loads(result_raw[0].text)
        assert result["totalLights"] > 0
        assert "lightsOn" in result
        assert "lightsOff" in result

    async def test_lights_in_room(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_lights_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        # Living Room has Light + Dimmer
        assert result["totalLights"] >= 2

    async def test_light_has_is_on_flag(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_lights_status", {})
        result = json.loads(result_raw[0].text)
        for light in result["lights"]:
            assert "isOn" in light
            assert isinstance(light["isOn"], bool)

    async def test_light_on_off_count(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_lights_status", {})
        result = json.loads(result_raw[0].text)
        assert result["lightsOn"] + result["lightsOff"] == result["totalLights"]


# --- control_room_lights ---


class TestControlRoomLights:
    """Tests for control_room_lights tool."""

    async def test_turn_off_lights(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server,
            "control_room_lights",
            {"room_name": "Living Room", "action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["action"] == "Off"
        assert result["totalLights"] > 0
        assert result["successful"] > 0

    async def test_turn_on_lights(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server,
            "control_room_lights",
            {"room_name": "Kitchen", "action": "On"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Kitchen"
        assert result["action"] == "On"

    async def test_invalid_action(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="must be"):
            await handle_call_tool(
                server,
                "control_room_lights",
                {"room_name": "Kitchen", "action": "Dim"},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server,
                "control_room_lights",
                {"room_name": "Kitchen", "action": "On"},
            )

    async def test_room_not_found(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="not found"):
            await handle_call_tool(
                server,
                "control_room_lights",
                {"room_name": "Garage", "action": "On"},
            )

    async def test_light_controller_uses_changeto_command(self) -> None:
        """LightController must use changeTo/0 for Off, changeTo/99 for On."""
        server = make_server()
        result_raw = await handle_call_tool(
            server,
            "control_room_lights",
            {"room_name": "Living Room", "action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] == result["totalLights"]

        # Verify the actual commands sent
        calls = server._http_client.control_component.call_args_list
        for call in calls:
            uuid_arg, action_arg = call.args
            # Get the component from the structure to check its type
            from uuid import UUID as _UUID

            structure = server.state_manager.cache.structure
            comp = structure.controls.get(_UUID(uuid_arg))
            if comp and comp.type in ("LightController", "LightControllerV2"):
                assert action_arg == "changeTo/0", (
                    f"LightController {comp.name} should use changeTo/0, got {action_arg}"
                )
            else:
                assert action_arg == "Off", (
                    f"Non-LightController {comp.name} should use Off, got {action_arg}"
                )

    async def test_light_controller_on_uses_changeto_99(self) -> None:
        """LightController must use changeTo/99 for On."""
        server = make_server()
        await handle_call_tool(
            server,
            "control_room_lights",
            {"room_name": "Kitchen", "action": "On"},
        )
        calls = server._http_client.control_component.call_args_list
        # Kitchen has a LightController
        assert any(c.args[1] == "changeTo/99" for c in calls)

    async def test_command_failure_reported_as_failed(self) -> None:
        """When Loxone returns an error, the light should be reported as failed."""
        from loxone_mcp.loxone.client import LoxoneCommandError

        server = make_server()
        server._http_client.control_component = AsyncMock(
            side_effect=LoxoneCommandError("jdev/sps/io/uuid/Off", "404")
        )
        result_raw = await handle_call_tool(
            server,
            "control_room_lights",
            {"room_name": "Living Room", "action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] == 0
        assert result["failed"] == result["totalLights"]
        for r in result["results"]:
            assert r["success"] is False
            assert "error" in r


# --- get_temperatures ---


class TestGetTemperatures:
    """Tests for get_temperatures tool."""

    async def test_all_temperatures(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_temperatures", {})
        result = json.loads(result_raw[0].text)
        assert result["sensorCount"] > 0
        assert result["room"] == "all"

    async def test_bathroom_thermostat(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"}
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Bathroom"
        # Bathroom has IRoomControllerV2
        thermostat = [t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"]
        assert len(thermostat) == 1
        assert thermostat[0]["actualTemperature"] == 21.5
        assert thermostat[0]["targetTemperature"] == 22.0

    async def test_temperature_has_mode_text(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"}
        )
        result = json.loads(result_raw[0].text)
        thermostat = [t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"]
        assert thermostat[0]["modeText"] == "Comfort heating"

    async def test_thermostat_has_comfort_temperature(self) -> None:
        """IRoomControllerV2 should report comfort temperature setpoints."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"}
        )
        result = json.loads(result_raw[0].text)
        thermostat = next(
            t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"
        )
        assert thermostat["comfortTemperature"] == 22.0
        assert thermostat["comfortTemperatureCool"] == 25.0

    async def test_thermostat_has_protection_temps(self) -> None:
        """IRoomControllerV2 should report frost/heat protection temperatures."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"}
        )
        result = json.loads(result_raw[0].text)
        thermostat = next(
            t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"
        )
        assert thermostat["frostProtectTemperature"] == 5.0
        assert thermostat["heatProtectTemperature"] == 38.0

    async def test_thermostat_has_open_window(self) -> None:
        """IRoomControllerV2 should report openWindow status."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        thermostat = next(
            t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"
        )
        # Living Room thermostat has openWindow=1
        assert thermostat["openWindow"] is True

    async def test_thermostat_has_prepare_state(self) -> None:
        """IRoomControllerV2 should report prepareState (pre-heating/cooling)."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"}
        )
        result = json.loads(result_raw[0].text)
        thermostat = next(
            t for t in result["temperatures"] if t["type"] == "IRoomControllerV2"
        )
        assert thermostat["prepareState"] == 0

    async def test_living_room_temperature_sensor(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        # Living room has InfoOnlyAnalog "Living Room Temperature"
        temp_sensors = [t for t in result["temperatures"] if "actualTemperature" in t]
        assert len(temp_sensors) >= 1


# --- get_presence_status ---


class TestGetPresenceStatus:
    """Tests for get_presence_status tool."""

    async def test_all_presence(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_presence_status", {})
        result = json.loads(result_raw[0].text)
        assert "presenceDetected" in result
        assert "roomsWithPresence" in result

    async def test_living_room_presence(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        # Living Room has PresenceDetector with active=1
        assert result["presenceDetected"] is True
        assert "Living Room" in result["roomsWithPresence"]

    async def test_presence_sensor_has_active_flag(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_presence_status", {})
        result = json.loads(result_raw[0].text)
        for sensor in result["sensors"]:
            assert "isActive" in sensor

    async def test_presence_sensor_has_motion_field(self) -> None:
        """PresenceDetector should report motionDetected from subControls."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        sensor = result["sensors"][0]
        assert "motionDetected" in sensor
        assert sensor["motionDetected"] is True

    async def test_presence_sensor_has_brightness(self) -> None:
        """PresenceDetector should report brightnessLux from subControls."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        sensor = result["sensors"][0]
        assert "brightnessLux" in sensor
        assert sensor["brightnessLux"] == 342.0

    async def test_presence_sensor_has_noise_level(self) -> None:
        """PresenceDetector should report noiseLevel from subControls."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        sensor = result["sensors"][0]
        assert "noiseLevel" in sensor
        assert sensor["noiseLevel"] == 28.5

    async def test_motion_only_triggers_presence(self) -> None:
        """If active=0 but motion=1, presence should still be detected."""
        server = make_server()
        # Override: active=0 but motion detected via subControl
        cache = server.state_manager.cache
        from tests.fixtures.loxone_responses import PRESENCE_UUID
        cache.update_component_state(str(PRESENCE_UUID), "active", 0)
        cache.update_component_state(str(PRESENCE_UUID), "subControl:Motion/active", 1)

        result_raw = await handle_call_tool(
            server, "get_presence_status", {"room_name": "Living Room"}
        )
        result = json.loads(result_raw[0].text)
        assert result["presenceDetected"] is True
        sensor = result["sensors"][0]
        assert sensor["isActive"] is False
        assert sensor["motionDetected"] is True


# --- get_window_door_status ---


class TestGetWindowDoorStatus:
    """Tests for get_window_door_status tool."""

    async def test_all_windows(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_window_door_status", {})
        result = json.loads(result_raw[0].text)
        assert result["sensorCount"] == 2  # LR Window + Bedroom Window (Intercom excluded)
        assert "allClosed" in result

    async def test_open_window_detected(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_window_door_status", {})
        result = json.loads(result_raw[0].text)
        # Loxone InfoOnlyDigital: active=1 means contact CLOSED (window shut),
        # active=0 means contact OPEN (window open).
        # Living Room Window has active=1 → closed, Bedroom Window has active=0 → open
        assert result["openCount"] == 1
        assert result["closedCount"] == 1
        assert result["allClosed"] is False
        assert result["openItems"][0]["name"] == "Bedroom Window"

    async def test_room_filter(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_window_door_status", {"room_name": "Bedroom"}
        )
        result = json.loads(result_raw[0].text)
        assert result["sensorCount"] == 1
        # Bedroom Window has active=0 → contact open → window is open
        assert result["allClosed"] is False


# --- get_alarm_status ---


class TestGetAlarmStatus:
    """Tests for get_alarm_status tool."""

    async def test_alarm_status(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_alarm_status", {})
        result = json.loads(result_raw[0].text)
        assert result["alarmCount"] == 1
        assert result["anyArmed"] is False
        assert result["anyTriggered"] is False

    async def test_alarm_details(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_alarm_status", {})
        result = json.loads(result_raw[0].text)
        alarm = result["alarms"][0]
        assert alarm["name"] == "Home Alarm"
        assert alarm["type"] == "Alarm"
        assert alarm["isArmed"] is False


# --- control_alarm ---


class TestControlAlarm:
    """Tests for control_alarm tool."""

    async def test_arm_alarm(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_alarm", {"action": "On"}
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "On"
        assert result["alarm"] == "Home Alarm"

    async def test_disarm_alarm(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_alarm", {"action": "Off"}
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "Off"

    async def test_delayed_arm(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_alarm", {"action": "delayedon"}
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "delayedon"

    async def test_invalid_action(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid action"):
            await handle_call_tool(
                server, "control_alarm", {"action": "Explode"}
            )

    async def test_action_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "control_alarm", {})

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_alarm", {"action": "On"}
            )

    async def test_find_alarm_by_name(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_alarm", {"alarm_name": "Home Alarm", "action": "On"}
        )
        result = json.loads(result_raw[0].text)
        assert result["alarm"] == "Home Alarm"


# --- get_energy_status ---


class TestGetEnergyStatus:
    """Tests for get_energy_status tool."""

    async def test_energy_components_found(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_energy_status", {})
        result = json.loads(result_raw[0].text)
        assert result["componentCount"] >= 3  # Grid, Solar, Battery

    async def test_grid_consumption(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_energy_status", {})
        result = json.loads(result_raw[0].text)
        # Grid Power Consumption with value=2450.5
        grid_components = [
            c for c in result["components"] if c.get("category") == "grid_consumption"
        ]
        assert len(grid_components) >= 1
        assert result["summary"]["gridConsumption"] == 2450.5

    async def test_solar_production(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_energy_status", {})
        result = json.loads(result_raw[0].text)
        assert result["summary"]["solarProduction"] == 3200.0

    async def test_battery_level(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_energy_status", {})
        result = json.loads(result_raw[0].text)
        assert result["summary"]["batteryLevel"] == 78.5

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(server, "get_energy_status", {})
