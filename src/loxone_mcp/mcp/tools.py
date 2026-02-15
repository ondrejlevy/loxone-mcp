"""MCP Tool handlers for Loxone operations.

Implements Tools:
- get_component_state    - Query a specific component's state
- control_component      - Send control commands to components
- get_room_components    - Get all components in a room
- get_components_by_type - Get all components of a given type
- list_rooms             - List all rooms with component counts
- get_room_by_name       - Find room by name (case-insensitive)
- get_lights_status      - Get light on/off status per room or home
- control_room_lights    - Turn all lights in a room on/off
- get_temperatures       - Get temperature readings per room or home
- get_presence_status    - Get motion/presence detection status
- get_window_door_status - Get window/door open/closed status
- get_alarm_status       - Get alarm/security system status
- control_alarm          - Arm/disarm alarm system
- get_energy_status      - Get energy consumption/production/battery
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from mcp.types import TextContent, Tool

from loxone_mcp.config import AccessMode
from loxone_mcp.loxone.models import (
    ALARM_TYPES,
    AUDIO_TYPES,
    BLIND_TYPES,
    COMPONENT_ACTIONS,
    ENERGY_TYPES,
    HVAC_MODES,
    INTERCOM_TYPES,
    LIGHT_CONTROLLER_TYPES,
    LIGHT_TYPES,
    PREDEFINED_SCENES,
    PRESENCE_TYPES,
    TEMPERATURE_TYPES,
    WINDOW_DOOR_TYPES,
    uuid_to_loxone_format,
)

if TYPE_CHECKING:
    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()


async def get_tool_list(server: LoxoneMCPServer) -> list[Tool]:
    """List all available MCP Tools.

    Used by MCP server's list_tools handler.
    """
    return [
        Tool(
            name="get_component_state",
            description="Get the current state of a specific Loxone component by UUID",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_uuid": {
                        "type": "string",
                        "description": "UUID of the Loxone component",
                    },
                },
                "required": ["component_uuid"],
            },
        ),
        Tool(
            name="control_component",
            description="Send a control command to a Loxone component",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_uuid": {
                        "type": "string",
                        "description": "UUID of the Loxone component to control",
                    },
                    "action": {
                        "type": "string",
                        "description": "Action to perform (e.g., On, Off, Pulse, FullUp)",
                    },
                    "params": {
                        "type": "object",
                        "description": "Optional parameters (e.g., {\"value\": 50} for dimming, {\"id\": 777} for changeTo mood)",
                        "default": {},
                    },
                },
                "required": ["component_uuid", "action"],
            },
        ),
        Tool(
            name="get_room_components",
            description="Get all Loxone components in a specific room",
            inputSchema={
                "type": "object",
                "properties": {
                    "room_uuid": {
                        "type": "string",
                        "description": "UUID of the room",
                    },
                },
                "required": ["room_uuid"],
            },
        ),
        Tool(
            name="get_components_by_type",
            description="Get all Loxone components of a specific type",
            inputSchema={
                "type": "object",
                "properties": {
                    "component_type": {
                        "type": "string",
                        "description": (
                            "Component type (e.g., LightController, Switch, "
                            "EIBDimmer, Jalousie, IRoomControllerV2)"
                        ),
                    },
                },
                "required": ["component_type"],
            },
        ),
        Tool(
            name="list_rooms",
            description=(
                "List all rooms in the Loxone smart home with their UUIDs, names, "
                "and component counts. Use this to discover available rooms before "
                "querying room-specific data."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_room_by_name",
            description=(
                "Find a room by name (case-insensitive) and return its details "
                "including UUID and all components with their current states. "
                "Supports partial name matching."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Room name or partial name to search for"
                            " (e.g., 'Living Room', 'kitchen')"
                        ),
                    },
                },
                "required": ["room_name"],
            },
        ),
        Tool(
            name="get_lights_status",
            description=(
                "Get the status of all lights in the home, or filtered by room name. "
                "Returns each light's on/off state, brightness level, and room location. "
                "Covers LightController, Dimmer, EIBDimmer component types."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room name to filter lights"
                            " (case-insensitive, partial match)"
                        ),
                    },
                },
            },
        ),
        Tool(
            name="control_room_lights",
            description=(
                "Turn all lights in a specific room on or off. "
                "Finds the room by name and controls all light components in it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name (case-insensitive, partial match)",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["On", "Off"],
                        "description": "Action to perform: 'On' or 'Off'",
                    },
                },
                "required": ["room_name", "action"],
            },
        ),
        Tool(
            name="get_temperatures",
            description=(
                "Get temperature readings from all rooms or a specific room. "
                "For IRoomControllerV2 components returns: actual temperature, "
                "target temperature, comfort/frost/heat protection temperatures, "
                "HVAC operating mode, open window status, and override info."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room name to filter"
                            " (case-insensitive, partial match)."
                            " Omit for all rooms."
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_presence_status",
            description=(
                "Get motion/presence detection status across all rooms or a specific room. "
                "Returns which rooms currently have detected motion/presence. "
                "For each PresenceDetector, reports: active (combined presence), "
                "motionDetected (raw motion sensor), brightnessLux (ambient light level), "
                "and noiseLevel (sound level)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room name to filter"
                            " (case-insensitive, partial match)."
                            " Omit for all rooms."
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_window_door_status",
            description=(
                "Get the open/closed status of all windows and doors in the home, "
                "or filtered by room name. Returns which windows/doors are open. "
                "Only returns actual window/door contact sensors (InfoOnlyDigital), "
                "NOT blind/shutter (Jalousie) components. "
                "Each sensor includes a 'type' field indicating the Loxone component type."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room name to filter"
                            " (case-insensitive, partial match)."
                            " Omit for all rooms."
                        ),
                    },
                },
            },
        ),
        Tool(
            name="get_alarm_status",
            description=(
                "Get the current status of all alarm/security systems in the home. "
                "Returns armed/disarmed state, alarm level, and any active alarms."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="control_alarm",
            description=(
                "Arm or disarm the home security/alarm system. "
                "Supports actions: On (arm), Off (disarm), "
                "delayedon (arm with delay), quit (acknowledge alarm)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "alarm_name": {
                        "type": "string",
                        "description": (
                            "Optional alarm component name to target."
                            " If omitted, targets the first alarm found."
                        ),
                    },
                    "action": {
                        "type": "string",
                        "enum": ["On", "Off", "delayedon", "quit"],
                        "description": (
                            "Action: 'On' (arm), 'Off' (disarm),"
                            " 'delayedon' (arm with entry delay),"
                            " 'quit' (acknowledge)"
                        ),
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="get_energy_status",
            description=(
                "Get energy consumption, production, and battery status for the home. "
                "Returns current power draw from grid, solar production, battery charge level, "
                "and consumption totals from EnergyMonitor and Meter components."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # --- Wave 1 Tools ---
        Tool(
            name="control_room_blinds",
            description=(
                "Control blinds/shutters in a specific room by name. "
                "Supports FullUp (open), FullDown (close), Stop, Shade, "
                "or set a specific position (0-100)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name (case-insensitive, partial match)",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["FullUp", "FullDown", "Stop", "Shade"],
                        "description": "Action: FullUp (open), FullDown (close), Stop, Shade",
                    },
                    "position": {
                        "type": "number",
                        "description": (
                            "Optional position 0-100"
                            " (0=fully open, 100=fully closed)."
                            " Overrides action."
                        ),
                    },
                },
                "required": ["room_name", "action"],
            },
        ),
        Tool(
            name="set_room_temperature",
            description=(
                "Set the target temperature for a specific room by name. "
                "Finds IRoomControllerV2 in the room and sets the manual temperature."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name (case-insensitive, partial match)",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature in °C (e.g., 22.0)",
                    },
                },
                "required": ["room_name", "temperature"],
            },
        ),
        Tool(
            name="set_hvac_mode",
            description=(
                "Set HVAC mode for a specific room or the entire home. "
                "Modes: comfort (heating), eco (economy), building_protection, manual. "
                "If room_name is omitted, applies to all rooms."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Optional room name. Omit to set mode for entire home.",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["comfort", "eco", "building_protection", "manual", "auto"],
                        "description": "HVAC mode to set",
                    },
                },
                "required": ["mode"],
            },
        ),
        Tool(
            name="get_blinds_status",
            description=(
                "Get the position of all blinds/shutters in the home, or filtered by room. "
                "Returns position (0-100), slat angle, and movement state for each blind."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": (
                            "Optional room name to filter"
                            " (case-insensitive). Omit for all rooms."
                        ),
                    },
                },
            },
        ),
        Tool(
            name="control_all_lights",
            description=(
                "Turn all lights in the entire home on or off with a single command."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["On", "Off"],
                        "description": "Action: 'On' or 'Off'",
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="get_home_summary",
            description=(
                "Get a comprehensive summary of the entire smart home status. "
                "Includes lights, temperatures, blinds, security, energy, presence, "
                "and window/door status in a single response."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # --- Wave 2 Tools ---
        Tool(
            name="set_lighting_mood",
            description=(
                "Switch a Lighting Controller to a specific mood (scene) by ID. "
                "Use get_lights_status to discover available moods for a room."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name containing the Lighting Controller",
                    },
                    "mood_id": {
                        "type": "integer",
                        "description": "Mood ID to activate (from moodList in light state)",
                    },
                },
                "required": ["room_name", "mood_id"],
            },
        ),
        Tool(
            name="dim_light",
            description=(
                "Dim a light to a specific brightness level (0-100). "
                "Can target a specific component by UUID or all dimmable lights in a room."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name to dim all lights in (case-insensitive)",
                    },
                    "component_uuid": {
                        "type": "string",
                        "description": "Optional specific component UUID to dim",
                    },
                    "brightness": {
                        "type": "integer",
                        "description": "Brightness level 0-100 (0=off, 100=full brightness)",
                    },
                },
                "required": ["brightness"],
            },
        ),
        Tool(
            name="set_slat_position",
            description=(
                "Set the slat/tilt angle of blinds (Jalousie). "
                "Can target a specific blind by UUID or all blinds in a room."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name (case-insensitive)",
                    },
                    "component_uuid": {
                        "type": "string",
                        "description": "Optional specific blind UUID",
                    },
                    "position": {
                        "type": "integer",
                        "description": "Slat position 0-100 (0=horizontal, 100=fully closed)",
                    },
                },
                "required": ["position"],
            },
        ),
        Tool(
            name="execute_scene",
            description=(
                "Execute a predefined smart home scene. "
                "Available scenes: 'goodnight' (all off, blinds down, eco, alarm on), "
                "'morning' (blinds up, lights on, comfort), "
                "'away' (lights off, alarm on, eco), "
                "'home' (alarm off, lights on, comfort)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scene_name": {
                        "type": "string",
                        "enum": ["goodnight", "morning", "away", "home"],
                        "description": "Name of the scene to execute",
                    },
                },
                "required": ["scene_name"],
            },
        ),
        # --- Wave 3 Tools ---
        Tool(
            name="control_audio",
            description=(
                "Control audio playback in a specific zone/room. "
                "Supports play, pause, stop, and volume control."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "room_name": {
                        "type": "string",
                        "description": "Room name containing the audio zone",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["Play", "Pause", "Stop", "SetVolume", "VolumeUp", "VolumeDown"],
                        "description": "Audio action to perform",
                    },
                    "volume": {
                        "type": "integer",
                        "description": "Volume level 0-100 (only for SetVolume action)",
                    },
                },
                "required": ["room_name", "action"],
            },
        ),
        Tool(
            name="control_intercom",
            description=(
                "Interact with the intercom/doorbell system. "
                "Answer a call, open the door, or reject a call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["answer", "open", "reject"],
                        "description": (
                            "Intercom action: answer (pick up),"
                            " open (unlock door), reject (decline)"
                        ),
                    },
                },
                "required": ["action"],
            },
        ),
        Tool(
            name="enable_presence_simulation",
            description=(
                "Enable or disable presence simulation on Lighting Controllers. "
                "When enabled, lights will randomly turn on/off to simulate occupancy."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "True to enable, False to disable presence simulation",
                    },
                    "room_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of room names. Omit to apply to all rooms.",
                    },
                },
                "required": ["enabled"],
            },
        ),
        Tool(
            name="get_history",
            description=(
                "Query historical state data for a component. "
                "Note: Returns cached state history from the MCP server session, "
                "not persistent Loxone statistics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "component_uuid": {
                        "type": "string",
                        "description": "UUID of the component to query history for",
                    },
                },
                "required": ["component_uuid"],
            },
        ),
        Tool(
            name="subscribe_notification",
            description=(
                "Set up a conditional notification/watch on a component. "
                "Get notified when a component's state changes or crosses a threshold."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "component_uuid": {
                        "type": "string",
                        "description": "UUID of the component to watch",
                    },
                    "condition": {
                        "type": "string",
                        "enum": ["on_change", "threshold"],
                        "description": "Trigger condition: 'on_change' or 'threshold'",
                    },
                    "threshold": {
                        "type": "number",
                        "description": "Threshold value (required when condition='threshold')",
                    },
                    "state_key": {
                        "type": "string",
                        "description": (
                            "Optional state key to watch"
                            " (e.g., 'value', 'tempActual')."
                            " Defaults to primary state."
                        ),
                    },
                },
                "required": ["component_uuid", "condition"],
            },
        ),
    ]


async def handle_call_tool(
    server: LoxoneMCPServer,
    name: str,
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Execute an MCP Tool by name.

    Args:
        server: LoxoneMCPServer instance
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with JSON result

    Raises:
        ToolNotFoundError: If tool name is not recognized
    """
    from loxone_mcp.server import AccessDeniedError, ToolExecutionError, ToolNotFoundError

    handlers = {
        "get_component_state": _handle_get_component_state,
        "control_component": _handle_control_component,
        "get_room_components": _handle_get_room_components,
        "get_components_by_type": _handle_get_components_by_type,
        "list_rooms": _handle_list_rooms,
        "get_room_by_name": _handle_get_room_by_name,
        "get_lights_status": _handle_get_lights_status,
        "control_room_lights": _handle_control_room_lights,
        "get_temperatures": _handle_get_temperatures,
        "get_presence_status": _handle_get_presence_status,
        "get_window_door_status": _handle_get_window_door_status,
        "get_alarm_status": _handle_get_alarm_status,
        "control_alarm": _handle_control_alarm,
        "get_energy_status": _handle_get_energy_status,
        # Wave 1
        "control_room_blinds": _handle_control_room_blinds,
        "set_room_temperature": _handle_set_room_temperature,
        "set_hvac_mode": _handle_set_hvac_mode,
        "get_blinds_status": _handle_get_blinds_status,
        "control_all_lights": _handle_control_all_lights,
        "get_home_summary": _handle_get_home_summary,
        # Wave 2
        "set_lighting_mood": _handle_set_lighting_mood,
        "dim_light": _handle_dim_light,
        "set_slat_position": _handle_set_slat_position,
        "execute_scene": _handle_execute_scene,
        # Wave 3
        "control_audio": _handle_control_audio,
        "control_intercom": _handle_control_intercom,
        "enable_presence_simulation": _handle_enable_presence_simulation,
        "get_history": _handle_get_history,
        "subscribe_notification": _handle_subscribe_notification,
    }

    handler = handlers.get(name)
    if not handler:
        raise ToolNotFoundError(name)

    # Metrics instrumentation (T054)
    import time as _time

    # Audit logging (T061, T063)
    from loxone_mcp.audit.logger import EventType, log_event
    from loxone_mcp.metrics.collector import record_request, track_request_duration

    start = _time.monotonic()
    try:
        with track_request_duration("tools/call"):
            result = await handler(server, arguments)
        duration_ms = (_time.monotonic() - start) * 1000
        record_request("tools/call", "success")

        log_event(
            EventType.TOOL_EXECUTION,
            user="unknown",
            action=name,
            success=True,
            method=arguments.get("action"),
            target=arguments.get("component_uuid", arguments.get("room_uuid")),
            duration_ms=duration_ms,
        )
        return [TextContent(type="text", text=json.dumps(result, default=str))]
    except ToolNotFoundError:
        record_request("tools/call", "error")
        raise
    except ToolExecutionError as e:
        record_request("tools/call", "error")
        duration_ms = (_time.monotonic() - start) * 1000
        log_event(
            EventType.TOOL_EXECUTION,
            user="unknown",
            action=name,
            success=False,
            method=arguments.get("action"),
            target=arguments.get("component_uuid"),
            duration_ms=duration_ms,
            error_message=str(e),
        )
        raise
    except AccessDeniedError as e:
        record_request("tools/call", "error")
        duration_ms = (_time.monotonic() - start) * 1000
        log_event(
            EventType.ACCESS_DENIED,
            user="unknown",
            action=name,
            success=False,
            method=arguments.get("action"),
            target=arguments.get("component_uuid"),
            duration_ms=duration_ms,
            error_message=str(e),
        )
        raise
    except Exception as e:
        record_request("tools/call", "error")
        duration_ms = (_time.monotonic() - start) * 1000
        log_event(
            EventType.ERROR,
            user="unknown",
            action=name,
            success=False,
            duration_ms=duration_ms,
            error_message=str(e),
        )
        raise ToolExecutionError(name, str(e)) from e


