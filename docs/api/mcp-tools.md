# MCP Tools Contract

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**MCP Version**: 2025-06-18

This document defines all MCP Tools exposed by the Loxone MCP server.

## Overview

Tools are executable actions that MCP clients can invoke to control Loxone components or query specific data. All Tools use JSON for input and output.

## Tool List

### 1. Get Component State

**Name**: `get_component_state`  
**Description**: Retrieve the current state of a specific component  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "component_uuid": {
      "type": "string",
      "format": "uuid",
      "description": "UUID of the component"
    }
  },
  "required": ["component_uuid"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "uuid": {"type": "string", "format": "uuid"},
    "name": {"type": "string"},
    "type": {"type": "string"},
    "state": {"type": "object"},
    "lastUpdated": {"type": "string", "format": "date-time"}
  }
}
```

**Example Request**:
```json
{
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e"
}
```

**Example Response**:
```json
{
  "uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "name": "Living Room Light",
  "type": "LightController",
  "state": {
    "active": 1,
    "value": 75.5
  },
  "lastUpdated": "2026-02-10T14:32:15Z"
}
```

**Errors**:
- `COMPONENT_NOT_FOUND`: Component UUID does not exist
- `STATE_UNAVAILABLE`: State not yet received from Loxone

**Performance**: <1s response time (from cache)

---

### 2. Control Component

**Name**: `control_component`  
**Description**: Execute a control command on a component  
**Category**: Action

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "component_uuid": {
      "type": "string",
      "format": "uuid",
      "description": "UUID of the component to control"
    },
    "action": {
      "type": "string",
      "description": "Action to execute (e.g., 'On', 'Off', 'Pulse')",
      "minLength": 1
    },
    "params": {
      "type": "object",
      "description": "Optional parameters for the action",
      "additionalProperties": true
    }
  },
  "required": ["component_uuid", "action"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "success": {"type": "boolean"},
    "component_uuid": {"type": "string", "format": "uuid"},
    "action": {"type": "string"},
    "executionTime": {"type": "number", "description": "Execution time in milliseconds"},
    "newState": {
      "type": "object",
      "description": "State after action (if immediately available)"
    }
  },
  "required": ["success", "component_uuid", "action"]
}
```

**Common Actions by Component Type**:

**LightController**:
- `On`: Turn light on
- `Off`: Turn light off
- `Dim`: Set dimmer value (requires `params.value` 0-100)

**Switch**:
- `On`: Turn on
- `Off`: Turn off
- `Pulse`: Momentary pulse

**Jalousie (Blind/Shutter)**:
- `FullUp`: Move to fully open
- `FullDown`: Move to fully closed
- `Up`: Move up (continuous)
- `Down`: Move down (continuous)
- `Stop`: Stop movement
- `Shade`: Move to shade position (requires `params.position` 0-100)

**IRoomControllerV2 (Climate)**:
- `setManualTemperature`: Set target temperature (requires `params.temperature`)
- `setComfortTemperature`: Switch to comfort mode
- `setMode`: Set operating mode (requires `params.mode`)

**Example Request (Turn on light)**:
```json
{
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "action": "On"
}
```

**Example Response**:
```json
{
  "success": true,
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "action": "On",
  "executionTime": 152,
  "newState": {
    "active": 1,
    "value": 100
  }
}
```

**Example Request (Dim light)**:
```json
{
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "action": "Dim",
  "params": {
    "value": 50
  }
}
```

**Example Response**:
```json
{
  "success": true,
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "action": "Dim",
  "executionTime": 187,
  "newState": {
    "active": 1,
    "value": 50
  }
}
```

**Errors**:
- `COMPONENT_NOT_FOUND`: Component UUID does not exist
- `ACTION_NOT_SUPPORTED`: Action not valid for this component type
- `INVALID_PARAMS`: Required parameters missing or invalid
- `EXECUTION_FAILED`: Loxone API returned error
- `ACCESS_DENIED`: Server is in read-only mode

**Performance**: <2s execution time (including Loxone response)

---

### 3. Get Room Components

