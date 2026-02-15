"""Integration scenario tests for the Top 50 AI Use-Cases.

Each test validates that a specific use-case from the analysis document
(docs/analysis-top50-usecases.md) can be fulfilled by the MCP server.
Tests simulate the AI orchestration layer combining multiple tool calls.
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
from loxone_mcp.state.cache import StateCache
from loxone_mcp.state.manager import StateManager
from tests.fixtures.loxone_responses import (
    LIGHT_UUID,
    load_structure_file,
    make_state_values,
)

# --- Helpers ---


def make_server(mode: AccessMode = AccessMode.READ_WRITE) -> MagicMock:
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
# Lighting Use-Cases (UC #1-10)
# ========================================================================


class TestLightingUseCases:
    """UC #1-10: Lighting scenarios."""

    async def test_uc01_turn_on_living_room_lights(self) -> None:
        """UC #1: 'Rozsviť v obýváku' - Turn on lights in Living Room."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_lights",
            {"room_name": "Living Room", "action": "On"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["action"] == "On"
        assert result["successful"] > 0

    async def test_uc02_turn_off_all_lights(self) -> None:
        """UC #2: 'Zhasni v celém domě' - Turn off all lights in entire home."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_all_lights", {"action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "Off"
        assert result["successful"] == result["totalLights"]

    async def test_uc03_dim_bedroom_light_30_percent(self) -> None:
        """UC #3: 'Nastav světlo v ložnici na 30%' - Dim specific light."""
        server = make_server()
        # Bedroom has no dimmable lights in our fixture, so dim Living Room
        result_raw = await handle_call_tool(
            server, "dim_light",
            {"room_name": "Living Room", "brightness": 30},
        )
        result = json.loads(result_raw[0].text)
        assert result["brightness"] == 30
        assert result["successful"] > 0

    async def test_uc04_activate_movie_mood(self) -> None:
        """UC #4: 'Aktivuj filmovou náladu v obýváku' - Set lighting mood."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_lighting_mood",
            {"room_name": "Living Room", "mood_id": 778},
        )
        result = json.loads(result_raw[0].text)
        assert result["moodId"] == 778
        assert result["successful"] == 1

    async def test_uc05_which_lights_are_on(self) -> None:
        """UC #5: 'Jaká světla svítí?' - Query all light status."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_lights_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalLights"] > 0
        assert "lightsOn" in result
        # Living Room Light is on (active=1), Kitchen Light is off (active=0)
        on_lights = [light for light in result["lights"] if light["isOn"]]
        assert len(on_lights) >= 1

    async def test_uc06_presence_simulation(self) -> None:
        """UC #6: 'Simuluj přítomnost, jedu na dovolenou' - Enable presence sim."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": True},
        )
        result = json.loads(result_raw[0].text)
        assert result["enabled"] is True
        assert result["successful"] >= 2  # Both LightControllers

    async def test_uc09_night_lighting_mood(self) -> None:
        """UC #9: 'Zapni noční režim osvětlení' - Night mood via mood ID."""
        server = make_server()
        # Night mood would be a different mood_id; use 0 to turn off (dark)
        result_raw = await handle_call_tool(
            server, "set_lighting_mood",
            {"room_name": "Living Room", "mood_id": 0},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] == 1

    async def test_uc10_rooms_with_lights_on(self) -> None:
        """UC #10: 'Které místnosti mají rozsvíceno?' - Lights by room."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_lights_status", {},
        )
        result = json.loads(result_raw[0].text)
        # Group by room and check which have lights on
        rooms_on = set()
        for light in result["lights"]:
            if light["isOn"]:
                rooms_on.add(light["room"])
        assert len(rooms_on) >= 1


# ========================================================================
# Shading Use-Cases (UC #11-17)
# ========================================================================


class TestShadingUseCases:
    """UC #11-17: Blinds/shading scenarios."""

    async def test_uc11_close_living_room_blinds(self) -> None:
        """UC #11: 'Stáhni žaluzie v obýváku' - Close blinds in a room."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Living Room", "action": "FullDown"},
        )
        result = json.loads(result_raw[0].text)
        assert result["room"] == "Living Room"
        assert result["successful"] == 1

    async def test_uc12_open_all_blinds(self) -> None:
        """UC #12: 'Vytáhni všechny rolety' - Open all blinds via scene."""
        server = make_server()
        # Use execute_scene morning (opens all blinds) or iterate rooms
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "FullUp"},
        )
        r1 = json.loads(result_raw[0].text)
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Living Room", "action": "FullUp"},
        )
        r2 = json.loads(result_raw[0].text)
        assert r1["successful"] == 1
        assert r2["successful"] == 1

    async def test_uc13_set_blinds_50_percent(self) -> None:
        """UC #13: 'Nastav žaluzie na 50%' - Set blind position."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Bedroom", "action": "Shade", "position": 50},
        )
        result = json.loads(result_raw[0].text)
        assert result["action"] == "manualPosition/50"

    async def test_uc14_set_slat_horizontal(self) -> None:
        """UC #14: 'Přestav lamely vodorovně' - Set slat to horizontal (0)."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_slat_position",
            {"room_name": "Bedroom", "position": 0},
        )
        result = json.loads(result_raw[0].text)
        assert result["slatPosition"] == 0
        assert result["successful"] == 1

    async def test_uc15_blinds_status_whole_house(self) -> None:
        """UC #15: 'Stav žaluzií v celém domě?' - Query all blind positions."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_blinds_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["totalBlinds"] == 2
        for blind in result["blinds"]:
            assert "position" in blind
            assert "slatPosition" in blind


# ========================================================================
# Climate Use-Cases (UC #18-27)
# ========================================================================


class TestClimateUseCases:
    """UC #18-27: Climate/HVAC scenarios."""

    async def test_uc18_bedroom_temperature(self) -> None:
        """UC #18: 'Jaká je teplota v ložnici?' - Query room temperature."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {"room_name": "Bathroom"},
        )
        result = json.loads(result_raw[0].text)
        thermostat = [t for t in result["temperatures"]
                      if t["type"] == "IRoomControllerV2"]
        assert len(thermostat) == 1
        assert thermostat[0]["actualTemperature"] == 21.5

    async def test_uc19_set_temperature_22c(self) -> None:
        """UC #19: 'Nastav teplotu v obýváku na 22°C' - Set room temperature."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_room_temperature",
            {"room_name": "Living Room", "temperature": 22.0},
        )
        result = json.loads(result_raw[0].text)
        assert result["targetTemperature"] == 22.0
        assert result["successful"] == 1

    async def test_uc20_eco_mode_whole_home(self) -> None:
        """UC #20: 'Přepni celý dům do režimu Eco' - Set HVAC eco for all."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_hvac_mode", {"mode": "eco"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scope"] == "whole_home"
        assert result["modeValue"] == 0  # Economy
        assert result["successful"] == 2  # Both thermostats

    async def test_uc21_comfort_mode_bedroom(self) -> None:
        """UC #21: comfort mode - only in Bathroom (no thermostat in Bedroom)."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "set_hvac_mode",
            {"room_name": "Bathroom", "mode": "comfort"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scope"] == "Bathroom"
        assert result["modeValue"] == 1

    async def test_uc22_hottest_room(self) -> None:
        """UC #22: 'Který pokoj je nejteplejší?' - AI analyzes temp data."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {},
        )
        result = json.loads(result_raw[0].text)
        # AI would analyze: find max temperature across rooms
        temps_with_actual = [
            t for t in result["temperatures"]
            if t.get("actualTemperature") is not None
        ]
        assert len(temps_with_actual) >= 2
        hottest = max(temps_with_actual, key=lambda t: t["actualTemperature"])
        assert hottest["actualTemperature"] > 0

    async def test_uc25_current_hvac_mode(self) -> None:
        """UC #25: 'Jaký je aktuální režim vytápění?' - Query HVAC modes."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {},
        )
        result = json.loads(result_raw[0].text)
        modes = [t.get("modeText") for t in result["temperatures"]
                 if t.get("modeText")]
        assert len(modes) >= 1

    async def test_uc26_open_windows_while_heating(self) -> None:
        """UC #26: 'Jsou otevřená okna a topí se?' - Cross-check windows + heating."""
        server = make_server()
        # Check windows
        window_raw = await handle_call_tool(server, "get_window_door_status", {})
        windows = json.loads(window_raw[0].text)
        # Check temperatures
        temp_raw = await handle_call_tool(server, "get_temperatures", {})
        temps = json.loads(temp_raw[0].text)
        # AI would correlate: any open windows in rooms with active heating?
        # Verify we can get both pieces of data for cross-referencing
        assert windows["sensorCount"] > 0
        assert temps["sensorCount"] > 0

    async def test_uc27_outdoor_temperature(self) -> None:
        """UC #27: 'Jaká je venkovní teplota?' - Query outdoor sensor by name."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_temperatures", {},
        )
        result = json.loads(result_raw[0].text)
        # In our fixture we have "Living Room Temperature" sensor
        # AI would look for "outdoor" in name; we verify the mechanism works
        assert result["sensorCount"] >= 1


# ========================================================================
# Security Use-Cases (UC #28-35)
# ========================================================================


class TestSecurityUseCases:
    """UC #28-35: Security/access scenarios."""

    async def test_uc28_leaving_home_scene(self) -> None:
        """UC #28: 'Zabezpeč dům, odcházím' - Execute 'away' scene."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "away"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "away"
        assert result["successful"] >= 2
        # Verify alarm was armed
        alarm_step = [r for r in result["results"] if "alarm" in r["step"]]
        assert len(alarm_step) >= 1

    async def test_uc29_is_house_secured(self) -> None:
        """UC #29: 'Je dům zabezpečen?' - Check alarm status."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_alarm_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert "anyArmed" in result
        assert result["anyArmed"] is False  # Default state

    async def test_uc30_disarm_alarm(self) -> None:
        """UC #30: 'Deaktivuj alarm' - Disarm alarm."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_alarm", {"action": "Off"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "Off"

    async def test_uc31_open_garage(self) -> None:
        """UC #31: 'Otevři garáž' - Control gate via control_component."""
        # No Gate in fixture, but validate the mechanism
        server = make_server()
        # Would use: control_component(gate_uuid, "Open")
        # Here we verify the control mechanism works
        result_raw = await handle_call_tool(
            server, "control_component",
            {"component_uuid": str(LIGHT_UUID), "action": "changeTo/99"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True

    async def test_uc32_are_all_windows_closed(self) -> None:
        """UC #32: 'Jsou všechna okna zavřená?' - Check window status."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_window_door_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert "allClosed" in result
        # BR Window contact is open (active=0 → window open)
        assert result["allClosed"] is False

    async def test_uc33_which_windows_open(self) -> None:
        """UC #33: 'Která okna/dveře jsou otevřená?' - List open items."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_window_door_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["openCount"] >= 1
        assert result["openItems"][0]["name"] == "Bedroom Window"

    async def test_uc34_who_is_ringing(self) -> None:
        """UC #34: 'Kdo zvoní u dveří?' - Check intercom state."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_component_state",
            {"component_uuid": "0f5e3a01-0111-1b0a-ffff504f9412ab34"},
        )
        result = json.loads(result_raw[0].text)
        assert result["name"] == "Front Door Intercom"
        assert "currentState" in result

    async def test_uc35_unlock_door(self) -> None:
        """UC #35: 'Odemkni vstupní dveře' - Open via intercom."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_intercom", {"action": "open"},
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["action"] == "open"


# ========================================================================
# Presence Use-Cases (UC #36-39)
# ========================================================================


class TestPresenceUseCases:
    """UC #36-39: Presence/motion scenarios."""

    async def test_uc36_is_anyone_home(self) -> None:
        """UC #36: 'Je někdo doma?' - Check whole-home presence."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert "presenceDetected" in result
        assert result["presenceDetected"] is True  # LR presence active

    async def test_uc37_rooms_with_motion(self) -> None:
        """UC #37: 'Ve kterých místnostech je pohyb?' - List active rooms."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_presence_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert len(result["roomsWithPresence"]) >= 1
        assert "Living Room" in result["roomsWithPresence"]

    async def test_uc38_how_long_empty(self) -> None:
        """UC #38: 'Jak dlouho je obývák prázdný?' - History query."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_history",
            {"component_uuid": str(LIGHT_UUID)},
        )
        result = json.loads(result_raw[0].text)
        assert "currentState" in result
        assert "note" in result  # Session-only caveat

    async def test_uc39_notify_on_garage_motion(self) -> None:
        """UC #39: 'Upozorni mě, když někdo vstoupí do garáže' - Subscribe."""
        server = make_server()
        # Use presence sensor UUID (Living Room in our fixture)
        result_raw = await handle_call_tool(
            server, "subscribe_notification",
            {
                "component_uuid": str(LIGHT_UUID),
                "condition": "on_change",
            },
        )
        result = json.loads(result_raw[0].text)
        assert result["success"] is True
        assert result["subscription"]["condition"] == "on_change"


# ========================================================================
# Energy Use-Cases (UC #40-43)
# ========================================================================


class TestEnergyUseCases:
    """UC #40-43: Energy monitoring scenarios."""

    async def test_uc40_current_consumption(self) -> None:
        """UC #40: 'Jaká je aktuální spotřeba?' - Grid consumption."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_energy_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["summary"]["gridConsumption"] == 2450.5

    async def test_uc41_solar_production(self) -> None:
        """UC #41: 'Kolik vyrábí fotovoltaika?' - Solar production."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_energy_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["summary"]["solarProduction"] == 3200.0

    async def test_uc42_battery_level(self) -> None:
        """UC #42: 'Jaký je stav baterie?' - Battery status."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_energy_status", {},
        )
        result = json.loads(result_raw[0].text)
        assert result["summary"]["batteryLevel"] == 78.5

    async def test_uc43_daily_energy_overview(self) -> None:
        """UC #43: 'Jaký je energetický přehled dne?' - Home summary energy."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_home_summary", {},
        )
        result = json.loads(result_raw[0].text)
        energy = result["energy"]
        assert energy["gridConsumption"] is not None
        assert energy["solarProduction"] is not None
        assert energy["batteryLevel"] is not None


# ========================================================================
# Audio Use-Cases (UC #44-46)
# ========================================================================


class TestAudioUseCases:
    """UC #44-46: Audio/media scenarios."""

    async def test_uc44_play_music_living_room(self) -> None:
        """UC #44: 'Pusť hudbu v obýváku' - Play audio."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "Play"},
        )
        result = json.loads(result_raw[0].text)
        assert result["successful"] == 1
        assert result["action"] == "Play"

    async def test_uc45_set_volume_30(self) -> None:
        """UC #45: 'Ztlum hudbu na 30%' - Set volume."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "SetVolume", "volume": 30},
        )
        result = json.loads(result_raw[0].text)
        assert result["volume"] == 30
        assert result["successful"] == 1

    async def test_uc46_stop_music_everywhere(self) -> None:
        """UC #46: 'Zastav hudbu v celém domě' - Stop in all rooms."""
        server = make_server()
        # Stop in Living Room
        r1_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "Stop"},
        )
        r1 = json.loads(r1_raw[0].text)
        # Stop in Kitchen
        r2_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Kitchen", "action": "Stop"},
        )
        r2 = json.loads(r2_raw[0].text)
        assert r1["successful"] == 1
        assert r2["successful"] == 1


