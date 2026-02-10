# Audit Log Schema

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**Purpose**: Defines audit log entry structure to clarify FR-021 requirements

This document specifies the audit log format for security compliance and troubleshooting.

## Audit Entry Format

Audit logs are written in **JSON Lines** format (one JSON object per line) to `logs/audit.jsonl`.

## Schema

```json
{
  "type": "object",
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 timestamp (UTC)"
    },
    "event_type": {
      "type": "string",
      "enum": [
        "AUTH_SUCCESS",
        "AUTH_FAILURE",
        "RESOURCE_READ",
        "TOOL_EXECUTION",
        "ACCESS_DENIED",
        "STRUCTURE_RELOAD",
        "ERROR"
      ],
      "description": "Category of audit event"
    },
    "user": {
      "type": "string",
      "description": "Username from authentication (redacted if auth failed)"
    },
    "source_ip": {
      "type": "string",
      "description": "Client IP address (for remote transports)"
    },
    "action": {
      "type": "string",
      "description": "Specific action: Tool name (control_component), Resource URI (loxone://components), or auth method (token_websocket)"
    },
    "method": {
      "type": "string",
      "nullable": true,
      "description": "Control action for Tool executions: On, Off, Dim, etc. Null for Resource reads."
    },
    "target": {
      "type": "string",
      "nullable": true,
      "description": "Target component UUID or resource identifier"
    },
    "success": {
      "type": "boolean",
      "description": "Operation result"
    },
    "duration_ms": {
      "type": "number",
      "description": "Operation duration in milliseconds"
    },
    "error_message": {
      "type": "string",
      "nullable": true,
      "description": "Error message if success=false"
    },
    "details": {
      "type": "object",
      "description": "Additional context (sanitized to remove sensitive data)"
    }
  },
  "required": [
    "timestamp",
    "event_type",
    "user",
    "action",
    "success"
  ]
}
```

## Event Type Definitions

### AUTH_SUCCESS
- **action**: Authentication method used (`token_websocket`, `token_http`, `hash_legacy`)
- **method**: null
- **target**: null
- **success**: true
- **Example**: User successfully authenticated via token-based WebSocket

### AUTH_FAILURE
- **action**: Attempted authentication method
- **method**: null
- **target**: null
- **success**: false
- **error_message**: Reason for failure
- **Example**: Invalid credentials, token expired

### RESOURCE_READ
- **action**: Resource URI (`loxone://components`, `loxone://structure`, etc.)
- **method**: null
- **target**: Resource URI (duplicate of action for consistency)
- **success**: true/false
- **Example**: AI client queries component list

### TOOL_EXECUTION
- **action**: Tool name (`control_component`, `get_component_state`, `get_room_components`, etc.)
- **method**: Control action for control_component Tool (`On`, `Off`, `Dim`, `FullUp`, etc.), null for query Tools
- **target**: Component UUID for component-specific Tools, room/category UUID for filtered queries
- **success**: true/false
- **Example**: AI executes command to turn on a light

### ACCESS_DENIED
- **action**: Attempted action (Resource URI or Tool name)
- **method**: Control action if applicable
- **target**: Target identifier
- **success**: false
- **error_message**: Reason (e.g., "Server in read-only mode")
- **Example**: Write operation blocked by read-only configuration

### STRUCTURE_RELOAD
- **action**: `structure_reload`
- **method**: null
- **target**: null
- **success**: true/false
- **Example**: Structure file re-fetched after change detection

### ERROR
- **action**: Operation that failed
- **method**: null
- **target**: null
- **success**: false
- **error_message**: Error description
- **Example**: WebSocket disconnection, Loxone API timeout

## Example Audit Entries

### Successful Control Operation
```json
{
  "timestamp": "2026-02-10T14:32:15.342Z",
  "event_type": "TOOL_EXECUTION",
  "user": "ai_assistant",
  "source_ip": "192.168.1.50",
  "action": "control_component",
  "method": "On",
  "target": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "success": true,
  "duration_ms": 157,
  "error_message": null,
  "details": {
    "component_name": "Living Room Light",
    "component_type": "LightController"
  }
}
```

### Failed Authentication
```json
{
  "timestamp": "2026-02-10T14:30:01.123Z",
  "event_type": "AUTH_FAILURE",
  "user": "unknown_user",
  "source_ip": "192.168.1.100",
  "action": "token_websocket",
  "method": null,
  "target": null,
  "success": false,
  "duration_ms": 45,
  "error_message": "Invalid credentials",
  "details": {
    "auth_tier": "token_websocket",
    "fallback_attempted": false
  }
}
```

### Resource Read
```json
{
  "timestamp": "2026-02-10T14:33:22.567Z",
  "event_type": "RESOURCE_READ",
  "user": "ai_assistant",
  "source_ip": "192.168.1.50",
  "action": "loxone://components",
  "method": null,
  "target": "loxone://components",
  "success": true,
  "duration_ms": 12,
  "error_message": null,
  "details": {
    "component_count": 47,
    "cache_hit": true
  }
}
```

### Access Denied (Read-Only Mode)
```json
{
  "timestamp": "2026-02-10T14:35:00.890Z",
  "event_type": "ACCESS_DENIED",
  "user": "ai_assistant",
  "source_ip": "192.168.1.50",
  "action": "control_component",
  "method": "Off",
  "target": "0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
  "success": false,
  "duration_ms": 3,
  "error_message": "Server configured in read-only mode",
  "details": {
    "access_control_mode": "read-only"
  }
}
```

## Sensitive Data Redaction Rules

The following data MUST be redacted before logging:
- **Passwords**: Replace with `***REDACTED***`
- **Full tokens**: Log only first 8 characters + `...` (e.g., `eyJhbGci...`)
- **Encryption keys**: Never log
- **Raw authentication credentials**: Never log plaintext

Safe to log:
- Usernames
- UUIDs
- Operation types
- Timestamps
- IP addresses (in secure environments)
- Error messages (already sanitized by error handler)

## Log Rotation

- **Rotation**: Daily at midnight UTC
- **Format**: `audit-YYYY-MM-DD.jsonl`
- **Retention**: Configurable via `AuditConfig.retention_days` (default: 90 days)
- **Cleanup**: Automatic deletion of logs older than retention period on startup

## Implementation Reference

This schema is implemented in:
- **T059**: Define AuditEntry model in `src/loxone_mcp/audit/logger.py`
- **T060-T063**: Audit logging instrumentation across modules
- **T065**: Sensitive data redaction implementation

## Compliance Notes

This audit log format supports:
- **FR-020**: Generate audit log entries for all operations
- **FR-021**: Record timestamp, username, action type, target component, operation result
- **FR-022**: Record failed authentication attempts
- **FR-023**: Clear error messages for troubleshooting

---

**Version**: 1.0  
**Status**: Complete