**Name**: `get_room_components`  
**Description**: Retrieve all components in a specific room  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_uuid": {
      "type": "string",
      "format": "uuid",
      "description": "UUID of the room"
    }
  },
  "required": ["room_uuid"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "room": {
      "type": "object",
      "properties": {
        "uuid": {"type": "string"},
        "name": {"type": "string"}
      }
    },
    "components": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "uuid": {"type": "string"},
          "name": {"type": "string"},
          "type": {"type": "string"},
          "state": {"type": "object"},
          "capabilities": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "count": {"type": "integer"}
  }
}
```

**Example Request**:
```json
{
  "room_uuid": "0f1e2c44-0000-1111-ffff403fb0c34b9e"
}
```

**Example Response**:
```json
{
  "room": {
    "uuid": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
    "name": "Living Room"
  },
  "components": [
    {
      "uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
      "name": "Living Room Light",
      "type": "LightController",
      "state": {
        "active": 1,
        "value": 75.5
      },
      "capabilities": ["On", "Off", "Dim"]
    },
    {
      "uuid": "0f1e2c44-0005-1a2b-ffff403fb0c34b9e",
      "name": "Living Room Blind",
      "type": "Jalousie",
      "state": {
        "position": 30
      },
      "capabilities": ["FullUp", "FullDown", "Up", "Down", "Stop"]
    }
  ],
  "count": 2
}
```

**Errors**:
- `ROOM_NOT_FOUND`: Room UUID does not exist

**Performance**: <1s response time (from cache)

---

### 4. Get Components by Type

**Name**: `get_components_by_type`  
**Description**: Retrieve all components of a specific type  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "component_type": {
      "type": "string",
      "description": "Component type (e.g., 'LightController', 'Jalousie')",
      "minLength": 1
    }
  },
  "required": ["component_type"]
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "componentType": {"type": "string"},
    "components": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "uuid": {"type": "string"},
          "name": {"type": "string"},
          "room": {"type": "string"},
          "roomName": {"type": "string"},
          "state": {"type": "object"},
          "capabilities": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "count": {"type": "integer"}
  }
}
```

**Example Request**:
```json
{
  "component_type": "LightController"
}
```

**Example Response**:
```json
{
  "componentType": "LightController",
  "components": [
    {
      "uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
      "name": "Living Room Light",
      "room": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
      "roomName": "Living Room",
      "state": {
        "active": 1,
        "value": 75.5
      },
      "capabilities": ["On", "Off", "Dim"]
    },
    {
      "uuid": "0f1e2c44-0009-1a2b-ffff403fb0c34b9e",
      "name": "Kitchen Light",
      "room": "0f1e2c44-0000-3333-ffff403fb0c34b9e",
      "roomName": "Kitchen",
      "state": {
        "active": 0,
        "value": 0
      },
      "capabilities": ["On", "Off", "Dim"]
    }
  ],
  "count": 2
}
```

**Common Component Types**:
- `LightController`: Lights with dimming
- `Switch`: Simple on/off switches
- `Jalousie`: Blinds/shutters
- `EIBDimmer`: EIB/KNX dimmers
- `IRoomControllerV2`: Climate control
- `Pushbutton`: Buttons/triggers
- `UpDownAnalog`: Analog up/down controls

**Errors**:
- `NO_COMPONENTS_FOUND`: No components of this type exist

**Performance**: <1s response time (from cache)

---

## Access Control

All tools respect the server's `AccessControlConfig.mode`:

- **read-only**: Only query tools accessible (get_component_state, get_room_components, get_components_by_type) ✅, control_component returns `403 Forbidden` ❌
- **write-only**: Only control_component accessible ✅, query tools return `403 Forbidden` ❌
- **read-write**: All tools accessible ✅

---

## Audit Logging

All Tool executions are logged to the audit log:

```json
{
  "timestamp": "2026-02-10T14:32:01.123Z",
  "event": "component_control_executed",
  "user": "ai_assistant_client_abc123",
  "component_uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "action": "On",
  "success": true,
  "duration_ms": 152
}
```

Failed executions are also logged with error details.

---

## Error Response Format

All errors follow consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": "Additional context or suggestions"
  }
}
```

---

**Contract Version**: 2.0  
**Last Updated**: 2026-02-10  
**Status**: Complete

### 5. List Rooms

**Name**: `list_rooms`  
**Description**: List all rooms in the Loxone smart home with UUIDs, names, and component counts  
**Category**: Query

**Input Schema**: No required parameters

**Example Response**:
```json
{
  "roomCount": 4,
  "rooms": [
    {"uuid": "...", "name": "Living Room", "type": 1, "componentCount": 5},
    {"uuid": "...", "name": "Kitchen", "type": 0, "componentCount": 2}
  ]
}
```

---

### 6. Get Room by Name

**Name**: `get_room_by_name`  
**Description**: Find a room by name (case-insensitive, partial match) and return details with all components  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string", "description": "Room name or partial name"}
  },
  "required": ["room_name"]
}
```

**Example Request**: `{"room_name": "Living"}`