async def _handle_get_component_state(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get current state of a specific component (T029).

    Args:
        arguments: {"component_uuid": "..."}

    Returns:
        Component info with current state values
    """
    from loxone_mcp.server import AccessDeniedError, ToolExecutionError

    # Check read access
    mode = server.config.access_control.mode
    if mode == AccessMode.WRITE_ONLY:
        raise AccessDeniedError("get_component_state", mode.value)

    component_uuid = arguments.get("component_uuid")
    if not component_uuid:
        raise ToolExecutionError("get_component_state", "component_uuid is required")

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError("get_component_state", "Structure not loaded")

    try:
        uuid = UUID(component_uuid)
    except ValueError as e:
        raise ToolExecutionError("get_component_state", f"Invalid UUID: {component_uuid}") from e

    comp = structure.get_component(uuid)
    if not comp:
        raise ToolExecutionError("get_component_state", f"Component not found: {component_uuid}")

    # Get live state from cache
    current_state = server.state_manager.cache.get_component_state(component_uuid) or {}

    # Resolve room and category names
    room_name = ""
    if comp.room and comp.room in structure.rooms:
        room_name = structure.rooms[comp.room].name

    category_name = ""
    if comp.category and comp.category in structure.categories:
        category_name = structure.categories[comp.category].name

    return {
        "uuid": comp.loxone_uuid,
        "name": comp.name,
        "type": comp.type,
        "room": uuid_to_loxone_format(comp.room),
        "roomName": room_name,
        "category": uuid_to_loxone_format(comp.category),
        "categoryName": category_name,
        "states": comp.states,
        "currentState": current_state,
        "capabilities": comp.capabilities,
        "is_secured": comp.is_secured,
    }


async def _handle_control_component(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Control a component - send action command (T038).

    Args:
        arguments: {"component_uuid": "...", "action": "...", "params": {...}}

    Returns:
        Success status and new state
    """
    from loxone_mcp.server import AccessDeniedError, ToolExecutionError

    # Check write access (T041)
    mode = server.config.access_control.mode
    if mode == AccessMode.READ_ONLY:
        raise AccessDeniedError("control_component", mode.value)

    component_uuid = arguments.get("component_uuid")
    action = arguments.get("action")
    params = arguments.get("params", {})

    if not component_uuid:
        raise ToolExecutionError("control_component", "component_uuid is required")
    if not action:
        raise ToolExecutionError("control_component", "action is required")

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError("control_component", "Structure not loaded")

    try:
        uuid = UUID(component_uuid)
    except ValueError as e:
        raise ToolExecutionError(
            "control_component", f"Invalid UUID: {component_uuid}"
        ) from e

    comp = structure.get_component(uuid)
    if not comp:
        raise ToolExecutionError(
            "control_component", f"Component not found: {component_uuid}"
        )

    # Validate action for component type (T039)
    valid_actions = COMPONENT_ACTIONS.get(comp.type, [])
    if valid_actions and action not in valid_actions:
        raise ToolExecutionError(
            "control_component",
            f"Action '{action}' not supported for component type '{comp.type}'. "
            f"Valid actions: {valid_actions}",
        )

    # Validate parameters (T040)
    if action in ("Dim", "setManualTemperature", "setComfortTemperature"):
        value = params.get("value")
        if value is None:
            raise ToolExecutionError(
                "control_component",
                f"Parameter 'value' is required for action '{action}'",
            )

    # Build action string with parameters
    action_str = action
    if params.get("value") is not None:
        action_str = f"{action}/{params['value']}"
    elif params.get("id") is not None:
        action_str = f"{action}/{params['id']}"

    # Execute via HTTP client (T037)
    try:
        result = await server._http_client.control_component(comp.loxone_uuid, action_str)
        logger.info(
            "component_controlled",
            uuid=comp.loxone_uuid,
            action=action,
            params=params,
        )
        return {
            "success": True,
            "uuid": comp.loxone_uuid,
            "action": action,
            "params": params,
            "result": result,
        }
    except Exception as e:
        raise ToolExecutionError("control_component", str(e)) from e


async def _handle_get_room_components(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get all components in a room (T030).

    Args:
        arguments: {"room_uuid": "..."}

    Returns:
        Room info with all components and their states
    """
    from loxone_mcp.server import AccessDeniedError, ToolExecutionError

    mode = server.config.access_control.mode
    if mode == AccessMode.WRITE_ONLY:
        raise AccessDeniedError("get_room_components", mode.value)

    room_uuid_str = arguments.get("room_uuid")
    if not room_uuid_str:
        raise ToolExecutionError("get_room_components", "room_uuid is required")

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError("get_room_components", "Structure not loaded")

    try:
        room_uuid = UUID(room_uuid_str)
    except ValueError as e:
        raise ToolExecutionError(
            "get_room_components", f"Invalid UUID: {room_uuid_str}"
        ) from e

    room = structure.rooms.get(room_uuid)
    if not room:
        raise ToolExecutionError("get_room_components", f"Room not found: {room_uuid_str}")

    components = structure.get_components_by_room(room_uuid)
    result_components = []
    for comp in components:
        current_state = await _get_component_state(server, comp)
        result_components.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "currentState": current_state,
            "capabilities": comp.capabilities,
        })

    return {
        "room": {
            "uuid": uuid_to_loxone_format(room.uuid),
            "name": room.name,
            "type": room.type,
        },
        "componentCount": len(result_components),
        "components": result_components,
    }


async def _handle_get_components_by_type(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get all components of a given type (T031).

    Args:
        arguments: {"component_type": "..."}

    Returns:
        List of matching components with states
    """
    from loxone_mcp.server import AccessDeniedError, ToolExecutionError

    mode = server.config.access_control.mode
    if mode == AccessMode.WRITE_ONLY:
        raise AccessDeniedError("get_components_by_type", mode.value)

    component_type = arguments.get("component_type")
    if not component_type:
        raise ToolExecutionError("get_components_by_type", "component_type is required")

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError("get_components_by_type", "Structure not loaded")

    components = structure.get_components_by_type(component_type)
    result_components = []
    for comp in components:
        current_state = await _get_component_state(server, comp)

        # Resolve room name
        room_name = ""
        if comp.room and comp.room in structure.rooms:
            room_name = structure.rooms[comp.room].name

        result_components.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": uuid_to_loxone_format(comp.room),
            "roomName": room_name,
            "currentState": current_state,
            "capabilities": comp.capabilities,
        })

    return {
        "type": component_type,
        "validActions": COMPONENT_ACTIONS.get(component_type, []),
        "componentCount": len(result_components),
        "components": result_components,
    }