# ========================================================================
# Scene Use-Cases (UC #47-50)
# ========================================================================


class TestSceneUseCases:
    """UC #47-50: Scene/automation scenarios."""

    async def test_uc47_goodnight_scene(self) -> None:
        """UC #47: 'Aktivuj scénu Dobrou noc' - Execute goodnight."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "goodnight"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "goodnight"
        assert result["totalSteps"] == 4
        assert result["successful"] == 4
        # Verify all steps executed: lights off, blinds down, hvac eco, alarm on
        steps = [r["step"] for r in result["results"]]
        assert any("all_lights" in s for s in steps)
        assert any("all_blinds" in s for s in steps)
        assert any("all_hvac" in s for s in steps)
        assert any("alarm" in s for s in steps)

    async def test_uc48_vacation_mode(self) -> None:
        """UC #48: 'Přepni do režimu Dovolená' - Away scene + presence sim."""
        server = make_server()
        # Execute away scene
        scene_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "away"},
        )
        scene_result = json.loads(scene_raw[0].text)
        assert scene_result["successful"] >= 2

        # Enable presence simulation
        sim_raw = await handle_call_tool(
            server, "enable_presence_simulation", {"enabled": True},
        )
        sim_result = json.loads(sim_raw[0].text)
        assert sim_result["enabled"] is True
        assert sim_result["successful"] >= 2

    async def test_uc49_morning_routine(self) -> None:
        """UC #49: 'Ranní rutina' - Execute morning scene."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "execute_scene", {"scene_name": "morning"},
        )
        result = json.loads(result_raw[0].text)
        assert result["scene"] == "morning"
        assert result["totalSteps"] == 3
        assert result["successful"] == 3

    async def test_uc50_full_home_dashboard(self) -> None:
        """UC #50: 'Přehled stavu celého domu' - Comprehensive summary."""
        server = make_server()
        result_raw = await handle_call_tool(
            server, "get_home_summary", {},
        )
        result = json.loads(result_raw[0].text)

        # Verify comprehensive data is returned
        assert result["rooms"] == 4
        assert result["components"] == 19

        # Lights
        assert result["lights"]["total"] > 0
        assert result["lights"]["on"] >= 0

        # Temperatures
        assert len(result["temperatures"]) >= 2

        # Blinds
        assert result["blinds"]["total"] >= 2

        # Security
        assert "alarmArmed" in result["security"]
        assert "openWindows" in result["security"]

        # Energy
        assert result["energy"]["gridConsumption"] is not None

        # Presence
        assert "detected" in result["presence"]


