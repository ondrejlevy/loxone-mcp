"""Unit tests for Wave 1-3 MCP tools.

Tests: control_room_blinds, set_room_temperature, set_hvac_mode,
       get_blinds_status, control_all_lights, get_home_summary,
       set_lighting_mood, dim_light, set_slat_position, execute_scene,
       control_audio, control_intercom, enable_presence_simulation,
       get_history, subscribe_notification.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

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
    BLINDS_UUID,
    DIMMER_UUID,
    LIGHT_UUID,
    THERMOSTAT_UUID,
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

    for uuid_str, states in make_state_values().items():
        for key, value in states.items():
            cache.update_component_state(uuid_str, key, value)

    manager = StateManager(cache)
    server.state_manager = manager

    server._http_client = MagicMock()
    server._http_client.control_component = AsyncMock(
        return_value={"LL": {"Code": "200", "value": "OK"}}
    )
    server._http_client.fetch_component_states = AsyncMock(return_value={})
    server._http_client.fetch_state_value = AsyncMock(return_value=None)

    return server


# ========================================================================
# Wave 1 Tests
# ========================================================================


class TestControlRoomBlinds:
    """Tests for control_room_blinds tool."""

    async def test_close_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "FullDown"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Bedroom"
        assert result["action"] == "FullDown"
        assert result["totalBlinds"] == 1
        assert result["successful"] == 1

    async def test_open_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Living Room", "action": "FullUp"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["successful"] == 1

    async def test_set_position(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "FullDown", "position": 50},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "manualPosition/50"
        server._http_client.control_component.assert_called_once()
        call_args = server._http_client.control_component.call_args
        assert "manualPosition/50" in call_args.args[1]

    async def test_no_blinds_in_room(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="No blinds"):
            await handle_call_tool(
                server, "control_room_blinds",
                {"room_name": "Kitchen", "action": "FullUp"},
            )

    async def test_room_not_found(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="not found"):
            await handle_call_tool(
                server, "control_room_blinds",
                {"room_name": "Garage", "action": "FullUp"},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_room_blinds",
                {"room_name": "Bedroom", "action": "FullDown"},
            )

    async def test_stop_command(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "Stop"},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "Stop"

    async def test_command_failure_reported(self) -> None:
        from loxone_mcp.loxone.client import LoxoneCommandError
        server = make_server()
        server._http_client.control_component = AsyncMock(
            side_effect=LoxoneCommandError("cmd", "404")
        )
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "FullDown"},
        )
        result = json.loads(result_raw[0].text)
        assert result["failed"] == 1
        assert result["successful"] == 0


class TestSetRoomTemperature:
    """Tests for set_room_temperature tool."""

    async def test_set_temperature(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_room_temperature",
            {"room_name": "Bathroom", "temperature": 23.0},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Bathroom"
        assert result["targetTemperature"] == 23.0
        assert result["successful"] == 1
        call_args = server._http_client.control_component.call_args
        assert "setManualTemperature/23.0" in call_args.args[1]

    async def test_living_room_thermostat(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_room_temperature",
            {"room_name": "Living Room", "temperature": 22.0},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["successful"] == 1

    async def test_temperature_out_of_range_low(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="out of range"):
            await handle_call_tool(
                server, "set_room_temperature",
                {"room_name": "Bathroom", "temperature": 3.0},
            )

    async def test_temperature_out_of_range_high(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="out of range"):
            await handle_call_tool(
                server, "set_room_temperature",
                {"room_name": "Bathroom", "temperature": 45.0},
            )

    async def test_no_thermostat_in_room(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="No thermostat"):
            await handle_call_tool(
                server, "set_room_temperature",
                {"room_name": "Kitchen", "temperature": 22.0},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "set_room_temperature",
                {"room_name": "Bathroom", "temperature": 22.0},
            )


class TestSetHvacMode:
    """Tests for set_hvac_mode tool."""

    async def test_set_eco_whole_home(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_hvac_mode", {"mode": "eco"},
        )
        result = json.loads(result_raw[0].text)
        assert result["mode"] == "eco"
        assert result["modeValue"] == 0
        assert result["scope"] == "whole_home"
        # Should target both thermostats (Bathroom + Living Room)
        assert result["totalThermostats"] == 2
        assert result["successful"] == 2

    async def test_set_comfort_specific_room(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_hvac_mode",
            {"room_name": "Bathroom", "mode": "comfort"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scope"] == "Bathroom"
        assert result["totalThermostats"] == 1
        assert result["successful"] == 1

    async def test_invalid_mode(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid mode"):
            await handle_call_tool(
                server, "set_hvac_mode", {"mode": "turbo"},
            )

    async def test_mode_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "set_hvac_mode", {})

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "set_hvac_mode", {"mode": "eco"},
            )

    async def test_building_protection_mode(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_hvac_mode", {"mode": "building_protection"},
        )
        result = json.loads(result_raw[0].text)
        assert result["modeValue"] == 3


class TestGetBlindsStatus:
    """Tests for get_blinds_status tool."""

    async def test_all_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_blinds_status", {})
        result = json.loads(result_raw[0].text)
        assert result["totalBlinds"] == 2  # Bedroom Blinds + Living Room Blinds
        assert result["room"] == "all"

    async def test_bedroom_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_blinds_status", {"room_name": "Bedroom"},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalBlinds"] == 1
        blind = result["blinds"][0]
        assert blind["name"] == "Bedroom Blinds"
        assert blind["position"] == 45.0
        assert blind["slatPosition"] == 0.0

    async def test_living_room_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_blinds_status", {"room_name": "Living Room"},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalBlinds"] == 1
        blind = result["blinds"][0]
        assert blind["name"] == "Living Room Blinds"
        assert blind["position"] == 20.0

    async def test_blind_has_fields(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_blinds_status", {})
        result = json.loads(result_raw[0].text)
        for blind in result["blinds"]:
            assert "position" in blind
            assert "slatPosition" in blind
            assert "isMoving" in blind
            assert "isFullyOpen" in blind
            assert "isFullyClosed" in blind

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(server, "get_blinds_status", {})


class TestControlAllLights:
    """Tests for control_all_lights tool."""

    async def test_turn_off_all(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_all_lights", {"action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "Off"
        # At least LR Light, Kitchen Switch, Dimmer, Kitchen Light
        assert result["totalLights"] >= 4
        assert result["successful"] == result["totalLights"]

    async def test_turn_on_all(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_all_lights", {"action": "On"},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "On"
        assert result["successful"] > 0

    async def test_invalid_action(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="must be"):
            await handle_call_tool(
                server, "control_all_lights", {"action": "Dim"},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_all_lights", {"action": "Off"},
            )

    async def test_light_controller_uses_changeto(self) -> None:
        server = make_server()
        await handle_call_tool(
            server, "control_all_lights", {"action": "Off"},
        )
        calls = server._http_client.control_component.call_args_list
        # Verify at least one changeTo/0 call for LightControllers
        changeto_calls = [c for c in calls if c.args[1] == "changeTo/0"]
        assert len(changeto_calls) >= 2  # Living Room Light + Kitchen Light


class TestGetHomeSummary:
    """Tests for get_home_summary tool."""

    async def test_summary_has_all_sections(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert "lights" in result
        assert "temperatures" in result
        assert "blinds" in result
        assert "security" in result
        assert "energy" in result
        assert "presence" in result

    async def test_summary_lights(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert result["lights"]["total"] > 0
        assert result["lights"]["on"] + result["lights"]["off"] == result["lights"]["total"]

    async def test_summary_temperatures(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert len(result["temperatures"]) == 2  # Bathroom + Living Room thermostats

    async def test_summary_blinds(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert result["blinds"]["total"] == 2

    async def test_summary_security(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert result["security"]["alarmArmed"] is False
        assert result["security"]["openWindows"] >= 1  # Bedroom Window contact is open (active=0)

    async def test_summary_energy(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert result["energy"]["gridConsumption"] == 2450.5
        assert result["energy"]["solarProduction"] == 3200.0

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(server, "get_home_summary", {})

    async def test_rooms_and_components_count(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(server, "get_home_summary", {})
        result = json.loads(result_raw[0].text)
        assert result["rooms"] == 4
        assert result["components"] == 19


# ========================================================================
# Wave 2 Tests
# ========================================================================


class TestSetLightingMood:
    """Tests for set_lighting_mood tool."""

    async def test_set_mood(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_lighting_mood",
            {"room_name": "Living Room", "mood_id": 778},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["moodId"] == 778
        assert result["successful"] == 1
        call_args = server._http_client.control_component.call_args
        assert "changeTo/778" in call_args.args[1]

    async def test_no_light_controller(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="No LightController"):
            await handle_call_tool(
                server, "set_lighting_mood",
                {"room_name": "Bedroom", "mood_id": 1},
            )

    async def test_room_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "set_lighting_mood", {"mood_id": 1},
            )

    async def test_mood_id_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "set_lighting_mood", {"room_name": "Living Room"},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "set_lighting_mood",
                {"room_name": "Living Room", "mood_id": 1},
            )


class TestDimLight:
    """Tests for dim_light tool."""

    async def test_dim_room(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "dim_light",
            {"room_name": "Living Room", "brightness": 50},
        )
        result = json.loads(result_raw[0].text)
        assert result["brightness"] == 50
        assert result["totalLights"] >= 2  # LR Light + Dimmer
        assert result["successful"] == result["totalLights"]

    async def test_dim_to_zero_turns_off(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "dim_light",
            {"room_name": "Living Room", "brightness": 0},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] > 0
        calls = server._http_client.control_component.call_args_list
        # LightController should use changeTo/0 for brightness=0
        assert any(c.args[1] == "changeTo/0" for c in calls)

    async def test_dim_by_uuid(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "dim_light",
            {"component_uuid": str(DIMMER_UUID), "brightness": 30},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalLights"] == 1
        assert result["successful"] == 1

    async def test_brightness_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "dim_light", {"room_name": "Living Room"},
            )

    async def test_brightness_out_of_range(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="0-100"):
            await handle_call_tool(
                server, "dim_light",
                {"room_name": "Living Room", "brightness": 150},
            )

    async def test_no_target(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "dim_light", {"brightness": 50},
            )


class TestSetSlatPosition:
    """Tests for set_slat_position tool."""

    async def test_set_slat(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_slat_position",
            {"room_name": "Bedroom", "position": 50},
        )
        result = json.loads(result_raw[0].text)
        assert result["slatPosition"] == 50
        assert result["totalBlinds"] == 1
        assert result["successful"] == 1
        call_args = server._http_client.control_component.call_args
        assert call_args.args[1].startswith("manualLamelle/50")

    async def test_set_slat_by_uuid(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_slat_position",
            {"component_uuid": str(BLINDS_UUID), "position": 75},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalBlinds"] == 1
        assert result["successful"] == 1

    async def test_position_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "set_slat_position", {"room_name": "Bedroom"},
            )

    async def test_position_out_of_range(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="0-100"):
            await handle_call_tool(
                server, "set_slat_position",
                {"room_name": "Bedroom", "position": 200},
            )

    async def test_no_target(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "set_slat_position", {"position": 50},
            )


class TestExecuteScene:
    """Tests for execute_scene tool."""

    async def test_goodnight_scene(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "goodnight"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "goodnight"
        assert result["totalSteps"] == 4  # lights, blinds, hvac, alarm
        assert result["successful"] == 4

    async def test_morning_scene(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "morning"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "morning"
        assert result["totalSteps"] == 3

    async def test_away_scene(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "away"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "away"
        assert result["successful"] >= 2

    async def test_home_scene(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "home"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "home"

    async def test_unknown_scene(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Unknown scene"):
            await handle_call_tool(
                server, "execute_scene", {"scene_name": "party"},
            )

    async def test_scene_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "execute_scene", {})

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "execute_scene", {"scene_name": "goodnight"},
            )


# ========================================================================
# Wave 3 Tests
# ========================================================================


class TestControlAudio:
    """Tests for control_audio tool."""

    async def test_play(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "Play"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["action"] == "Play"
        assert result["successful"] == 1

    async def test_set_volume(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "SetVolume", "volume": 60},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "SetVolume"
        assert result["volume"] == 60
        call_args = server._http_client.control_component.call_args
        assert "SetVolume/60" in call_args.args[1]

    async def test_stop(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Kitchen", "action": "Stop"},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] == 1

    async def test_set_volume_requires_volume_param(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="volume is required"):
            await handle_call_tool(
                server, "control_audio",
                {"room_name": "Living Room", "action": "SetVolume"},
            )

    async def test_invalid_action(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid action"):
            await handle_call_tool(
                server, "control_audio",
                {"room_name": "Living Room", "action": "Rewind"},
            )

    async def test_no_audio_in_room(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="No audio"):
            await handle_call_tool(
                server, "control_audio",
                {"room_name": "Bedroom", "action": "Play"},
            )

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_audio",
                {"room_name": "Living Room", "action": "Play"},
            )


class TestControlIntercom:
    """Tests for control_intercom tool."""

    async def test_open_door(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_intercom", {"action": "open"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "open"
        assert result["intercom"] == "Front Door Intercom"

    async def test_answer(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_intercom", {"action": "answer"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "answer"

    async def test_reject(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_intercom", {"action": "reject"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True

    async def test_invalid_action(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid action"):
            await handle_call_tool(
                server, "control_intercom", {"action": "explode"},
            )

    async def test_action_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "control_intercom", {})

    async def test_read_only_denied(self) -> None:
        server = make_server(mode=AccessMode.READ_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_intercom", {"action": "open"},
            )


class TestEnablePresenceSimulation:
    """Tests for enable_presence_simulation tool."""

    async def test_enable_all(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": True},
        )
        result = json.loads(result_raw[0].text)
        assert result["enabled"] is True
        assert result["totalControllers"] == 2  # LR Light + Kitchen Light
        assert result["successful"] == 2

    async def test_disable_all(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": False},
        )
        result = json.loads(result_raw[0].text)
        assert result["enabled"] is False
        assert result["successful"] == 2

    async def test_enable_specific_rooms(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "enable_presence_simulation",
            {"enabled": True, "room_names": ["Living Room"]},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalControllers"] == 1
        assert result["successful"] == 1

    async def test_enabled_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "enable_presence_simulation", {},
            )

    async def test_enable_uses_changeto_100(self) -> None:
        server = make_server()
        await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": True},
        )
        calls = server._http_client.control_component.call_args_list
        for call in calls:
            assert call.args[1] == "changeTo/100"

    async def test_disable_uses_changeto_101(self) -> None:
        server = make_server()
        await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": False},
        )
        calls = server._http_client.control_component.call_args_list
        for call in calls:
            assert call.args[1] == "changeTo/101"


class TestGetHistory:
    """Tests for get_history tool."""

    async def test_get_history(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_history",
            {"component_uuid": str(LIGHT_UUID)},
        )
        result = json.loads(result_raw[0].text)
        assert result["name"] == "Living Room Light"
        assert "currentState" in result
        assert "note" in result

    async def test_uuid_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(server, "get_history", {})

    async def test_invalid_uuid(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid UUID"):
            await handle_call_tool(
                server, "get_history", {"component_uuid": "not-a-uuid"},
            )

    async def test_component_not_found(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="not found"):
            await handle_call_tool(
                server, "get_history",
                {"component_uuid": "00000000-0000-0000-0000-000000000000"},
            )

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "get_history",
                {"component_uuid": str(LIGHT_UUID)},
            )


class TestSubscribeNotification:
    """Tests for subscribe_notification tool."""

    async def test_subscribe_on_change(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "subscribe_notification",
            {"component_uuid": str(THERMOSTAT_UUID), "condition": "on_change"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["subscription"]["condition"] == "on_change"
        assert result["subscription"]["active"] is True

    async def test_subscribe_threshold(self) -> None:
        server = make_server()
        result_raw = await handle_call_tool(
            server, "subscribe_notification",
            {
                "component_uuid": str(THERMOSTAT_UUID),
                "condition": "threshold",
                "threshold": 25.0,
                "state_key": "tempActual",
            },
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["subscription"]["threshold"] == 25.0
        assert result["subscription"]["stateKey"] == "tempActual"

    async def test_threshold_required_for_threshold_condition(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="threshold is required"):
            await handle_call_tool(
                server, "subscribe_notification",
                {"component_uuid": str(THERMOSTAT_UUID), "condition": "threshold"},
            )

    async def test_invalid_condition(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="Invalid condition"):
            await handle_call_tool(
                server, "subscribe_notification",
                {"component_uuid": str(THERMOSTAT_UUID), "condition": "magic"},
            )

    async def test_uuid_required(self) -> None:
        server = make_server()
        with pytest.raises(ToolExecutionError, match="required"):
            await handle_call_tool(
                server, "subscribe_notification", {"condition": "on_change"},
            )

    async def test_write_only_denied(self) -> None:
        server = make_server(mode=AccessMode.WRITE_ONLY)
        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "subscribe_notification",
                {"component_uuid": str(THERMOSTAT_UUID), "condition": "on_change"},
            )