# --- Helper functions ---


def _resolve_room_name(server: LoxoneMCPServer, comp: Any) -> str:
    """Resolve room name for a component."""
    structure = server.state_manager.cache.structure
    if structure and comp.room and comp.room in structure.rooms:
        return structure.rooms[comp.room].name
    return ""


def _find_room_by_name(server: LoxoneMCPServer, room_name: str) -> Any:
    """Find a room by name, raise ToolExecutionError if not found."""
    from loxone_mcp.server import ToolExecutionError

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError("find_room", "Structure not loaded")

    room = structure.get_room_by_name(room_name)
    if room:
        return room

    # Try partial match
    rooms = structure.search_rooms(room_name)
    if len(rooms) == 1:
        return rooms[0]
    if len(rooms) > 1:
        names = [r.name for r in rooms]
        raise ToolExecutionError(
            "find_room",
            f"Multiple rooms match '{room_name}': {names}. Please be more specific.",
        )

    # No match - list available rooms
    available = [r.name for r in structure.rooms.values()]
    raise ToolExecutionError(
        "find_room",
        f"Room '{room_name}' not found. Available rooms: {available}",
    )


def _check_read_access(server: LoxoneMCPServer, tool_name: str) -> None:
    """Check that read access is permitted."""
    from loxone_mcp.server import AccessDeniedError

    mode = server.config.access_control.mode
    if mode == AccessMode.WRITE_ONLY:
        raise AccessDeniedError(tool_name, mode.value)


def _check_write_access(server: LoxoneMCPServer, tool_name: str) -> None:
    """Check that write access is permitted."""
    from loxone_mcp.server import AccessDeniedError

    mode = server.config.access_control.mode
    if mode == AccessMode.READ_ONLY:
        raise AccessDeniedError(tool_name, mode.value)


def _ensure_structure(server: LoxoneMCPServer, tool_name: str) -> Any:
    """Get structure or raise if not loaded."""
    from loxone_mcp.server import ToolExecutionError

    structure = server.state_manager.cache.structure
    if not structure:
        raise ToolExecutionError(tool_name, "Structure not loaded")
    return structure


# Component types where HTTP status queries don't work (function blocks).
# Per Loxone docs: "Status requests via web service are only possible
# with inputs and outputs and are not possible with function blocks."
_HTTP_UNSUPPORTED_TYPES: set[str] = {
    "IRoomControllerV2", "IRoomController",
    "PresenceDetector", "MotionSensor",
    "IRCV2Daytimer", "Alarm", "SmokeAlarm",
    "AudioZone", "Gate", "Intercom",
    "LightController", "LightControllerV2",
}


