# MCP Resources Contract

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**MCP Version**: 2025-06-18

This document defines all MCP Resources exposed by the Loxone MCP server.

## Overview

Resources are read-only data endpoints that MCP clients can query to retrieve information about the Loxone system. All resources return JSON-formatted data.

## Resource List

### 1. Structure File Resource

**URI**: `loxone://structure`  
**Name**: Loxone Structure File  
**Description**: Complete Loxone miniserver configuration including all components, rooms, and categories  
**MIME Type**: `application/json`

**Response Schema**:
```json
{
  "type": "object",
  "properties": {
    "lastModified": {
      "type": "string",
      "format": "date-time",
      "description": "Last modification timestamp from Loxone"
    },
    "msInfo": {
      "type": "object",
      "properties": {
        "serialNumber": {"type": "string"},
        "msName": {"type": "string"},
        "projectName": {"type": "string"},
        "localUrl": {"type": "string"},
        "remoteUrl": {"type": "string"},
        "firmwareVersion": {"type": "string"}
      }
    },
    "controls": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/Component"
      },
      "description": "All components indexed by UUID"
    },
    "rooms": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/Room"
      }
    },
    "categories": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/Category"
      }
    }
  },
  "definitions": {
    "Component": {
      "type": "object",
      "properties": {
        "uuid": {"type": "string", "format": "uuid"},
        "name": {"type": "string"},
        "type": {"type": "string"},
        "room": {"type": "string", "format": "uuid"},
        "category": {"type": "string", "format": "uuid"},
        "state": {"type": "object"},
        "capabilities": {"type": "array", "items": {"type": "string"}},
        "lastUpdated": {"type": "string", "format": "date-time"}
      },
      "required": ["uuid", "name", "type", "room", "category", "state"]
    },
    "Room": {
      "type": "object",
      "properties": {
        "uuid": {"type": "string", "format": "uuid"},
        "name": {"type": "string"},
        "type": {"type": "integer"},
        "image": {"type": "string", "nullable": true}
      },
      "required": ["uuid", "name", "type"]
    },
    "Category": {
      "type": "object",
      "properties": {
        "uuid": {"type": "string", "format": "uuid"},
        "name": {"type": "string"},
        "type": {"type": "string"},
        "image": {"type": "string", "nullable": true}
      },
      "required": ["uuid", "name", "type"]
    }
  }
}
```

**Example Response**:
```json
{
  "lastModified": "2026-02-10T14:30:00Z",
  "msInfo": {
    "serialNumber": "504F12345678",
    "msName": "Loxone Miniserver",
    "projectName": "My Smart Home",
    "firmwareVersion": "13.2.8.24"
  },
  "controls": {
    "0f1e2c44-0004-1a2b-ffff403fb0c34b9e": {
      "uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
      "name": "Living Room Light",
      "type": "LightController",
      "room": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
      "category": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
      "state": {
        "active": 1,
        "value": 75.5
      },
      "capabilities": ["On", "Off", "Dim"],
      "lastUpdated": "2026-02-10T14:32:15Z"
    }
  },
  "rooms": {
    "0f1e2c44-0000-1111-ffff403fb0c34b9e": {
      "uuid": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
      "name": "Living Room",
      "type": 1
    }
  },
  "categories": {
    "0f1e2c44-0000-2222-ffff403fb0c34b9e": {
      "uuid": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
      "name": "Lights",
      "type": "lights"
    }
  }
}
```

**Cache Behavior**: Cached for 1 hour (configurable), invalidated on WebSocket reconnect

---

### 2. Components List Resource

**URI**: `loxone://components`  
**Name**: Components List  
**Description**: List of all controllable components in the Loxone system  
**MIME Type**: `application/json`

**Response Schema**:
```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "uuid": {"type": "string", "format": "uuid"},
      "name": {"type": "string"},
      "type": {"type": "string"},
      "room": {"type": "string", "format": "uuid"},
      "roomName": {"type": "string"},
      "category": {"type": "string", "format": "uuid"},
      "categoryName": {"type": "string"},
      "state": {"type": "object"},
      "capabilities": {"type": "array", "items": {"type": "string"}},
      "lastUpdated": {"type": "string", "format": "date-time"}
    },
    "required": ["uuid", "name", "type", "state"]
  }
}
```

