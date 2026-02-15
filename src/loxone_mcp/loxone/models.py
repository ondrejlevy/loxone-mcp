"""Loxone domain models.

Represents the data structures from the Loxone miniserver:
components, rooms, categories, and the structure file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


def uuid_to_loxone_format(uuid: UUID | str) -> str:
    """Convert a UUID to Loxone's native format (8-4-4-16).

    Loxone uses non-standard UUIDs: xxxxxxxx-xxxx-xxxx-xxxxxxxxxxxxxxxx
    Python's UUID normalizes to:    xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    The Loxone miniserver rejects Python-format UUIDs with 404.
    """
    hex_str = UUID(str(uuid)).hex  # 32 hex chars, no dashes
    return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:]}"


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

    @property
    def loxone_uuid(self) -> str:
        """Return the UUID in Loxone's native format for API commands.

        Prefers uuid_action (original string from structure file).
        Falls back to converting the UUID object to Loxone format.
        """
        return self.uuid_action or uuid_to_loxone_format(self.uuid)


# Supported actions per component type
# LightController types use mood-based commands:
#   changeTo/0  = All Off
#   changeTo/99 = Last active mood (On)
#   plus        = Next mood
LIGHT_CONTROLLER_TYPES: set[str] = {"LightController", "LightControllerV2"}

COMPONENT_ACTIONS: dict[str, list[str]] = {
    "LightController": ["changeTo/0", "changeTo/99", "plus", "changeTo"],
    "LightControllerV2": ["changeTo/0", "changeTo/99", "plus", "changeTo"],
    "Switch": ["On", "Off", "Pulse"],
    "EIBDimmer": ["On", "Off"],
    "Dimmer": ["On", "Off"],
    "Jalousie": ["FullUp", "FullDown", "Up", "Down", "Stop", "Shade", "manualPosition", "manualLamelle"],
    "IRoomControllerV2": [
        "setManualTemperature",
        "setComfortTemperature",
        "setMode",
    ],
    "IRoomController": [
        "setManualTemperature",
        "setComfortTemperature",
        "setMode",
    ],
    "Alarm": ["On", "Off", "delayedon", "quit"],
    "SmokeAlarm": ["mute", "quit"],
    "Gate": ["Open", "Close", "Stop"],
    "AudioZone": ["Play", "Pause", "Stop", "SetVolume", "VolumeUp", "VolumeDown"],
    "Intercom": ["answer", "open", "reject"],
}

# Component types that represent lights (used by light-related tools)
LIGHT_TYPES: set[str] = {
    "LightController",
    "LightControllerV2",
    "EIBDimmer",
    "Dimmer",
    "Switch",  # Switches in "Lighting" category are treated as lights
}

# Component types that provide temperature readings
TEMPERATURE_TYPES: set[str] = {
    "IRoomControllerV2",
    "IRoomController",
    "InfoOnlyAnalog",  # Generic analog sensor - may have temperature
}

# Component types for presence/motion detection
PRESENCE_TYPES: set[str] = {
    "PresenceDetector",
    "MotionSensor",
    "InfoOnlyDigital",  # Generic digital sensor - may be a presence sensor
}

# Component types for window/door sensors
WINDOW_DOOR_TYPES: set[str] = {
    "InfoOnlyDigital",  # Window/door contacts are typically digital sensors
}

# Component types for alarm systems
ALARM_TYPES: set[str] = {
    "Alarm",
    "SmokeAlarm",
}

# Component types for energy monitoring
ENERGY_TYPES: set[str] = {
    "EnergyMonitor",
    "Meter",
    "InfoOnlyAnalog",  # Generic analog - may carry energy data
}

# Component types for blinds/shading
BLIND_TYPES: set[str] = {
    "Jalousie",
    "AutomaticShading",
}

# Component types for audio zones
AUDIO_TYPES: set[str] = {
    "AudioZone",
}

# Component types for intercom/doorbell
INTERCOM_TYPES: set[str] = {
    "Intercom",
}

# HVAC mode constants
HVAC_MODES: dict[str, int] = {
    "economy": 0,
    "comfort_heating": 1,
    "comfort_cooling": 2,
    "empty_house": 3,
    "heat_protection": 4,
    "manual": 5,
    "comfort": 1,  # alias
    "eco": 0,  # alias
    "building_protection": 3,  # alias
    "off": 3,  # alias for empty house/building protection
    "auto": 1,  # alias for comfort
}

# Predefined scenes
PREDEFINED_SCENES: dict[str, dict[str, Any]] = {
    "goodnight": {
        "description": "Good night scene: lights off, blinds down, heating eco, alarm on",
        "actions": [
            {"target": "all_lights", "action": "Off"},
            {"target": "all_blinds", "action": "FullDown"},
            {"target": "all_hvac", "action": "setMode", "value": 0},  # Economy
            {"target": "alarm", "action": "delayedon"},
        ],
    },
    "morning": {
        "description": "Morning routine: blinds up, lights on, heating comfort",
        "actions": [
            {"target": "all_blinds", "action": "FullUp"},
            {"target": "all_lights", "action": "On"},
            {"target": "all_hvac", "action": "setMode", "value": 1},  # Comfort
        ],
    },
    "away": {
        "description": "Leaving home: lights off, alarm on, heating eco",
        "actions": [
            {"target": "all_lights", "action": "Off"},
            {"target": "alarm", "action": "delayedon"},
            {"target": "all_hvac", "action": "setMode", "value": 3},  # Empty house
        ],
    },
    "home": {
        "description": "Arriving home: alarm off, lights on, heating comfort",
        "actions": [
            {"target": "alarm", "action": "Off"},
            {"target": "all_lights", "action": "On"},
            {"target": "all_hvac", "action": "setMode", "value": 1},  # Comfort
        ],
    },
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

    def get_room_by_name(self, name: str) -> Room | None:
        """Find a room by name (case-insensitive)."""
        name_lower = name.lower()
        for room in self.rooms.values():
            if room.name.lower() == name_lower:
                return room
        return None

    def search_rooms(self, query: str) -> list[Room]:
        """Search rooms by partial name match (case-insensitive)."""
        query_lower = query.lower()
        return [r for r in self.rooms.values() if query_lower in r.name.lower()]

    def get_components_by_types(self, type_set: set[str]) -> list[Component]:
        """Get all components matching any of the given types."""
        return [c for c in self.controls.values() if c.type in type_set]

    def get_components_by_room_and_types(
        self, room_uuid: UUID, type_set: set[str]
    ) -> list[Component]:
        """Get components in a room matching any of the given types."""
        return [
            c for c in self.controls.values()
            if c.room == room_uuid and c.type in type_set
        ]

    def get_components_by_category_name(self, category_name: str) -> list[Component]:
        """Get components belonging to a category by name (case-insensitive)."""
        name_lower = category_name.lower()
        matching_cat_uuids = [
            cat.uuid for cat in self.categories.values()
            if cat.name.lower() == name_lower
        ]
        return [
            c for c in self.controls.values()
            if c.category in matching_cat_uuids
        ]