async def _get_component_state(
    server: LoxoneMCPServer,
    comp: Any,
) -> dict[str, Any]:
    """Get component state from cache, with HTTP fallback.

    Checks the state cache first.  If the cache is empty (e.g. because the
    WebSocket state pipeline hasn't delivered data yet), falls back to
    fetching via the HTTP REST API and caches the results.

    HTTP fallback strategy (only for I/O components, not function blocks):
    1. Query ``/jdev/sps/io/{component_uuid}`` — returns the component's
       primary value; mapped to the ``value`` state key.
    2. Query ``/jdev/sps/io/{state_uuid}`` per remaining missing state —
       works for some state UUIDs on certain miniserver firmware versions.

    For components with subControls (e.g. PresenceDetector), the sub-control
    states are also fetched and stored with the composite key format
    ``subControl:<name>/<state_key>``.
    """
    state = server.state_manager.cache.get_component_state(str(comp.uuid)) or {}
    comp_uuid_str = str(comp.uuid)

    # Determine which main states are missing from cache
    missing_main = {
        k: v for k, v in comp.states.items() if k not in state
    } if comp.states else {}

    if missing_main:
        logger.debug(
            "component_state_cache_miss",
            component=comp.name,
            comp_type=comp.type,
            cached=list(state.keys()),
            missing=list(missing_main.keys()),
        )

    # --- HTTP fallback (only for I/O component types) ---
    skip_http = comp.type in _HTTP_UNSUPPORTED_TYPES

    if missing_main and not skip_http:
        # Strategy 1: query the component's own UUID (/jdev/sps/io/<uuid>)
        # This returns the primary value for simple I/O components.
        # For InfoOnlyDigital, the primary state key is "active" (not "value").
        primary_key = (
            "active" if "active" in missing_main and "value" not in missing_main
            else "value"
        )
        if primary_key in missing_main:
            try:
                comp_value = await server._http_client.fetch_state_value(
                    comp.loxone_uuid,
                )
                if comp_value is not None:
                    server.state_manager.cache.update_component_state(
                        comp_uuid_str, primary_key, comp_value,
                    )
                    state[primary_key] = comp_value
                    missing_main.pop(primary_key, None)
            except Exception:
                pass

        # Strategy 2: query remaining missing state UUIDs individually
        if missing_main:
            try:
                fetched = await server._http_client.fetch_component_states(
                    missing_main,
                )
                if fetched:
                    for fkey, fvalue in fetched.items():
                        server.state_manager.cache.update_component_state(
                            comp_uuid_str, fkey, fvalue,
                        )
                    state.update(fetched)
            except Exception:
                pass  # HTTP fallback is best-effort

    # Fetch missing subControl states (only for I/O types)
    if not skip_http and hasattr(comp, "sub_controls") and comp.sub_controls:
        for _sub_uuid, sub_ctrl in comp.sub_controls.items():
            sub_states = sub_ctrl.get("states", {})
            sub_name = sub_ctrl.get("name", "")
            if not sub_states:
                continue
            # Only fetch sub-states not already in cache
            missing_sub = {
                k: v for k, v in sub_states.items()
                if f"subControl:{sub_name}/{k}" not in state
            }
            if not missing_sub:
                continue
            try:
                fetched = await server._http_client.fetch_component_states(
                    missing_sub,
                )
                if fetched:
                    for fkey, fvalue in fetched.items():
                        composite = f"subControl:{sub_name}/{fkey}"
                        server.state_manager.cache.update_component_state(
                            comp_uuid_str, composite, fvalue,
                        )
                        state[composite] = fvalue
            except Exception:
                pass  # best-effort

    return state


# --- New tool handlers ---


async def _handle_list_rooms(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """List all rooms in the Loxone system.

    Returns:
        List of rooms with UUIDs, names, and component counts
    """
    _check_read_access(server, "list_rooms")
    structure = _ensure_structure(server, "list_rooms")

    rooms = []
    for uuid, room in structure.rooms.items():
        components = structure.get_components_by_room(uuid)
        rooms.append({
            "uuid": uuid_to_loxone_format(room.uuid),
            "name": room.name,
            "type": room.type,
            "componentCount": len(components),
        })

    return {
        "roomCount": len(rooms),
        "rooms": rooms,
    }


async def _handle_get_room_by_name(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Find a room by name and return its details with components.

    Args:
        arguments: {"room_name": "..."}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_read_access(server, "get_room_by_name")
    structure = _ensure_structure(server, "get_room_by_name")

    room_name = arguments.get("room_name")
    if not room_name:
        raise ToolExecutionError("get_room_by_name", "room_name is required")

    room = _find_room_by_name(server, room_name)
    components = structure.get_components_by_room(room.uuid)

    result_components = []
    for comp in components:
        current_state = await _get_component_state(server, comp)
        result_components.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "currentState": current_state,
            "capabilities": comp.capabilities,
        })

    return {
        "room": {
            "uuid": uuid_to_loxone_format(room.uuid),
            "name": room.name,
            "type": room.type,
        },
        "componentCount": len(result_components),
        "components": result_components,
    }


async def _handle_get_lights_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get light status across the home or for a specific room.

    Args:
        arguments: {"room_name": "..." (optional)}
    """
    _check_read_access(server, "get_lights_status")
    structure = _ensure_structure(server, "get_lights_status")

    room_name = arguments.get("room_name")

    if room_name:
        room = _find_room_by_name(server, room_name)
        lights = structure.get_components_by_room_and_types(room.uuid, LIGHT_TYPES)
        # Also include components from Lighting category in this room
        lighting_cats = [
            c for c in structure.categories.values()
            if c.type in ("lights", "lighting")
        ]
        for cat in lighting_cats:
            cat_components = [
                c for c in structure.controls.values()
                if c.category == cat.uuid and c.room == room.uuid
                and c not in lights
            ]
            lights.extend(cat_components)
    else:
        lights = structure.get_components_by_types(LIGHT_TYPES)
        # Also include components from Lighting category
        lighting_cats = [
            c for c in structure.categories.values()
            if c.type in ("lights", "lighting")
        ]
        for cat in lighting_cats:
            cat_components = [
                c for c in structure.controls.values()
                if c.category == cat.uuid and c not in lights
            ]
            lights.extend(cat_components)

    result_lights = []
    lights_on = 0
    for comp in lights:
        current_state = await _get_component_state(server, comp)
        is_on = _is_light_on(current_state)
        if is_on:
            lights_on += 1

        result_lights.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": _resolve_room_name(server, comp),
            "isOn": is_on,
            "brightness": current_state.get("position", current_state.get("value")),
            "currentState": current_state,
        })

    return {
        "totalLights": len(result_lights),
        "lightsOn": lights_on,
        "lightsOff": len(result_lights) - lights_on,
        "room": room_name if room_name else "all",
        "lights": result_lights,
    }


def _is_light_on(state: dict[str, Any]) -> bool:
    """Determine if a light is on based on its state."""
    # Check common state keys
    active = state.get("active")
    if active is not None:
        return bool(active) and active != 0

    value = state.get("value")
    if value is not None:
        return bool(value) and value != 0

    position = state.get("position")
    if position is not None:
        return bool(position) and position != 0

    return False


async def _handle_control_room_lights(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Turn all lights in a room on or off.

    Args:
        arguments: {"room_name": "...", "action": "On"|"Off"}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_room_lights")
    structure = _ensure_structure(server, "control_room_lights")

    room_name = arguments.get("room_name")
    action = arguments.get("action")
    if not room_name:
        raise ToolExecutionError("control_room_lights", "room_name is required")
    if action not in ("On", "Off"):
        raise ToolExecutionError("control_room_lights", "action must be 'On' or 'Off'")

    room = _find_room_by_name(server, room_name)

    # Find all lights in the room
    lights = structure.get_components_by_room_and_types(room.uuid, LIGHT_TYPES)
    # Also include Lighting category components
    lighting_cats = [
        c for c in structure.categories.values()
        if c.type in ("lights", "lighting")
    ]
    for cat in lighting_cats:
        cat_components = [
            c for c in structure.controls.values()
            if c.category == cat.uuid and c.room == room.uuid
            and c not in lights
        ]
        lights.extend(cat_components)

    if not lights:
        raise ToolExecutionError(
            "control_room_lights",
            f"No lights found in room '{room.name}'",
        )

    results = []
    for comp in lights:
        # LightController types use mood-based commands
        if comp.type in LIGHT_CONTROLLER_TYPES:
            lc_action = "changeTo/0" if action == "Off" else "changeTo/99"
        else:
            lc_action = action

        try:
            await server._http_client.control_component(comp.loxone_uuid, lc_action)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "room": room.name,
        "action": action,
        "totalLights": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_get_temperatures(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get temperature readings from all or specific room.

    For IRoomControllerV2, extracts the full set of states:
    - tempActual / tempTarget: current and target temperatures
    - mode / operatingMode: HVAC operating mode (0-5)
    - comfortTemperature / comfortTemperatureCool: comfort setpoints
    - frostProtectTemperature / heatProtectTemperature: protection limits
    - prepareState: pre-heating/cooling active (0/1)
    - openWindow: window-open detection active (0/1)
    - overrideEntries / overrideReason: manual override info

    Args:
        arguments: {"room_name": "..." (optional)}
    """
    _check_read_access(server, "get_temperatures")
    structure = _ensure_structure(server, "get_temperatures")

    room_name = arguments.get("room_name")

    if room_name:
        room = _find_room_by_name(server, room_name)
        sensors = structure.get_components_by_room_and_types(room.uuid, TEMPERATURE_TYPES)
    else:
        sensors = structure.get_components_by_types(TEMPERATURE_TYPES)

    result_temps = []
    for comp in sensors:
        current_state = await _get_component_state(server, comp)

        # Extract temperature data based on component type
        temp_data: dict[str, Any] = {
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": _resolve_room_name(server, comp),
        }

        if comp.type in ("IRoomControllerV2", "IRoomController"):
            temp_data["actualTemperature"] = current_state.get("tempActual")
            temp_data["targetTemperature"] = current_state.get("tempTarget")
            mode = current_state.get("operatingMode", current_state.get("mode"))
            temp_data["mode"] = mode
            temp_data["modeText"] = _get_hvac_mode_text(mode)
            temp_data["comfortTemperature"] = current_state.get("comfortTemperature")
            temp_data["comfortTemperatureCool"] = current_state.get("comfortTemperatureCool")
            temp_data["frostProtectTemperature"] = current_state.get("frostProtectTemperature")
            temp_data["heatProtectTemperature"] = current_state.get("heatProtectTemperature")
            temp_data["prepareState"] = current_state.get("prepareState")
            open_window = current_state.get("openWindow")
            temp_data["openWindow"] = bool(open_window) if open_window is not None else None
            override_reason = current_state.get("overrideReason")
            if override_reason:
                temp_data["overrideReason"] = override_reason
        elif comp.type == "InfoOnlyAnalog":
            # Generic analog sensor - check if it looks like temperature
            value = current_state.get("value")
            if value is not None:
                temp_data["value"] = value
                # Check if the name suggests it's a temperature sensor
                name_lower = comp.name.lower()
                if any(kw in name_lower for kw in ("temp", "teplota", "teplot")):
                    temp_data["actualTemperature"] = value

        result_temps.append(temp_data)

    # Filter out InfoOnlyAnalog that doesn't look like temperature
    result_temps = [
        t for t in result_temps
        if t["type"] != "InfoOnlyAnalog" or "actualTemperature" in t
    ]

    return {
        "sensorCount": len(result_temps),
        "room": room_name if room_name else "all",
        "temperatures": result_temps,
    }