**Example Response**:
```json
[
  {
    "uuid": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
    "name": "Living Room Light",
    "type": "LightController",
    "room": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
    "roomName": "Living Room",
    "category": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
    "categoryName": "Lights",
    "state": {
      "active": 1,
      "value": 75.5
    },
    "capabilities": ["On", "Off", "Dim"],
    "lastUpdated": "2026-02-10T14:32:15Z"
  },
  {
    "uuid": "0f1e2c44-0005-1a2b-ffff403fb0c34b9e",
    "name": "Kitchen Blind",
    "type": "Jalousie",
    "room": "0f1e2c44-0000-3333-ffff403fb0c34b9e",
    "roomName": "Kitchen",
    "category": "0f1e2c44-0000-4444-ffff403fb0c34b9e",
    "categoryName": "Shading",
    "state": {
      "position": 50,
      "shade": 0
    },
    "capabilities": ["Up", "Down", "FullUp", "FullDown", "Shade"],
    "lastUpdated": "2026-02-10T14:31:00Z"
  }
]
```

**Cache Behavior**: Derived from structure file cache

---

### 3. Rooms List Resource

**URI**: `loxone://rooms`  
**Name**: Rooms List  
**Description**: List of all rooms in the Loxone system  
**MIME Type**: `application/json`

**Response Schema**:
```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "uuid": {"type": "string", "format": "uuid"},
      "name": {"type": "string"},
      "type": {"type": "integer"},
      "typeName": {"type": "string"},
      "image": {"type": "string", "nullable": true},
      "componentCount": {"type": "integer"}
    },
    "required": ["uuid", "name", "type", "componentCount"]
  }
}
```

**Room Type Mapping**:
- `0`: Generic
- `1`: Bathroom
- `2`: Bedroom
- `3`: Kitchen
- `4`: Living Room
- `5`: Office
- `6`: Garage

**Example Response**:
```json
[
  {
    "uuid": "0f1e2c44-0000-1111-ffff403fb0c34b9e",
    "name": "Living Room",
    "type": 4,
    "typeName": "Living Room",
    "componentCount": 8
  },
  {
    "uuid": "0f1e2c44-0000-3333-ffff403fb0c34b9e",
    "name": "Kitchen",
    "type": 3,
    "typeName": "Kitchen",
    "componentCount": 5
  }
]
```

**Cache Behavior**: Derived from structure file cache

---

### 4. Categories List Resource

**URI**: `loxone://categories`  
**Name**: Categories List  
**Description**: List of all component categories in the Loxone system  
**MIME Type**: `application/json`

**Response Schema**:
```json
{
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "uuid": {"type": "string", "format": "uuid"},
      "name": {"type": "string"},
      "type": {"type": "string"},
      "image": {"type": "string", "nullable": true},
      "componentCount": {"type": "integer"}
    },
    "required": ["uuid", "name", "type", "componentCount"]
  }
}
```

**Example Response**:
```json
[
  {
    "uuid": "0f1e2c44-0000-2222-ffff403fb0c34b9e",
    "name": "Lights",
    "type": "lights",
    "componentCount": 15
  },
  {
    "uuid": "0f1e2c44-0000-4444-ffff403fb0c34b9e",
    "name": "Shading",
    "type": "shading",
    "componentCount": 8
  }
]
```

**Cache Behavior**: Derived from structure file cache

---

## MCP Notifications

When component states change (via WebSocket updates), the server sends MCP notifications:

**Method**: `notifications/resources/updated`  
**Params**:
```json
{
  "uri": "loxone://components"
}
```

Clients should re-fetch the updated resource after receiving this notification.

---

## Access Control

All resources respect the server's `AccessControlConfig.mode`:

- **read-only**: Resources accessible ✅
- **write-only**: Resources return `403 Forbidden` ❌
- **read-write**: Resources accessible ✅

---

## Error Responses

**Structure File Not Available**:
```json
{
  "error": {
    "code": "STRUCTURE_NOT_LOADED",
    "message": "Structure file not yet loaded from Loxone miniserver",
    "details": "Retry in a few seconds"
  }
}
```

**Access Denied**:
```json
{
  "error": {
    "code": "ACCESS_DENIED",
    "message": "Server is in write-only mode",
    "details": "Resource reads are disabled"
  }
}
```

---

**Contract Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Complete
