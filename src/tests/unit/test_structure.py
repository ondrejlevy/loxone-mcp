"""Unit tests for Loxone structure file parser (structure.py).

Tests parsing of structure files, rooms, categories, and controls.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loxone_mcp.loxone.structure import (
    _parse_categories,
    _parse_controls,
    _parse_rooms,
    parse_structure_file,
)
from tests.fixtures.loxone_responses import load_structure_file


class TestParseStructureFile:
    def test_parse_full_structure(self) -> None:
        data = load_structure_file()
        structure = parse_structure_file(data)
        assert len(structure.controls) > 0
        assert len(structure.rooms) > 0
        assert len(structure.categories) > 0

    def test_parse_empty_structure(self) -> None:
        data: dict[str, Any] = {}
        structure = parse_structure_file(data)
        assert len(structure.controls) == 0
        assert len(structure.rooms) == 0
        assert len(structure.categories) == 0

    def test_version_from_ms_info(self) -> None:
        data = {"msInfo": {"swVersion": "13.0.1.2"}}
        structure = parse_structure_file(data)
        assert structure.version == "13.0.1.2"

    def test_version_missing(self) -> None:
        data: dict[str, Any] = {}
        structure = parse_structure_file(data)
        assert structure.version == "unknown"

    def test_last_modified(self) -> None:
        data = {"lastModified": "2024-01-15"}
        structure = parse_structure_file(data)
        assert structure.last_modified == "2024-01-15"


class TestParseRooms:
    def test_parse_valid_rooms(self) -> None:
        raw = {
            "0f5e3a01-0288-1b0a-ffff504f9412ab34": {
                "name": "Living Room",
                "type": 1,
                "image": "room.png",
                "defaultRating": 5,
            }
        }
        rooms = _parse_rooms(raw)
        assert len(rooms) == 1
        room = rooms[UUID("0f5e3a01-0288-1b0a-ffff504f9412ab34")]
        assert room.name == "Living Room"
        assert room.type == 1
        assert room.image == "room.png"
        assert room.default_rating == 5

    def test_parse_room_defaults(self) -> None:
        raw = {"0f5e3a01-0288-1b0a-ffff504f9412ab34": {}}
        rooms = _parse_rooms(raw)
        room = rooms[UUID("0f5e3a01-0288-1b0a-ffff504f9412ab34")]
        assert room.name == "Unknown"
        assert room.type == 0

    def test_parse_invalid_uuid_skipped(self) -> None:
        raw = {"not-a-uuid": {"name": "Bad Room"}}
        rooms = _parse_rooms(raw)
        assert len(rooms) == 0


class TestParseCategories:
    def test_parse_valid_categories(self) -> None:
        raw = {
            "0f5e3a01-0300-1b0a-ffff504f9412ab34": {
                "name": "Lighting",
                "type": "lights",
                "image": "cat.png",
                "defaultRating": 3,
            }
        }
        cats = _parse_categories(raw)
        assert len(cats) == 1
        cat = cats[UUID("0f5e3a01-0300-1b0a-ffff504f9412ab34")]
        assert cat.name == "Lighting"
        assert cat.type == "lights"

    def test_parse_invalid_uuid_skipped(self) -> None:
        raw = {"not-valid": {"name": "Bad"}}
        cats = _parse_categories(raw)
        assert len(cats) == 0


class TestParseControls:
    def test_parse_valid_control(self) -> None:
        raw = {
            "0f5e3a01-0100-1b0a-ffff504f9412ab34": {
                "name": "Main Light",
                "type": "LightController",
                "room": "0f5e3a01-0288-1b0a-ffff504f9412ab34",
                "cat": "0f5e3a01-0300-1b0a-ffff504f9412ab34",
                "states": {"active": "0f5e3a01-0200-1b0a-ffff504f9412ab34"},
                "defaultRating": 5,
                "isSecured": True,
                "uuidAction": "action-uuid",
                "details": {"key": "value"},
                "subControls": {"sub1": {}},
            }
        }
        controls = _parse_controls(raw)
        assert len(controls) == 1
        comp = controls[UUID("0f5e3a01-0100-1b0a-ffff504f9412ab34")]
        assert comp.name == "Main Light"
        assert comp.type == "LightController"
        assert comp.capabilities == ["changeTo/0", "changeTo/99", "plus", "changeTo"]
        assert comp.is_secured is True
        assert comp.uuid_action == "action-uuid"

    def test_parse_control_without_room(self) -> None:
        raw = {
            "0f5e3a01-0100-1b0a-ffff504f9412ab34": {
                "name": "Orphan",
                "type": "Switch",
            }
        }
        controls = _parse_controls(raw)
        comp = controls[UUID("0f5e3a01-0100-1b0a-ffff504f9412ab34")]
        assert comp.room == UUID(int=0)

    def test_parse_invalid_uuid_skipped(self) -> None:
        raw = {"bad-uuid": {"name": "Bad", "type": "Switch"}}
        controls = _parse_controls(raw)
        assert len(controls) == 0
