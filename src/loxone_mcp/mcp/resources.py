"""MCP Resource handlers for Loxone data.

Implements Resources:
- loxone://structure  - Full structure file
- loxone://components - All components with enriched data
- loxone://rooms      - All rooms with component counts
- loxone://categories - All categories with component counts
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import Resource, TextContent

from loxone_mcp.config import AccessMode

if TYPE_CHECKING:
    from loxone_mcp.server import LoxoneMCPServer

logger = structlog.get_logger()


async def get_resource_list(server: LoxoneMCPServer) -> list[Resource]:
    """List all available MCP Resources.

    Used by MCP server's list_resources handler.
    """
    from pydantic import AnyUrl

    return [
        Resource(
            uri=AnyUrl("loxone://structure"),
            name="Loxone Structure File",
            description=(
                "Complete Loxone miniserver configuration including "
                "all components, rooms, and categories"
            ),
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("loxone://components"),
            name="Components List",
            description=(
                "List of all controllable components with enriched data "
                "(room name, category name, current state)"
            ),
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("loxone://rooms"),
            name="Rooms List",
            description="List of all rooms with component counts",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("loxone://categories"),
            name="Categories List",
            description="List of all component categories with component counts",
            mimeType="application/json",
        ),
    ]


async def handle_read_resource(
    server: LoxoneMCPServer,
    uri: str,
) -> list[TextContent]:
    """Read a specific MCP Resource by URI.

    Args:
        server: LoxoneMCPServer instance
        uri: Resource URI (e.g., "loxone://structure")

    Returns:
        List of TextContent with JSON data

    Raises:
        ResourceNotFoundError: If URI is not recognized
    """
    from loxone_mcp.server import AccessDeniedError, ResourceNotFoundError

    # Access control check (T036)
    mode = server.config.access_control.mode
    if mode == AccessMode.WRITE_ONLY:
        # Audit: access denied (T063)
        from loxone_mcp.audit.logger import EventType, log_event

        log_event(
            EventType.ACCESS_DENIED,
            user="unknown",
            action=uri,
            success=False,
            target=uri,
            error_message=f"Server configured in {mode.value} mode",
        )
        raise AccessDeniedError("read resource", mode.value)

    handlers = {
        "loxone://structure": _read_structure,
        "loxone://components": _read_components,
        "loxone://rooms": _read_rooms,
        "loxone://categories": _read_categories,
    }

    handler = handlers.get(uri)
    if not handler:
        raise ResourceNotFoundError(uri)

    # Metrics instrumentation (T053)
    import time as _time

    from loxone_mcp.metrics.collector import record_request, track_request_duration

    start = _time.monotonic()
    with track_request_duration("resources/read"):
        data = await handler(server)
    duration_ms = (_time.monotonic() - start) * 1000

    record_request("resources/read", "success")

    # Audit: resource read (T062)
    from loxone_mcp.audit.logger import EventType, log_event

    log_event(
        EventType.RESOURCE_READ,
        user="unknown",
        action=uri,
        success=True,
        target=uri,
        duration_ms=duration_ms,
    )

    return [TextContent(type="text", text=json.dumps(data, default=str))]


async def _read_structure(server: LoxoneMCPServer) -> dict[str, Any]:
    """Read the full Loxone structure file (T025)."""
    structure = server.state_manager.cache.structure
    if not structure:
        return {"error": "Structure not loaded", "controls": {}, "rooms": {}, "categories": {}}

    return {
        "controls": {
            str(uuid): {
                "uuid": str(comp.uuid),
                "name": comp.name,
                "type": comp.type,
                "room": str(comp.room),
                "category": str(comp.category),
                "states": comp.states,
                "capabilities": comp.capabilities,
                "is_secured": comp.is_secured,
            }
            for uuid, comp in structure.controls.items()
        },
        "rooms": {
            str(uuid): {"uuid": str(room.uuid), "name": room.name, "type": room.type}
            for uuid, room in structure.rooms.items()
        },
        "categories": {
            str(uuid): {"uuid": str(cat.uuid), "name": cat.name, "type": cat.type}
            for uuid, cat in structure.categories.items()
        },
    }


async def _read_components(server: LoxoneMCPServer) -> list[dict[str, Any]]:
    """Read all components with enriched data (T026).

    Enriches each component with:
    - roomName: Resolved room name
    - categoryName: Resolved category name
    - currentState: Live state values from cache
    """
    structure = server.state_manager.cache.structure
    if not structure:
        return []

    components = []
    for uuid, comp in structure.controls.items():
        # Resolve room name
        room_name = ""
        if comp.room and comp.room in structure.rooms:
            room_name = structure.rooms[comp.room].name

        # Resolve category name
        category_name = ""
        if comp.category and comp.category in structure.categories:
            category_name = structure.categories[comp.category].name

        # Get current state from cache
        current_state = server.state_manager.cache.get_component_state(str(uuid)) or {}

        components.append({
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
        })

    return components


async def _read_rooms(server: LoxoneMCPServer) -> list[dict[str, Any]]:
    """Read all rooms with component counts (T027)."""
    structure = server.state_manager.cache.structure
    if not structure:
        return []

    rooms = []
    for uuid, room in structure.rooms.items():
        # Count components in this room
        components = structure.get_components_by_room(uuid)
        rooms.append({
            "uuid": str(room.uuid),
            "name": room.name,
            "type": room.type,
            "componentCount": len(components),
            "components": [
                {"uuid": str(c.uuid), "name": c.name, "type": c.type} for c in components
            ],
        })

    return rooms


async def _read_categories(server: LoxoneMCPServer) -> list[dict[str, Any]]:
    """Read all categories with component counts (T028)."""
    structure = server.state_manager.cache.structure
    if not structure:
        return []

    categories = []
    for uuid, cat in structure.categories.items():
        # Count components in this category
        components = structure.get_components_by_category(uuid)
        categories.append({
            "uuid": str(cat.uuid),
            "name": cat.name,
            "type": cat.type,
            "componentCount": len(components),
            "components": [
                {"uuid": str(c.uuid), "name": c.name, "type": c.type} for c in components
            ],
        })

    return categories