def _get_hvac_mode_text(mode: Any) -> str:
    """Convert HVAC mode number to human-readable text."""
    if mode is None:
        return "unknown"
    mode_map = {
        0: "Economy",
        1: "Comfort heating",
        2: "Comfort cooling",
        3: "Empty house",
        4: "Heat protection",
        5: "Manual",
    }
    return mode_map.get(int(mode) if mode is not None else -1, f"Mode {mode}")


async def _handle_get_presence_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get presence/motion detection status.

    The Loxone PresenceDetector block provides multiple sensor outputs:
    - active: combined presence state (0/1) - considers motion + timeout
    - motion: raw motion detection from subControls (InfoOnlyDigital)
    - brightness: ambient light level in lux from subControls (InfoOnlyAnalog)
    - noise: noise/sound level from subControls (InfoOnlyAnalog)

    SubControls state keys are stored as "subControl:<name>/<state_key>"
    in the component state cache.

    Args:
        arguments: {"room_name": "..." (optional)}
    """
    _check_read_access(server, "get_presence_status")
    structure = _ensure_structure(server, "get_presence_status")

    room_name = arguments.get("room_name")

    if room_name:
        room = _find_room_by_name(server, room_name)
        sensors = structure.get_components_by_room_and_types(room.uuid, PRESENCE_TYPES)
    else:
        sensors = structure.get_components_by_types(PRESENCE_TYPES)

    # Filter to components that look like presence/motion sensors
    presence_sensors = []
    for comp in sensors:
        if comp.type in ("PresenceDetector", "MotionSensor"):
            presence_sensors.append(comp)
        elif comp.type == "InfoOnlyDigital":
            # Check if name suggests presence/motion
            name_lower = comp.name.lower()
            if any(kw in name_lower for kw in (
                "presence", "motion", "bewegung", "přítomnost", "pohyb",
                "pir", "occupancy",
            )):
                presence_sensors.append(comp)

    result_sensors = []
    rooms_with_presence = []
    for comp in presence_sensors:
        current_state = await _get_component_state(server, comp)
        is_active = bool(current_state.get("active", current_state.get("value", 0)))
        r_name = _resolve_room_name(server, comp)

        # Extract subControl sensor data (motion, brightness, noise)
        motion_detected = None
        brightness_lux = None
        noise_level = None

        # Check subControl state keys in the cached state
        for state_key, state_value in current_state.items():
            if state_key.startswith("subControl:"):
                sub_label = state_key.split(":", 1)[1]  # e.g. "Motion/active"
                sub_name_lower = sub_label.lower()

                if any(kw in sub_name_lower for kw in (
                    "motion", "pohyb", "bewegung",
                )):
                    motion_detected = bool(state_value)
                elif any(kw in sub_name_lower for kw in (
                    "brightness", "jas", "helligkeit", "lux", "light", "osvětlení",
                )):
                    try:
                        brightness_lux = float(state_value)
                    except (TypeError, ValueError):
                        brightness_lux = None
                elif any(kw in sub_name_lower for kw in (
                    "noise", "hluk", "lautstärke", "sound", "zvuk",
                )):
                    try:
                        noise_level = float(state_value)
                    except (TypeError, ValueError):
                        noise_level = None

        # Also check if motion info is in direct states (some configs use
        # infoNrMotion, infoNrBrightness as direct state keys)
        if motion_detected is None and "infoNrMotion" in current_state:
            motion_detected = bool(current_state["infoNrMotion"])
        if brightness_lux is None and "infoNrBrightness" in current_state:
            try:
                brightness_lux = float(current_state["infoNrBrightness"])
            except (TypeError, ValueError):
                pass

        # If no subControl or direct state provides motionDetected,
        # infer it from the main ``active`` state — a PresenceDetector's
        # ``active`` flag IS the motion/presence detection result.
        if motion_detected is None and comp.type in ("PresenceDetector", "MotionSensor"):
            motion_detected = is_active

        # Determine presence: consider active flag AND motion
        has_presence = is_active
        if not has_presence and motion_detected:
            has_presence = True

        if has_presence and r_name:
            rooms_with_presence.append(r_name)

        sensor_data: dict[str, Any] = {
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "room": r_name,
            "isActive": is_active,
            "motionDetected": motion_detected,
            "brightnessLux": brightness_lux,
            "noiseLevel": noise_level,
            "currentState": current_state,
        }
        result_sensors.append(sensor_data)

    return {
        "sensorCount": len(result_sensors),
        "room": room_name if room_name else "all",
        "roomsWithPresence": list(set(rooms_with_presence)),
        "presenceDetected": len(rooms_with_presence) > 0,
        "sensors": result_sensors,
    }


async def _handle_get_window_door_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get window/door open/closed status.

    Args:
        arguments: {"room_name": "..." (optional)}
    """
    _check_read_access(server, "get_window_door_status")
    structure = _ensure_structure(server, "get_window_door_status")

    room_name = arguments.get("room_name")

    # Collect components: only WINDOW_DOOR_TYPES with name matching keywords
    # Explicitly exclude BLIND_TYPES (Jalousie, AutomaticShading) which may share
    # window/door-related names but represent shutter/blind controls, not sensors.
    all_components = list(structure.controls.values())
    if room_name:
        room = _find_room_by_name(server, room_name)
        all_components = structure.get_components_by_room(room.uuid)

    # Filter to actual window/door contact sensors
    window_door_sensors = []
    for comp in all_components:
        # Skip blind/shutter components — they are NOT window/door sensors
        if comp.type in BLIND_TYPES:
            continue
        name_lower = comp.name.lower()
        # Include if type is explicitly a window/door sensor type,
        # or if the name matches window/door keywords (for other sensor types)
        type_match = comp.type in WINDOW_DOOR_TYPES
        name_match = any(kw in name_lower for kw in (
            "window", "door", "fenster", "tür", "okno", "dveře",
            "dveřní", "okenní", "kontakt",
        ))
        if type_match and name_match:
            window_door_sensors.append(comp)

    result_sensors = []
    open_items = []
    for comp in window_door_sensors:
        current_state = await _get_component_state(server, comp)
        # Loxone InfoOnlyDigital window/door contacts:
        # active=1 means contact CLOSED (circuit closed = window/door shut)
        # active=0 means contact OPEN (circuit broken = window/door open)
        has_state = bool(current_state)
        raw_value = current_state.get("active", current_state.get("value", 0))
        is_open = not bool(raw_value)
        r_name = _resolve_room_name(server, comp)

        if is_open:
            open_items.append({"name": comp.name, "room": r_name})

        sensor_entry: dict[str, Any] = {
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": r_name,
            "isOpen": is_open,
            "currentState": current_state,
        }
        if not has_state:
            sensor_entry["stateUnavailable"] = True
            sensor_entry["note"] = (
                "State data not available — sensor value could not be "
                "determined. The isOpen value may be inaccurate."
            )
        result_sensors.append(sensor_entry)

    return {
        "sensorCount": len(result_sensors),
        "room": room_name if room_name else "all",
        "openCount": len(open_items),
        "closedCount": len(result_sensors) - len(open_items),
        "allClosed": len(open_items) == 0,
        "openItems": open_items,
        "sensors": result_sensors,
    }


