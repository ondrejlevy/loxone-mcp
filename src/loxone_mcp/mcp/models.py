"""MCP domain models for Resources, Tools, and Notifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResourceMimeType(str, Enum):
    """Supported MIME types for MCP Resources."""

    JSON = "application/json"
    TEXT = "text/plain"


@dataclass
class MCPResource:
    """MCP Resource definition."""

    uri: str
    name: str
    description: str
    mime_type: ResourceMimeType = ResourceMimeType.JSON


@dataclass
class MCPTool:
    """MCP Tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPNotification:
    """MCP notification to send to clients."""

    method: str  # e.g., "notifications/resources/updated"
    params: dict[str, Any] = field(default_factory=dict)


# --- Predefined Resources ---

RESOURCES = [
    MCPResource(
        uri="loxone://structure",
        name="Loxone Structure File",
        description=(
            "Complete Loxone miniserver configuration including "
            "all components, rooms, and categories"
        ),
    ),
    MCPResource(
        uri="loxone://components",
        name="Components List",
        description=(
            "List of all controllable components with enriched data "
            "(room name, category name, current state)"
        ),
    ),
    MCPResource(
        uri="loxone://rooms",
        name="Rooms List",
        description="List of all rooms with component counts",
    ),
    MCPResource(
        uri="loxone://categories",
        name="Categories List",
        description="List of all component categories with component counts",
    ),
]

# --- Predefined Tools ---

TOOLS = [
    MCPTool(
        name="get_component_state",
        description="Get the current state of a specific Loxone component by UUID",
        input_schema={
            "type": "object",
            "properties": {
                "component_uuid": {
                    "type": "string",
                    "description": "UUID of the component to query",
                },
            },
            "required": ["component_uuid"],
        },
    ),
    MCPTool(
        name="control_component",
        description="Send a control command to a Loxone component",
        input_schema={
            "type": "object",
            "properties": {
                "component_uuid": {
                    "type": "string",
                    "description": "UUID of the component to control",
                },
                "action": {
                    "type": "string",
                    "description": "Action to perform (e.g., On, Off, Dim, FullUp)",
                },
                "params": {
                    "type": "object",
                    "description": "Optional parameters for the action",
                    "default": {},
                },
            },
            "required": ["component_uuid", "action"],
        },
    ),
    MCPTool(
        name="get_room_components",
        description="Get all components in a specific room with their current states",
        input_schema={
            "type": "object",
            "properties": {
                "room_uuid": {
                    "type": "string",
                    "description": "UUID of the room to query",
                },
            },
            "required": ["room_uuid"],
        },
    ),
    MCPTool(
        name="get_components_by_type",
        description="Get all components of a specific type with their current states",
        input_schema={
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "description": (
                        "Component type to filter by "
                        "(e.g., LightController, Switch, Jalousie)"
                    ),
                },
            },
            "required": ["component_type"],
        },
    ),
]