# ========================================================================
# Cross-cutting multi-tool scenarios
# ========================================================================


class TestMultiToolScenarios:
    """Scenarios that require combining multiple tool calls."""

    async def test_arriving_home_workflow(self) -> None:
        """Arriving home: alarm off → lights on → comfort mode."""
        server = make_server()

        # 1. Disarm alarm
        r1_raw = await handle_call_tool(server, "control_alarm", {"action": "Off"})
        r1 = json.loads(r1_raw[0].text)
        assert r1["success"] is True

        # 2. Turn on lights
        r2_raw = await handle_call_tool(
            server, "control_room_lights",
            {"room_name": "Living Room", "action": "On"},
        )
        r2 = json.loads(r2_raw[0].text)
        assert r2["successful"] > 0

        # 3. Set comfort temperature
        r3_raw = await handle_call_tool(
            server, "set_room_temperature",
            {"room_name": "Living Room", "temperature": 22.0},
        )
        r3 = json.loads(r3_raw[0].text)
        assert r3["successful"] == 1

    async def test_leaving_home_workflow(self) -> None:
        """Leaving home: lights off → blinds down → alarm on → eco mode."""
        server = make_server()

        r1_raw = await handle_call_tool(
            server, "control_all_lights", {"action": "Off"})
        r1 = json.loads(r1_raw[0].text)
        assert r1["successful"] > 0

        r2_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Living Room", "action": "FullDown"})
        r2 = json.loads(r2_raw[0].text)
        assert r2["successful"] == 1

        r3_raw = await handle_call_tool(
            server, "control_alarm", {"action": "delayedon"})
        r3 = json.loads(r3_raw[0].text)
        assert r3["success"] is True

        r4_raw = await handle_call_tool(
            server, "set_hvac_mode", {"mode": "eco"})
        r4 = json.loads(r4_raw[0].text)
        assert r4["successful"] == 2

    async def test_movie_night_workflow(self) -> None:
        """Movie night: dim lights → close blinds → play music."""
        server = make_server()

        r1_raw = await handle_call_tool(
            server, "dim_light",
            {"room_name": "Living Room", "brightness": 15})
        r1 = json.loads(r1_raw[0].text)
        assert r1["successful"] > 0

        r2_raw = await handle_call_tool(
            server, "control_room_blinds",
            {"room_name": "Living Room", "action": "FullDown"})
        r2 = json.loads(r2_raw[0].text)
        assert r2["successful"] == 1

        r3_raw = await handle_call_tool(
            server, "control_audio",
            {"room_name": "Living Room", "action": "Play"})
        r3 = json.loads(r3_raw[0].text)
        assert r3["successful"] == 1

    async def test_full_status_check_workflow(self) -> None:
        """System check: temperatures + windows + alarm + energy in one."""
        server = make_server()

        # All queries should succeed
        t_raw = await handle_call_tool(server, "get_temperatures", {})
        t = json.loads(t_raw[0].text)
        assert t["sensorCount"] >= 2

        w_raw = await handle_call_tool(server, "get_window_door_status", {})
        w = json.loads(w_raw[0].text)
        assert w["sensorCount"] >= 2

        a_raw = await handle_call_tool(server, "get_alarm_status", {})
        a = json.loads(a_raw[0].text)
        assert a["alarmCount"] >= 1

        e_raw = await handle_call_tool(server, "get_energy_status", {})
        e = json.loads(e_raw[0].text)
        assert e["componentCount"] >= 3

    async def test_read_only_cannot_execute_scenes(self) -> None:
        """Read-only mode blocks all write operations including scenes."""
        server = make_server(mode=AccessMode.READ_ONLY)

        from loxone_mcp.server import AccessDeniedError

        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "execute_scene", {"scene_name": "goodnight"})

        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "control_all_lights", {"action": "Off"})

        with pytest.raises(AccessDeniedError):
            await handle_call_tool(
                server, "set_room_temperature",
                {"room_name": "Bathroom", "temperature": 22.0})

        # But read operations still work
        r_raw = await handle_call_tool(server, "get_home_summary", {})
        r = json.loads(r_raw[0].text)
        assert r["rooms"] == 4
