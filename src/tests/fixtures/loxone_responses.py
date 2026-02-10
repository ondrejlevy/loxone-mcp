"""Pytest fixtures for mock Loxone API responses.

Provides reusable test data for structure files, component states,
and WebSocket messages used across unit and integration tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

# Well-known test UUIDs
LIVING_ROOM_UUID = UUID("0f5e3a01-0288-1b0a-ffff504f9412ab34")
KITCHEN_UUID = UUID("0f5e3a01-0289-1b0a-ffff504f9412ab34")
BEDROOM_UUID = UUID("0f5e3a01-028a-1b0a-ffff504f9412ab34")
BATHROOM_UUID = UUID("0f5e3a01-028b-1b0a-ffff504f9412ab34")

LIGHTING_CAT_UUID = UUID("0f5e3a01-0300-1b0a-ffff504f9412ab34")
SHADING_CAT_UUID = UUID("0f5e3a01-0301-1b0a-ffff504f9412ab34")
CLIMATE_CAT_UUID = UUID("0f5e3a01-0302-1b0a-ffff504f9412ab34")

LIGHT_UUID = UUID("0f5e3a01-0100-1b0a-ffff504f9412ab34")
SWITCH_UUID = UUID("0f5e3a01-0101-1b0a-ffff504f9412ab34")
BLINDS_UUID = UUID("0f5e3a01-0102-1b0a-ffff504f9412ab34")
DIMMER_UUID = UUID("0f5e3a01-0103-1b0a-ffff504f9412ab34")
THERMOSTAT_UUID = UUID("0f5e3a01-0104-1b0a-ffff504f9412ab34")

FIXTURES_DIR = Path(__file__).parent


def load_structure_file() -> dict[str, Any]:
    """Load the mock Loxone structure file."""
    path = FIXTURES_DIR / "loxone_structure_file.json"
    with open(path) as f:
        data: dict[str, Any] = json.load(f)
        return data


def make_structure_response() -> dict[str, Any]:
    """Create a mock HTTP response for structure file retrieval."""
    return {
        "LL": {
            "control": "jdev/sps/LoxAPP3.json",
            "value": load_structure_file(),
            "Code": "200",
        }
    }


# --- Component State Responses ---

def make_state_values() -> dict[str, dict[str, Any]]:
    """Create mock component state values as they would appear in cache."""
    return {
        str(LIGHT_UUID): {
            "active": 1,
            "activeMoods": "[778]",
            "moodList": '[{"id":778,"name":"Bright","isUsed":true}]',
        },
        str(SWITCH_UUID): {
            "active": 0,
        },
        str(BLINDS_UUID): {
            "position": 45.0,
            "shade": 0.0,
            "up": 0,
            "down": 0,
        },
        str(DIMMER_UUID): {
            "position": 75.5,
        },
        str(THERMOSTAT_UUID): {
            "tempActual": 21.5,
            "tempTarget": 22.0,
            "mode": 1,
        },
    }


# --- WebSocket Messages ---

def make_ws_text_event(uuid: UUID, value: float) -> str:
    """Create a mock WebSocket text event."""
    return json.dumps({
        "LL": {
            "control": str(uuid),
            "value": value,
            "Code": "200",
        }
    })


def make_ws_keepalive_response() -> str:
    """Create a mock WebSocket keepalive response."""
    return json.dumps({
        "LL": {
            "control": "keepalive",
            "value": "OK",
            "Code": "200",
        }
    })


def make_ws_binary_state_header(msg_type: int, payload_len: int) -> bytes:
    """Create a binary WebSocket state update header.

    Header format (8 bytes):
        - Byte 0: Type indicator (0x03 for state update)
        - Byte 1: Message type identifier
        - Byte 2-3: Reserved/padding
        - Byte 4-7: Payload length (little-endian uint32)
    """
    import struct
    return struct.pack("<BBxx I", 0x03, msg_type, payload_len)


def make_ws_binary_state_value(uuid: UUID, value: float) -> bytes:
    """Create a binary state value entry.

    Entry format (24 bytes):
        - Bytes 0-15: UUID (16 bytes, little-endian)
        - Bytes 16-23: Value (double, little-endian)
    """
    import struct
    uuid_bytes = uuid.bytes
    return uuid_bytes + struct.pack("<d", value)


# --- Authentication Responses ---

def make_getkey_response(public_key: str = "mock-public-key") -> dict[str, Any]:
    """Create a mock response for jdev/sys/getkey2."""
    return {
        "LL": {
            "control": "jdev/sys/getkey2",
            "value": {
                "key": public_key,
                "salt": "a1b2c3d4e5f6",
            },
            "Code": "200",
        }
    }


def make_token_response(
    token: str = "mock-jwt-token-abc123",
    valid_until: int = 1739750400,
) -> dict[str, Any]:
    """Create a mock response for gettoken."""
    return {
        "LL": {
            "control": "jdev/sys/getjwt",
            "value": {
                "token": token,
                "validUntil": valid_until,
                "tokenRights": 2,
                "unsecurePass": False,
            },
            "Code": "200",
        }
    }


def make_hash_response(salt: str = "a1b2c3d4e5f6", hash_alg: str = "SHA1") -> dict[str, Any]:
    """Create a mock response for jdev/sys/getsalt (hash-based auth)."""
    return {
        "LL": {
            "control": "jdev/sys/getsalt",
            "value": {
                "Salt": salt,
                "HashAlg": hash_alg,
            },
            "Code": "200",
        }
    }


# --- Error Responses ---

def make_error_response(code: str = "500", value: str = "Error") -> dict[str, Any]:
    """Create a mock Loxone error response."""
    return {
        "LL": {
            "control": "dev/sps/unknown",
            "value": value,
            "Code": code,
        }
    }


def make_auth_error_response() -> dict[str, Any]:
    """Create a mock authentication failure response."""
    return {
        "LL": {
            "control": "jdev/sys/getjwt",
            "value": "Invalid credentials",
            "Code": "401",
        }
    }
