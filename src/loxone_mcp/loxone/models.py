"""Loxone domain models.

Represents the data structures from the Loxone miniserver:
components, rooms, categories, and the structure file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class Component:
    """Loxone component (light, sensor, switch, etc.)."""

    uuid: UUID
    name: str
    type: str  # e.g., "LightController", "Switch", "EIBDimmer", "Jalousie"
    room: UUID  # Reference to Room UUID
    category: UUID  # Reference to Category UUID
    states: dict[str, str]  # State key -> state UUID path
    state_values: dict[str, Any] = field(default_factory=dict)  # Current state values
    capabilities: list[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)
    default_rating: int = 0
    is_secured: bool = False
    uuid_action: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    sub_controls: dict[str, Any] = field(default_factory=dict)

    @property
    def state_uuids(self) -> list[str]:
        """Get all state UUID paths for this component."""
        return list(self.states.values())


# Supported actions per component type
COMPONENT_ACTIONS: dict[str, list[str]] = {
    "LightController": ["On", "Off"],
    "Switch": ["On", "Off", "Pulse"],
    "EIBDimmer": ["On", "Off"],
    "Jalousie": ["FullUp", "FullDown", "Up", "Down", "Stop", "Shade"],
    "IRoomControllerV2": [
        "setManualTemperature",
        "setComfortTemperature",
        "setMode",
    ],
}


def get_capabilities(component_type: str) -> list[str]:
    """Get supported actions for a component type."""
    return COMPONENT_ACTIONS.get(component_type, [])


@dataclass
class Room:
    """Loxone room."""

    uuid: UUID
    name: str
    type: int = 0  # Room type (0=generic, 1=bathroom, 2=bedroom, etc.)
    image: str | None = None
    default_rating: int = 0


@dataclass
class Category:
    """Loxone category."""

    uuid: UUID
    name: str
    type: str = ""  # e.g., "lights", "shading", "heating"
    image: str | None = None
    default_rating: int = 0


@dataclass
class StructureFile:
    """Complete Loxone structure file."""

    last_modified: str
    ms_info: dict[str, Any]
    controls: dict[UUID, Component]
    rooms: dict[UUID, Room]
    categories: dict[UUID, Category]
    loaded_at: datetime = field(default_factory=datetime.now)

    @property
    def version(self) -> str:
        """Get miniserver firmware version."""
        return str(self.ms_info.get("swVersion", "unknown"))

    def get_component(self, uuid: UUID) -> Component | None:
        """Get component by UUID."""
        return self.controls.get(uuid)

    def get_components_by_room(self, room_uuid: UUID) -> list[Component]:
        """Get all components in a room."""
        return [c for c in self.controls.values() if c.room == room_uuid]

    def get_components_by_type(self, component_type: str) -> list[Component]:
        """Get all components of a specific type."""
        return [c for c in self.controls.values() if c.type == component_type]

    def get_components_by_category(self, category_uuid: UUID) -> list[Component]:
        """Get all components in a category."""
        return [c for c in self.controls.values() if c.category == category_uuid]