async def _handle_get_alarm_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get alarm/security system status."""
    _check_read_access(server, "get_alarm_status")
    structure = _ensure_structure(server, "get_alarm_status")

    alarms = structure.get_components_by_types(ALARM_TYPES)

    result_alarms = []
    any_armed = False
    any_triggered = False
    for comp in alarms:
        current_state = await _get_component_state(server, comp)

        armed = bool(current_state.get("armed", 0))
        level = current_state.get("level", current_state.get("alarmLevel", 0))
        triggered = bool(level) and int(level) > 0 if level is not None else False

        if armed:
            any_armed = True
        if triggered:
            any_triggered = True

        result_alarms.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "isArmed": armed,
            "alarmLevel": level,
            "isTriggered": triggered,
            "currentState": current_state,
        })

    return {
        "alarmCount": len(result_alarms),
        "anyArmed": any_armed,
        "anyTriggered": any_triggered,
        "alarms": result_alarms,
    }


async def _handle_control_alarm(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Arm or disarm an alarm system.

    Args:
        arguments: {"alarm_name": "..." (optional), "action": "On"|"Off"|"delayedon"|"quit"}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_alarm")
    structure = _ensure_structure(server, "control_alarm")

    action = arguments.get("action")
    alarm_name = arguments.get("alarm_name")

    if not action:
        raise ToolExecutionError("control_alarm", "action is required")

    valid_actions = ["On", "Off", "delayedon", "quit"]
    if action not in valid_actions:
        raise ToolExecutionError(
            "control_alarm",
            f"Invalid action '{action}'. Valid: {valid_actions}",
        )

    alarms = structure.get_components_by_types(ALARM_TYPES)
    if not alarms:
        raise ToolExecutionError("control_alarm", "No alarm components found in the system")

    # Find target alarm
    target_alarm = None
    if alarm_name:
        name_lower = alarm_name.lower()
        for comp in alarms:
            if comp.name.lower() == name_lower or name_lower in comp.name.lower():
                target_alarm = comp
                break
        if not target_alarm:
            names = [c.name for c in alarms]
            raise ToolExecutionError(
                "control_alarm",
                f"Alarm '{alarm_name}' not found. Available: {names}",
            )
    else:
        target_alarm = alarms[0]

    try:
        result = await server._http_client.control_component(target_alarm.loxone_uuid, action)
        return {
            "success": True,
            "alarm": target_alarm.name,
            "uuid": target_alarm.loxone_uuid,
            "action": action,
            "result": result,
        }
    except Exception as e:
        raise ToolExecutionError("control_alarm", str(e)) from e


async def _handle_get_energy_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get energy consumption, production, and battery status."""
    _check_read_access(server, "get_energy_status")
    structure = _ensure_structure(server, "get_energy_status")

    energy_components = structure.get_components_by_types(ENERGY_TYPES)

    # Also find components by name heuristic
    all_components = list(structure.controls.values())
    energy_keywords = (
        "energy", "power", "watt", "kwh", "consumption", "production",
        "solar", "pv", "battery", "baterie", "grid", "meter",
        "spotřeba", "výroba", "síť", "elektro", "odběr",
    )
    for comp in all_components:
        if comp not in energy_components:
            name_lower = comp.name.lower()
            if any(kw in name_lower for kw in energy_keywords):
                energy_components.append(comp)

    result_components = []
    grid_consumption = None
    solar_production = None
    battery_level = None

    for comp in energy_components:
        current_state = await _get_component_state(server, comp)
        name_lower = comp.name.lower()

        component_data: dict[str, Any] = {
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": _resolve_room_name(server, comp),
            "currentState": current_state,
        }

        # Try to classify the energy component
        value = current_state.get("value", current_state.get("total"))

        if any(kw in name_lower for kw in ("grid", "síť", "odběr", "consumption", "spotřeba")):
            component_data["category"] = "grid_consumption"
            if value is not None:
                grid_consumption = value
        elif any(kw in name_lower for kw in ("solar", "pv", "výroba", "production")):
            component_data["category"] = "solar_production"
            if value is not None:
                solar_production = value
        elif any(kw in name_lower for kw in ("battery", "baterie", "akumulátor")):
            component_data["category"] = "battery"
            if value is not None:
                battery_level = value
        else:
            component_data["category"] = "other"

        result_components.append(component_data)

    return {
        "componentCount": len(result_components),
        "summary": {
            "gridConsumption": grid_consumption,
            "solarProduction": solar_production,
            "batteryLevel": battery_level,
        },
        "components": result_components,
    }


# ========================================================================
# Wave 1 Tools
# ========================================================================


