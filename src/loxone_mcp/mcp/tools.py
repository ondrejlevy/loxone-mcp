"""MCP Tool handlers for Loxone operations.

Implements Tools:
- get_component_state    - Query a specific component's state
- control_component      - Send control commands to components
- get_room_components    - Get all components in a room
- get_components_by_type - Get all components of a given type
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from mcp.types import TextContent, Tool

from loxone_mcp.config import AccessMode
from loxone_mcp.loxone.models import COMPONENT_ACTIONS

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
                        "description": "Optional parameters (e.g., {\"value\": 50} for dimming)",
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
    }

    handler = handlers.get(name)
    if not handler:
        raise ToolNotFoundError(name)

    # Metrics instrumentation (T054)
    from loxone_mcp.metrics.collector import record_request, track_request_duration

    # Audit logging (T061, T063)
    from loxone_mcp.audit.logger import EventType, log_event

    import time as _time

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
        "uuid": str(comp.uuid),
        "name": comp.name,
        "type": comp.type,
        "room": str(comp.room),
        "roomName": room_name,
        "category": str(comp.category),
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

    # Execute via HTTP client (T037)
    try:
        result = await server._http_client.control_component(component_uuid, action_str)
        logger.info(
            "component_controlled",
            uuid=component_uuid,
            action=action,
            params=params,
        )
        return {
            "success": True,
            "uuid": component_uuid,
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
        current_state = server.state_manager.cache.get_component_state(str(comp.uuid)) or {}
        result_components.append({
            "uuid": str(comp.uuid),
            "name": comp.name,
            "type": comp.type,
            "currentState": current_state,
            "capabilities": comp.capabilities,
        })

    return {
        "room": {
            "uuid": str(room.uuid),
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
        current_state = server.state_manager.cache.get_component_state(str(comp.uuid)) or {}

        # Resolve room name
        room_name = ""
        if comp.room and comp.room in structure.rooms:
            room_name = structure.rooms[comp.room].name

        result_components.append({
            "uuid": str(comp.uuid),
            "name": comp.name,
            "type": comp.type,
            "room": str(comp.room),
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