**Example Response**:
```json
{
  "room": {"uuid": "...", "name": "Living Room", "type": 1},
  "componentCount": 5,
  "components": [
    {"uuid": "...", "name": "Living Room Light", "type": "LightController", "currentState": {"active": 1}, "capabilities": ["On", "Off"]}
  ]
}
```

---

### 7. Get Lights Status

**Name**: `get_lights_status`  
**Description**: Get light status across the home or filtered by room name  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string", "description": "Optional room name filter"}
  }
}
```

**Example Response**:
```json
{
  "totalLights": 6,
  "lightsOn": 2,
  "lightsOff": 4,
  "room": "all",
  "lights": [
    {"uuid": "...", "name": "Living Room Light", "type": "LightController", "room": "Living Room", "isOn": true, "brightness": 75.5}
  ]
}
```

---

### 8. Control Room Lights

**Name**: `control_room_lights`  
**Description**: Turn all lights in a specific room on or off  
**Category**: Action

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string"},
    "action": {"type": "string", "enum": ["On", "Off"]}
  },
  "required": ["room_name", "action"]
}
```

**Example Request**: `{"room_name": "Kitchen", "action": "Off"}`

**Example Response**:
```json
{
  "room": "Kitchen",
  "action": "Off",
  "totalLights": 2,
  "successful": 2,
  "failed": 0,
  "results": [{"uuid": "...", "name": "Kitchen Light", "success": true}]
}
```

---

### 9. Get Temperatures

**Name**: `get_temperatures`  
**Description**: Get temperature readings from all rooms or a specific room  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string", "description": "Optional room name filter"}
  }
}
```

**Example Response**:
```json
{
  "sensorCount": 3,
  "room": "all",
  "temperatures": [
    {"uuid": "...", "name": "Bathroom Thermostat", "type": "IRoomControllerV2", "room": "Bathroom", "actualTemperature": 21.5, "targetTemperature": 22.0, "mode": 1, "modeText": "Comfort heating"}
  ]
}
```

---

### 10. Get Presence Status

**Name**: `get_presence_status`  
**Description**: Get motion/presence detection status across all rooms or a specific room  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string", "description": "Optional room name filter"}
  }
}
```

**Example Response**:
```json
{
  "sensorCount": 2,
  "room": "all",
  "roomsWithPresence": ["Living Room"],
  "presenceDetected": true,
  "sensors": [
    {"uuid": "...", "name": "Living Room Presence", "room": "Living Room", "isActive": true}
  ]
}
```

---

### 11. Get Window/Door Status

**Name**: `get_window_door_status`  
**Description**: Get open/closed status of all windows and doors  
**Category**: Query

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "room_name": {"type": "string", "description": "Optional room name filter"}
  }
}
```

**Example Response**:
```json
{
  "sensorCount": 4,
  "room": "all",
  "openCount": 1,
  "closedCount": 3,
  "allClosed": false,
  "openItems": [{"name": "Living Room Window", "room": "Living Room"}],
  "sensors": [{"uuid": "...", "name": "Living Room Window", "room": "Living Room", "isOpen": true}]
}
```

---

### 12. Get Alarm Status

**Name**: `get_alarm_status`  
**Description**: Get the current status of all alarm/security systems  
**Category**: Query

**Input Schema**: No required parameters

**Example Response**:
```json
{
  "alarmCount": 1,
  "anyArmed": false,
  "anyTriggered": false,
  "alarms": [
    {"uuid": "...", "name": "Home Alarm", "type": "Alarm", "isArmed": false, "alarmLevel": 0, "isTriggered": false}
  ]
}
```

---

### 13. Control Alarm

**Name**: `control_alarm`  
**Description**: Arm or disarm the home security/alarm system  
**Category**: Action

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "alarm_name": {"type": "string", "description": "Optional alarm name"},
    "action": {"type": "string", "enum": ["On", "Off", "delayedon", "quit"]}
  },
  "required": ["action"]
}
```

**Actions**:
- `On`: Arm immediately
- `Off`: Disarm
- `delayedon`: Arm with entry delay
- `quit`: Acknowledge/silence alarm

---

### 14. Get Energy Status

**Name**: `get_energy_status`  
**Description**: Get energy consumption, production, and battery status  
**Category**: Query

**Input Schema**: No required parameters

**Example Response**:
```json
{
  "componentCount": 3,
  "summary": {
    "gridConsumption": 2450.5,
    "solarProduction": 3200.0,
    "batteryLevel": 78.5
  },
  "components": [
    {"uuid": "...", "name": "Grid Power Consumption", "type": "InfoOnlyAnalog", "category": "grid_consumption", "currentState": {"value": 2450.5}}
  ]
}
```