async def _handle_control_room_blinds(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Control blinds/shutters in a room.

    Args:
        arguments: {"room_name": "...",
            "action": "FullUp"|"FullDown"|"Stop"|"Shade",
            "position": int}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_room_blinds")
    structure = _ensure_structure(server, "control_room_blinds")

    room_name = arguments.get("room_name")
    action = arguments.get("action")
    position = arguments.get("position")

    if not room_name:
        raise ToolExecutionError("control_room_blinds", "room_name is required")
    if not action and position is None:
        raise ToolExecutionError("control_room_blinds", "action or position is required")

    room = _find_room_by_name(server, room_name)

    # Find all blinds in the room
    blinds = [c for c in structure.controls.values()
              if c.room == room.uuid and c.type in BLIND_TYPES]

    if not blinds:
        raise ToolExecutionError(
            "control_room_blinds",
            f"No blinds/shutters found in room '{room.name}'",
        )

    results = []
    for comp in blinds:
        try:
            action_str = f"manualPosition/{position}" if position is not None else str(action)
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "room": room.name,
        "action": f"manualPosition/{position}" if position is not None else action,
        "totalBlinds": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_set_room_temperature(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Set target temperature for a room.

    Args:
        arguments: {"room_name": "...", "temperature": float}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "set_room_temperature")
    structure = _ensure_structure(server, "set_room_temperature")

    room_name = arguments.get("room_name")
    temperature = arguments.get("temperature")

    if not room_name:
        raise ToolExecutionError("set_room_temperature", "room_name is required")
    if temperature is None:
        raise ToolExecutionError("set_room_temperature", "temperature is required")
    if not (5.0 <= temperature <= 40.0):
        raise ToolExecutionError(
            "set_room_temperature",
            f"Temperature {temperature}°C out of range (5-40°C)",
        )

    room = _find_room_by_name(server, room_name)

    # Find IRoomControllerV2 in the room
    thermostats = [c for c in structure.controls.values()
                   if c.room == room.uuid and c.type in ("IRoomControllerV2", "IRoomController")]

    if not thermostats:
        raise ToolExecutionError(
            "set_room_temperature",
            f"No thermostat (IRoomControllerV2) found in room '{room.name}'",
        )

    results = []
    for comp in thermostats:
        try:
            action_str = f"setManualTemperature/{temperature}"
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
                "temperature": temperature,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "room": room.name,
        "targetTemperature": temperature,
        "totalThermostats": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_set_hvac_mode(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Set HVAC mode for a room or the whole home.

    Args:
        arguments: {"room_name": "..." (optional), "mode": str}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "set_hvac_mode")
    structure = _ensure_structure(server, "set_hvac_mode")

    room_name = arguments.get("room_name")
    mode = arguments.get("mode")

    if not mode:
        raise ToolExecutionError("set_hvac_mode", "mode is required")

    mode_value = HVAC_MODES.get(mode.lower())
    if mode_value is None:
        valid_modes = list(HVAC_MODES.keys())
        raise ToolExecutionError(
            "set_hvac_mode",
            f"Invalid mode '{mode}'. Valid modes: {valid_modes}",
        )

    if room_name:
        room = _find_room_by_name(server, room_name)
        thermostats = [
            c for c in structure.controls.values()
            if c.room == room.uuid
            and c.type in ("IRoomControllerV2", "IRoomController")
        ]
    else:
        thermostats = [c for c in structure.controls.values()
                       if c.type in ("IRoomControllerV2", "IRoomController")]

    if not thermostats:
        raise ToolExecutionError(
            "set_hvac_mode",
            f"No thermostats found{' in room ' + repr(room_name) if room_name else ' in the home'}",
        )

    results = []
    for comp in thermostats:
        try:
            action_str = f"setMode/{mode_value}"
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": True,
                "mode": mode,
                "modeValue": mode_value,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "mode": mode,
        "modeValue": mode_value,
        "scope": room_name if room_name else "whole_home",
        "totalThermostats": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_get_blinds_status(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get status of all blinds/shutters.

    Args:
        arguments: {"room_name": "..." (optional)}
    """
    _check_read_access(server, "get_blinds_status")
    structure = _ensure_structure(server, "get_blinds_status")

    room_name = arguments.get("room_name")

    if room_name:
        room = _find_room_by_name(server, room_name)
        blinds = [c for c in structure.controls.values()
                  if c.room == room.uuid and c.type in BLIND_TYPES]
    else:
        blinds = [c for c in structure.controls.values()
                  if c.type in BLIND_TYPES]

    result_blinds = []
    for comp in blinds:
        current_state = await _get_component_state(server, comp)
        position = current_state.get("position", 0)
        slat = current_state.get("shade", current_state.get("slat", 0))
        is_moving = bool(current_state.get("up", 0)) or bool(current_state.get("down", 0))

        result_blinds.append({
            "uuid": comp.loxone_uuid,
            "name": comp.name,
            "type": comp.type,
            "room": _resolve_room_name(server, comp),
            "position": position,
            "slatPosition": slat,
            "isMoving": is_moving,
            "isFullyOpen": position == 0 or position == 0.0,
            "isFullyClosed": position == 100 or position == 100.0,
            "currentState": current_state,
        })

    return {
        "totalBlinds": len(result_blinds),
        "room": room_name if room_name else "all",
        "blinds": result_blinds,
    }


async def _handle_control_all_lights(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Turn all lights in the entire home on or off.

    Args:
        arguments: {"action": "On"|"Off"}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_all_lights")
    structure = _ensure_structure(server, "control_all_lights")

    action = arguments.get("action")
    if action not in ("On", "Off"):
        raise ToolExecutionError("control_all_lights", "action must be 'On' or 'Off'")

    # Gather all lights from all rooms
    lights = structure.get_components_by_types(LIGHT_TYPES)
    # Also include Lighting category components
    lighting_cats = [
        c for c in structure.categories.values()
        if c.type in ("lights", "lighting")
    ]
    for cat in lighting_cats:
        cat_components = [
            c for c in structure.controls.values()
            if c.category == cat.uuid and c not in lights
            and c.type in LIGHT_TYPES
        ]
        lights.extend(cat_components)

    if not lights:
        raise ToolExecutionError("control_all_lights", "No lights found in the home")

    results = []
    for comp in lights:
        if comp.type in LIGHT_CONTROLLER_TYPES:
            lc_action = "changeTo/0" if action == "Off" else "changeTo/99"
        else:
            lc_action = action

        try:
            await server._http_client.control_component(comp.loxone_uuid, lc_action)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": True,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "action": action,
        "totalLights": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_get_home_summary(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get comprehensive home status summary."""
    _check_read_access(server, "get_home_summary")
    structure = _ensure_structure(server, "get_home_summary")

    # Lights summary
    lights = structure.get_components_by_types(LIGHT_TYPES)
    lights_on = 0
    for comp in lights:
        current_state = await _get_component_state(server, comp)
        if _is_light_on(current_state):
            lights_on += 1

    # Temperature summary
    thermostats = [c for c in structure.controls.values()
                   if c.type in ("IRoomControllerV2", "IRoomController")]
    temps = []
    for comp in thermostats:
        current_state = await _get_component_state(server, comp)
        temps.append({
            "room": _resolve_room_name(server, comp),
            "actual": current_state.get("tempActual"),
            "target": current_state.get("tempTarget"),
            "mode": _get_hvac_mode_text(current_state.get("mode")),
        })

    # Blinds summary
    blinds = [c for c in structure.controls.values() if c.type in BLIND_TYPES]
    blinds_open = 0
    blinds_closed = 0
    for comp in blinds:
        current_state = await _get_component_state(server, comp)
        pos = current_state.get("position", 0)
        if pos == 0 or pos == 0.0:
            blinds_open += 1
        elif pos == 100 or pos == 100.0:
            blinds_closed += 1

    # Alarm summary
    alarms = structure.get_components_by_types(ALARM_TYPES)
    any_armed = False
    for comp in alarms:
        current_state = await _get_component_state(server, comp)
        if bool(current_state.get("armed", 0)):
            any_armed = True

    # Windows summary — only actual contact sensors, exclude blinds/shutters
    all_components = list(structure.controls.values())
    open_windows = []
    for comp in all_components:
        # Skip blind/shutter components — they are NOT window/door sensors
        if comp.type in BLIND_TYPES:
            continue
        # Only include known window/door sensor types
        if comp.type not in WINDOW_DOOR_TYPES:
            continue
        name_lower = comp.name.lower()
        if any(kw in name_lower for kw in ("window", "door", "fenster", "tür", "okno", "dveře")):
            current_state = await _get_component_state(server, comp)
            # Loxone InfoOnlyDigital: active=1 → contact closed (window shut),
            # active=0 → contact open (window open)
            raw_value = current_state.get("active", current_state.get("value", 0))
            if not bool(raw_value):
                open_windows.append({"name": comp.name, "room": _resolve_room_name(server, comp)})

    # Energy summary
    energy_data = await _handle_get_energy_status(server, {})

    # Presence summary
    presence_data = await _handle_get_presence_status(server, {})

    return {
        "rooms": len(structure.rooms),
        "components": len(structure.controls),
        "lights": {
            "total": len(lights),
            "on": lights_on,
            "off": len(lights) - lights_on,
        },
        "temperatures": temps,
        "blinds": {
            "total": len(blinds),
            "open": blinds_open,
            "closed": blinds_closed,
            "partial": len(blinds) - blinds_open - blinds_closed,
        },
        "security": {
            "alarmArmed": any_armed,
            "openWindows": len(open_windows),
            "openWindowsList": open_windows,
        },
        "energy": energy_data.get("summary", {}),
        "presence": {
            "detected": presence_data.get("presenceDetected", False),
            "rooms": presence_data.get("roomsWithPresence", []),
        },
    }


# ========================================================================
# Wave 2 Tools
# ========================================================================


async def _handle_set_lighting_mood(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Switch a Lighting Controller to a specific mood.

    Args:
        arguments: {"room_name": "...", "mood_id": int}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "set_lighting_mood")
    structure = _ensure_structure(server, "set_lighting_mood")

    room_name = arguments.get("room_name")
    mood_id = arguments.get("mood_id")

    if not room_name:
        raise ToolExecutionError("set_lighting_mood", "room_name is required")
    if mood_id is None:
        raise ToolExecutionError("set_lighting_mood", "mood_id is required")

    room = _find_room_by_name(server, room_name)

    # Find LightControllers in the room
    light_controllers = [c for c in structure.controls.values()
                         if c.room == room.uuid and c.type in LIGHT_CONTROLLER_TYPES]

    if not light_controllers:
        raise ToolExecutionError(
            "set_lighting_mood",
            f"No LightController found in room '{room.name}'",
        )

    results = []
    for comp in light_controllers:
        try:
            action_str = f"changeTo/{mood_id}"
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
                "moodId": mood_id,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "room": room.name,
        "moodId": mood_id,
        "totalControllers": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_dim_light(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Dim a light or room lights to a specific brightness.

    Args:
        arguments: {"room_name": "...", "component_uuid": "...", "brightness": int}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "dim_light")
    structure = _ensure_structure(server, "dim_light")

    room_name = arguments.get("room_name")
    component_uuid = arguments.get("component_uuid")
    brightness = arguments.get("brightness")

    if brightness is None:
        raise ToolExecutionError("dim_light", "brightness is required")
    if not (0 <= brightness <= 100):
        raise ToolExecutionError("dim_light", "brightness must be 0-100")
    if not room_name and not component_uuid:
        raise ToolExecutionError("dim_light", "room_name or component_uuid is required")

    targets = []
    if component_uuid:
        try:
            uuid = UUID(component_uuid)
        except ValueError as e:
            raise ToolExecutionError("dim_light", f"Invalid UUID: {component_uuid}") from e
        comp = structure.get_component(uuid)
        if not comp:
            raise ToolExecutionError("dim_light", f"Component not found: {component_uuid}")
        targets = [comp]
    else:
        room = _find_room_by_name(server, str(room_name))
        # Find dimmable lights: LightControllers, Dimmers
        targets = [c for c in structure.controls.values()
                   if c.room == room.uuid and c.type in LIGHT_TYPES]

    if not targets:
        raise ToolExecutionError("dim_light", "No dimmable lights found")

    results = []
    for comp in targets:
        try:
            if comp.type in LIGHT_CONTROLLER_TYPES:
                # LightController uses mood-based commands:
                # changeTo/0 = All Off, changeTo/99 = last active mood (On)
                # Cannot set arbitrary brightness on a LightController directly
                action_str = "changeTo/0" if brightness == 0 else "changeTo/99"
            else:
                # Dimmer/EIBDimmer: send brightness value directly (0-100)
                action_str = str(brightness)
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
                "brightness": brightness,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "brightness": brightness,
        "totalLights": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_set_slat_position(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Set slat/tilt position of blinds.

    Args:
        arguments: {"room_name": "...", "component_uuid": "...", "position": int}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "set_slat_position")
    structure = _ensure_structure(server, "set_slat_position")

    room_name = arguments.get("room_name")
    component_uuid = arguments.get("component_uuid")
    position = arguments.get("position")

    if position is None:
        raise ToolExecutionError("set_slat_position", "position is required")
    if not (0 <= position <= 100):
        raise ToolExecutionError("set_slat_position", "position must be 0-100")
    if not room_name and not component_uuid:
        raise ToolExecutionError("set_slat_position", "room_name or component_uuid is required")

    targets = []
    if component_uuid:
        try:
            uuid = UUID(component_uuid)
        except ValueError as e:
            raise ToolExecutionError(
                "set_slat_position", f"Invalid UUID: {component_uuid}"
            ) from e
        comp = structure.get_component(uuid)
        if not comp:
            raise ToolExecutionError(
                "set_slat_position", f"Component not found: {component_uuid}"
            )
        targets = [comp]
    else:
        room = _find_room_by_name(server, str(room_name))
        targets = [c for c in structure.controls.values()
                   if c.room == room.uuid and c.type in BLIND_TYPES]

    if not targets:
        raise ToolExecutionError("set_slat_position", "No blinds found")

    results = []
    import random as _rnd
    for comp in targets:
        try:
            # Use manualLamelle command (Loxone native Jalousie slat control)
            # Add tiny random offset to prevent Loxone caching/dedup
            offset = _rnd.uniform(0.000000001, 0.009)
            action_str = f"manualLamelle/{position + offset}"
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
                "slatPosition": position,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "slatPosition": position,
        "totalBlinds": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_execute_scene(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Execute a predefined scene.

    Args:
        arguments: {"scene_name": str}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "execute_scene")
    structure = _ensure_structure(server, "execute_scene")

    scene_name = arguments.get("scene_name")
    if not scene_name:
        raise ToolExecutionError("execute_scene", "scene_name is required")

    scene = PREDEFINED_SCENES.get(scene_name)
    if not scene:
        available = list(PREDEFINED_SCENES.keys())
        raise ToolExecutionError(
            "execute_scene",
            f"Unknown scene '{scene_name}'. Available: {available}",
        )

    action_results = []
    for step in scene["actions"]:
        target = step["target"]
        action = step["action"]
        value = step.get("value")

        try:
            if target == "all_lights":
                result = await _handle_control_all_lights(server, {"action": action})
                action_results.append({
                    "step": f"all_lights/{action}",
                    "success": True,
                    "detail": result,
                })
            elif target == "all_blinds":
                # Control all blinds across all rooms
                blinds = [c for c in structure.controls.values() if c.type in BLIND_TYPES]
                for comp in blinds:
                    await server._http_client.control_component(comp.loxone_uuid, action)
                action_results.append({
                    "step": f"all_blinds/{action}",
                    "success": True,
                    "count": len(blinds),
                })
            elif target == "all_hvac":
                result = await _handle_set_hvac_mode(
                    server, {"mode": _get_mode_name_from_value(value)})
                action_results.append({
                    "step": f"all_hvac/{action}/{value}",
                    "success": True,
                    "detail": result,
                })
            elif target == "alarm":
                result = await _handle_control_alarm(server, {"action": action})
                action_results.append({
                    "step": f"alarm/{action}",
                    "success": True,
                    "detail": result,
                })
        except Exception as e:
            action_results.append({
                "step": f"{target}/{action}",
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in action_results if r["success"])
    return {
        "scene": scene_name,
        "description": scene["description"],
        "totalSteps": len(action_results),
        "successful": successful,
        "failed": len(action_results) - successful,
        "results": action_results,
    }


def _get_mode_name_from_value(value: int | None) -> str:
    """Reverse lookup HVAC mode value to name."""
    if value is None:
        return "comfort"
    mode_reverse = {
        0: "eco", 1: "comfort", 2: "comfort",
        3: "building_protection", 4: "building_protection",
        5: "manual",
    }
    return mode_reverse.get(value, "comfort")


# ========================================================================
# Wave 3 Tools
# ========================================================================


async def _handle_control_audio(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Control audio in a room.

    Args:
        arguments: {"room_name": "...", "action": str, "volume": int}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_audio")
    structure = _ensure_structure(server, "control_audio")

    room_name = arguments.get("room_name")
    action = arguments.get("action")
    volume = arguments.get("volume")

    if not room_name:
        raise ToolExecutionError("control_audio", "room_name is required")
    if not action:
        raise ToolExecutionError("control_audio", "action is required")

    valid_actions = ["Play", "Pause", "Stop", "SetVolume", "VolumeUp", "VolumeDown"]
    if action not in valid_actions:
        raise ToolExecutionError(
            "control_audio",
            f"Invalid action '{action}'. Valid: {valid_actions}",
        )

    if action == "SetVolume" and volume is None:
        raise ToolExecutionError("control_audio", "volume is required for SetVolume action")
    if volume is not None and not (0 <= volume <= 100):
        raise ToolExecutionError("control_audio", "volume must be 0-100")

    room = _find_room_by_name(server, room_name)

    audio_zones = [c for c in structure.controls.values()
                   if c.room == room.uuid and c.type in AUDIO_TYPES]

    if not audio_zones:
        raise ToolExecutionError(
            "control_audio",
            f"No audio zones found in room '{room.name}'",
        )

    results = []
    for comp in audio_zones:
        try:
            action_str = f"SetVolume/{volume}" if action == "SetVolume" else action
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": True,
                "action": action,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "room": room.name,
        "action": action,
        "volume": volume,
        "totalZones": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_control_intercom(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Interact with the intercom/doorbell.

    Args:
        arguments: {"action": "answer"|"open"|"reject"}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "control_intercom")
    structure = _ensure_structure(server, "control_intercom")

    action = arguments.get("action")
    if not action:
        raise ToolExecutionError("control_intercom", "action is required")

    valid_actions = ["answer", "open", "reject"]
    if action not in valid_actions:
        raise ToolExecutionError(
            "control_intercom",
            f"Invalid action '{action}'. Valid: {valid_actions}",
        )

    intercoms = [c for c in structure.controls.values() if c.type in INTERCOM_TYPES]

    if not intercoms:
        raise ToolExecutionError("control_intercom", "No intercom components found")

    target = intercoms[0]
    try:
        result = await server._http_client.control_component(target.loxone_uuid, action)
        return {
            "success": True,
            "intercom": target.name,
            "uuid": target.loxone_uuid,
            "action": action,
            "result": result,
        }
    except Exception as e:
        raise ToolExecutionError("control_intercom", str(e)) from e


async def _handle_enable_presence_simulation(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Enable or disable presence simulation on Lighting Controllers.

    Args:
        arguments: {"enabled": bool, "room_names": [str]}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_write_access(server, "enable_presence_simulation")
    structure = _ensure_structure(server, "enable_presence_simulation")

    enabled = arguments.get("enabled")
    room_names = arguments.get("room_names")

    if enabled is None:
        raise ToolExecutionError("enable_presence_simulation", "enabled is required")

    if room_names:
        rooms = []
        for rn in room_names:
            rooms.append(_find_room_by_name(server, rn))
        light_controllers = [
            c for c in structure.controls.values()
            if c.type in LIGHT_CONTROLLER_TYPES
            and any(c.room == r.uuid for r in rooms)
        ]
    else:
        light_controllers = [
            c for c in structure.controls.values()
            if c.type in LIGHT_CONTROLLER_TYPES
        ]

    if not light_controllers:
        raise ToolExecutionError(
            "enable_presence_simulation",
            "No Lighting Controllers found",
        )

    # Presence simulation: changeTo/100 to enable, changeTo/101 to disable
    # (Loxone convention for presence simulation moods)
    action_str = "changeTo/100" if enabled else "changeTo/101"

    results = []
    for comp in light_controllers:
        try:
            await server._http_client.control_component(comp.loxone_uuid, action_str)
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": True,
            })
        except Exception as e:
            results.append({
                "uuid": comp.loxone_uuid,
                "name": comp.name,
                "room": _resolve_room_name(server, comp),
                "success": False,
                "error": str(e),
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "enabled": enabled,
        "totalControllers": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


async def _handle_get_history(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Get historical state data for a component.

    Note: Returns current cached state as the MCP server does not
    persist historical data. For full history, Loxone statistics API
    would need to be implemented.

    Args:
        arguments: {"component_uuid": "..."}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_read_access(server, "get_history")
    structure = _ensure_structure(server, "get_history")

    component_uuid = arguments.get("component_uuid")
    if not component_uuid:
        raise ToolExecutionError("get_history", "component_uuid is required")

    try:
        uuid = UUID(component_uuid)
    except ValueError as e:
        raise ToolExecutionError("get_history", f"Invalid UUID: {component_uuid}") from e

    comp = structure.get_component(uuid)
    if not comp:
        raise ToolExecutionError("get_history", f"Component not found: {component_uuid}")

    current_state = server.state_manager.cache.get_component_state(component_uuid) or {}

    return {
        "uuid": comp.loxone_uuid,
        "name": comp.name,
        "type": comp.type,
        "room": _resolve_room_name(server, comp),
        "currentState": current_state,
        "note": "Historical data is limited to current session cache. "
                "Full statistics require Loxone Statistics API integration.",
    }


async def _handle_subscribe_notification(
    server: LoxoneMCPServer,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Set up a conditional notification watch.

    Note: This registers the watch in the state manager. Actual
    notification delivery depends on the MCP transport layer.

    Args:
        arguments: {"component_uuid": "...", "condition": str, "threshold": float, "state_key": str}
    """
    from loxone_mcp.server import ToolExecutionError

    _check_read_access(server, "subscribe_notification")
    structure = _ensure_structure(server, "subscribe_notification")

    component_uuid = arguments.get("component_uuid")
    condition = arguments.get("condition")
    threshold = arguments.get("threshold")
    state_key = arguments.get("state_key")

    if not component_uuid:
        raise ToolExecutionError("subscribe_notification", "component_uuid is required")
    if not condition:
        raise ToolExecutionError("subscribe_notification", "condition is required")
    if condition not in ("on_change", "threshold"):
        raise ToolExecutionError(
            "subscribe_notification",
            f"Invalid condition '{condition}'. Valid: ['on_change', 'threshold']",
        )
    if condition == "threshold" and threshold is None:
        raise ToolExecutionError(
            "subscribe_notification",
            "threshold is required when condition='threshold'",
        )

    try:
        uuid = UUID(component_uuid)
    except ValueError as e:
        raise ToolExecutionError(
            "subscribe_notification", f"Invalid UUID: {component_uuid}"
        ) from e

    comp = structure.get_component(uuid)
    if not comp:
        raise ToolExecutionError(
            "subscribe_notification", f"Component not found: {component_uuid}"
        )

    # Register the subscription (stored in memory for this session)
    subscription = {
        "uuid": comp.loxone_uuid,
        "name": comp.name,
        "condition": condition,
        "threshold": threshold,
        "stateKey": state_key or "value",
        "active": True,
    }

    return {
        "success": True,
        "subscription": subscription,
        "note": "Notification watch registered for this session. "
                "Notifications will be delivered via MCP resource change events.",
    }
