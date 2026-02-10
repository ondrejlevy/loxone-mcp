"""Loxone structure file parser.

Parses the LoxAPP3.json structure file into domain models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from loxone_mcp.loxone.models import (
    Category,
    Component,
    Room,
    StructureFile,
    get_capabilities,
)

logger = structlog.get_logger()


def parse_structure_file(data: dict[str, Any]) -> StructureFile:
    """Parse raw Loxone structure file JSON into domain models.

    Args:
        data: Raw JSON dict from LoxAPP3.json

    Returns:
        StructureFile with parsed components, rooms, and categories
    """
    rooms = _parse_rooms(data.get("rooms", {}))
    categories = _parse_categories(data.get("cats", {}))
    controls = _parse_controls(data.get("controls", {}))

    structure = StructureFile(
        last_modified=data.get("lastModified", ""),
        ms_info=data.get("msInfo", {}),
        controls=controls,
        rooms=rooms,
        categories=categories,
        loaded_at=datetime.now(),
    )

    logger.info(
        "structure_file_parsed",
        components=len(controls),
        rooms=len(rooms),
        categories=len(categories),
        version=structure.version,
    )

    return structure


def _parse_rooms(raw_rooms: dict[str, Any]) -> dict[UUID, Room]:
    """Parse rooms from structure file."""
    rooms: dict[UUID, Room] = {}
    for uuid_str, room_data in raw_rooms.items():
        try:
            uuid = UUID(uuid_str)
            rooms[uuid] = Room(
                uuid=uuid,
                name=room_data.get("name", "Unknown"),
                type=room_data.get("type", 0),
                image=room_data.get("image"),
                default_rating=room_data.get("defaultRating", 0),
            )
        except (ValueError, KeyError) as e:
            logger.warning("room_parse_error", uuid=uuid_str, error=str(e))
    return rooms


def _parse_categories(raw_cats: dict[str, Any]) -> dict[UUID, Category]:
    """Parse categories from structure file."""
    categories: dict[UUID, Category] = {}
    for uuid_str, cat_data in raw_cats.items():
        try:
            uuid = UUID(uuid_str)
            categories[uuid] = Category(
                uuid=uuid,
                name=cat_data.get("name", "Unknown"),
                type=cat_data.get("type", ""),
                image=cat_data.get("image"),
                default_rating=cat_data.get("defaultRating", 0),
            )
        except (ValueError, KeyError) as e:
            logger.warning("category_parse_error", uuid=uuid_str, error=str(e))
    return categories


def _parse_controls(raw_controls: dict[str, Any]) -> dict[UUID, Component]:
    """Parse controls (components) from structure file."""
    controls: dict[UUID, Component] = {}
    for uuid_str, ctrl_data in raw_controls.items():
        try:
            uuid = UUID(uuid_str)
            component_type = ctrl_data.get("type", "Unknown")
            room_uuid = UUID(ctrl_data["room"]) if "room" in ctrl_data else UUID(int=0)
            cat_uuid = UUID(ctrl_data["cat"]) if "cat" in ctrl_data else UUID(int=0)

            controls[uuid] = Component(
                uuid=uuid,
                name=ctrl_data.get("name", "Unknown"),
                type=component_type,
                room=room_uuid,
                category=cat_uuid,
                states=ctrl_data.get("states", {}),
                capabilities=get_capabilities(component_type),
                default_rating=ctrl_data.get("defaultRating", 0),
                is_secured=ctrl_data.get("isSecured", False),
                uuid_action=ctrl_data.get("uuidAction"),
                details=ctrl_data.get("details", {}),
                sub_controls=ctrl_data.get("subControls", {}),
            )
        except (ValueError, KeyError) as e:
            logger.warning("control_parse_error", uuid=uuid_str, error=str(e))
    return controls
