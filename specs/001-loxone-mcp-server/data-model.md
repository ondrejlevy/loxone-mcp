# Data Model: Loxone MCP Server

**Date**: 2026-02-10  
**Phase**: Phase 1 - Design  
**Status**: Complete

This document defines all data structures, state management strategies, and domain models for the Loxone MCP server.

## 1. Loxone Domain Models

### 1.1 Component

Represents a controllable device or sensor in the Loxone system.

```python
from dataclasses import dataclass
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime

@dataclass
class Component:
    """Loxone component (light, sensor, switch, etc.)"""
    uuid: UUID
    name: str
    type: str  # e.g., "LightController", "Switch", "EIBDimmer"
    room: UUID  # Reference to Room
    category: UUID  # Reference to Category
    state: Dict[str, Any]  # Current state values
    capabilities: list[str]  # e.g., ["On", "Off", "Dim"]
    last_updated: datetime
    
    # Optional metadata
    default_rating: int = 0  # Star rating
    is_secured: bool = False  # Requires authentication
    uuidAction: Optional[str] = None  # Command UUID
```

**State Structure Examples**:
```python
# Light component
state = {
    "active": 1,  # On/Off (0 or 1)
    "value": 75.5  # Dimmer value (0-100%)
}

# Temperature sensor
state = {
    "value": 21.5,  # Temperature in °C
    "outdoor": 15.2
}

# Blind/Shutter
state = {
    "position": 45,  # Position 0-100%
    "shade": 0  # Shade position
}
```

### 1.2 Room

Represents a physical room containing components.

```python
@dataclass
class Room:
    """Loxone room"""
    uuid: UUID
    name: str
    type: int  # Room type (0=generic, 1=bathroom, 2=bedroom, etc.)
    image: Optional[str] = None  # Image path
    default_rating: int = 0
    
    # Not stored, computed on demand
    @property
    def components(self) -> list[Component]:
        """Get all components in this room"""
        pass
```

### 1.3 Category

Represents a functional category of components.

```python
@dataclass
class Category:
    """Loxone category"""
    uuid: UUID
    name: str
    type: str  # e.g., "lights", "shading", "heating"
    image: Optional[str] = None
    default_rating: int = 0
    
    @property
    def components(self) -> list[Component]:
        """Get all components in this category"""
        pass
```

### 1.4 StructureFile

Represents the complete Loxone miniserver configuration.

```python
from typing import Dict

@dataclass
class StructureFile:
    """Complete Loxone structure file"""
    last_modified: datetime
    ms_info: Dict[str, Any]  # Miniserver info (serial, version, etc.)
    controls: Dict[UUID, Component]  # All components indexed by UUID
    rooms: Dict[UUID, Room]  # All rooms
    categories: Dict[UUID, Category]  # All categories
    
    # Metadata
    version: str  # Structure file format version
    loaded_at: datetime
    
    def get_component(self, uuid: UUID) -> Optional[Component]:
        """Get component by UUID"""
        return self.controls.get(uuid)
    
    def get_components_by_room(self, room_uuid: UUID) -> list[Component]:
        """Get all components in a room"""
        return [c for c in self.controls.values() if c.room == room_uuid]
    
    def get_components_by_type(self, component_type: str) -> list[Component]:
        """Get all components of a specific type"""
        return [c for c in self.controls.values() if c.type == component_type]
```

## 2. MCP Domain Models

### 2.1 MCPResource

Represents an MCP Resource exposed to clients.

```python
from enum import Enum

class ResourceMimeType(Enum):
    """Supported MIME types for MCP Resources"""
    JSON = "application/json"
    TEXT = "text/plain"

@dataclass
class MCPResource:
    """MCP Resource definition"""
    uri: str  # e.g., "loxone://structure"
    name: str
    description: str
    mime_type: ResourceMimeType
    metadata: Dict[str, Any] = None
    
    # Handler function (set at registration)
    handler: Optional[callable] = None

# Predefined resources
RESOURCES = [
    MCPResource(
        uri="loxone://structure",
        name="Loxone Structure File",
        description="Complete Loxone miniserver configuration including all components, rooms, and categories",
        mime_type=ResourceMimeType.JSON
    ),
    MCPResource(
        uri="loxone://components",
        name="Components List",
        description="List of all controllable components in the Loxone system",
        mime_type=ResourceMimeType.JSON
    ),
    M CPResource(
        uri="loxone://rooms",
        name="Rooms List",
        description="List of all rooms in the Loxone system",
        mime_type=ResourceMimeType.JSON
    ),
    MCPResource(
        uri="loxone://categories",
        name="Categories List",
        description="List of all component categories in the Loxone system",
        mime_type=ResourceMimeType.JSON
    ),
]
```

### 2.2 MCPTool

Represents an MCP Tool (executable action).

```python
from pydantic import BaseModel

class ToolInputSchema(BaseModel):
    """Base class for Tool input schemas"""
    pass

@dataclass
class MCPTool:
    """MCP Tool definition"""
    name: str
    description: str
    input_schema: type[ToolInputSchema]  # Pydantic model
    
    # Handler function (set at registration)
    handler: Optional[callable] = None

# Example input schemas
class GetComponentStateInput(ToolInputSchema):
    component_uuid: str  # UUID as string

class ControlComponentInput(ToolInputSchema):
    component_uuid: str
    action: str  # e.g., "On", "Off", "Dim"
    params: Optional[Dict[str, Any]] = None

class GetRoomComponentsInput(ToolInputSchema):
    room_uuid: str

class GetComponentsByTypeInput(ToolInputSchema):
    component_type: str  # e.g., "LightController"
```

### 2.3 MCPNotification

Represents an MCP notification sent to clients.

```python
from enum import Enum

class NotificationType(Enum):
    """Types of MCP notifications"""
    RESOURCE_UPDATED = "resources/updated"
    RESOURCE_LIST_CHANGED = "resources/list_changed"

@dataclass
class MCPNotification:
    """MCP notification"""
    method: NotificationType
    params: Dict[str, Any]
    
    @staticmethod
    def resource_updated(uri: str) -> "MCPNotification":
        """Create a resource updated notification"""
        return MCPNotification(
            method=NotificationType.RESOURCE_UPDATED,
            params={"uri": uri}
        )

# Example usage:
# notification = MCPNotification.resource_updated("loxone://components")
# await server.request_context.session.send_resource_updated("loxone://components")
```

## 3. Configuration Models

Using Pydantic for configuration validation.

### 3.1 ServerConfig

```python
from pydantic import BaseModel, Field, validator
from typing import Literal

class ServerConfig(BaseModel):
    """MCP server configuration"""
    name: str = "loxone-mcp"
    version: str = "1.0.0"
    host: str = Field(default="0.0.0.0", description="Host to bind to")
    port: int = Field(default=8080, ge=1024, le=65535, description="HTTP port")
    transport: Literal["stdio", "http", "both"] = Field(default="http")
    
    class Config:
        frozen = True  # Immutable after creation
```

### 3.2 LoxoneConfig

```python
from pydantic import BaseModel, Field, SecretStr

class LoxoneConfig(BaseModel):
    """Loxone miniserver configuration"""
    host: str = Field(..., description="Loxone miniserver hostname or IP")
    port: int = Field(default=80, ge=1, le=65535)
    use_tls: bool = Field(default=False, description="Use HTTPS/WSS")
    username: str
    password: SecretStr  # Securely handles password (not logged)
    
    # Connection settings
    reconnect_interval: int = Field(default=5, ge=1, description="Reconnect delay in seconds")
    max_reconnect_attempts: int = Field(default=10, ge=1)
    
    # Timeouts
    connection_timeout: int = Field(default=10, ge=1, description="Connection timeout in seconds")
    command_timeout: int = Field(default=30, ge=1, description="Command response timeout")
    
    @validator("host")
    def validate_host(cls, v):
        if not v or v.isspace():
            raise ValueError("Host cannot be empty")
        return v
    
    class Config:
        frozen = True
```

### 3.3 AccessControlConfig

```python
from enum import Enum

class AccessMode(Enum):
    """Server access control mode"""
    READ_ONLY = "read-only"  # Only Resource reads, no Tool calls
    WRITE_ONLY = "write-only"  # Only Tool calls, no Resource reads (unusual)
    READ_WRITE = "read-write"  # Full access (default)

class AccessControlConfig(BaseModel):
    """Access control configuration"""
    mode: AccessMode = Field(default=AccessMode.READ_WRITE)
    
    def can_read_resources(self) -> bool:
        return self.mode in [AccessMode.READ_ONLY, AccessMode.READ_WRITE]
    
    def can_call_tools(self) -> bool:
        return self.mode in [AccessMode.WRITE_ONLY, AccessMode.READ_WRITE]
    
    class Config:
        frozen = True
```

### 3.4 MetricsConfig

```python
class MetricsConfig(BaseModel):
    """Metrics configuration"""
    enabled: bool = Field(default=True)
    endpoint: str = Field(default="/metrics", pattern=r"^/.*")
    include_loxone_metrics: bool = Field(default=True, description="Include Loxone-specific metrics")
    
    class Config:
        frozen = True
```

### 3.5 AuditConfig

```python
from pathlib import Path

class AuditConfig(BaseModel):
    """Audit logging configuration"""
    enabled: bool = Field(default=True)
    log_file: Path = Field(default=Path("logs/audit.jsonl"))
    retention_days: int = Field(default=90, ge=1, description="Log retention period")
    log_authentication: bool = Field(default=True)
    log_control_commands: bool = Field(default=True)
    log_config_changes: bool = Field(default=True)
    
    class Config:
        frozen = True
```

### 3.6 RootConfig

```python
class Config(BaseModel):
    """Root configuration"""
    server: ServerConfig
    loxone: LoxoneConfig
    access_control: AccessControlConfig = AccessControlConfig()
    metrics: MetricsConfig = MetricsConfig()
    audit: AuditConfig = AuditConfig()
    
    # Cache settings
    structure_cache_ttl: int = Field(default=3600, ge=60, description="Structure file cache TTL in seconds")
    
    class Config:
        frozen = True
    
    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        """Load configuration from YAML file"""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls(
            server=ServerConfig(
                host=os.getenv("MCP_HOST", "0.0.0.0"),
                port=int(os.getenv("MCP_PORT", "8080")),
                transport=os.getenv("MCP_TRANSPORT", "http"),
            ),
            loxone=LoxoneConfig(
                host=os.getenv("LOXONE_HOST"),
                port=int(os.getenv("LOXONE_PORT", "80")),
                use_tls=os.getenv("LOXONE_USE_TLS", "false").lower() == "true",
                username=os.getenv("LOXONE_USERNAME"),
                password=os.getenv("LOXONE_PASSWORD"),
            ),
            access_control=AccessControlConfig(
                mode=AccessMode(os.getenv("ACCESS_MODE", "read-write"))
            ),
        )
```

## 4. State Management

### 4.1 StateCache

```python
from threading import Lock
from typing import Optional, Dict, Any

class StateCache:
    """Thread-safe in-memory cache for Loxone state"""
    
    def __init__(self, ttl: int = 3600):
        self._structure: Optional[StructureFile] = None
        self._component_states: Dict[UUID, Dict[str, Any]] = {}
        self._ttl = ttl
        self._last_structure_load: Optional[datetime] = None
        self._lock = Lock()
    
    def set_structure(self, structure: StructureFile) -> None:
        """Cache structure file"""
        with self._lock:
            self._structure = structure
            self._last_structure_load = datetime.now()
    
    def get_structure(self) -> Optional[StructureFile]:
        """Get cached structure file (None if expired)"""
        with self._lock:
            if self._structure and self._is_structure_valid():
                return self._structure
            return None
    
    def _is_structure_valid(self) -> bool:
        """Check if cached structure is still valid"""
        if not self._last_structure_load:
            return False
        age = (datetime.now() - self._last_structure_load).total_seconds()
        return age < self._ttl
    
    def update_component_state(self, uuid: UUID, state: Dict[str, Any]) -> None:
        """Update component state (real-time from WebSocket)"""
        with self._lock:
            self._component_states[uuid] = {
                **state,
                "last_updated": datetime.now()
            }
            
            # Also update in structure if loaded
            if self._structure and uuid in self._structure.controls:
                self._structure.controls[uuid].state = state
                self._structure.controls[uuid].last_updated = datetime.now()
    
    def get_component_state(self, uuid: UUID) -> Optional[Dict[str, Any]]:
        """Get component state"""
        with self._lock:
            return self._component_states.get(uuid)
    
    def invalidate_structure(self) -> None:
        """Force structure reload"""
        with self._lock:
            self._structure = None
            self._last_structure_load = None
    
    def clear(self) -> None:
        """Clear all cached data"""
        with self._lock:
            self._structure = None
            self._component_states.clear()
            self._last_structure_load = None
```

### 4.2 Cache Strategy

**Structure File**:
- **Source**: HTTP GET `/jdev/sps/LoxAPP3.json`
- **Cache Duration**: 1 hour (configurable via `structure_cache_ttl`)
- **Invalidation**: Automatic on TTL expiry, manual via management endpoint, on WebSocket reconnect

**Component States**:
- **Source**: WebSocket binary updates
- **Cache Duration**: No TTL (real-time)
- **Update Method**: Event-driven from WebSocket listener
- **Fallback**: HTTP GET if WebSocket unavailable

### 4.3 Notification Flow

```text
Loxone WebSocket
    │
    │ (binary state update)
    ▼
WebSocketHandler
    │
    │ parse_state_update()
    ▼
StateManager
    │
    │ update_component_state()
    ▼
StateCache
    │
    │ (state updated)
    ▼
MCPNotificationSender
    │
    │ send_resource_updated("loxone://components")
    ▼
MCP Clients (receive notification)
```

## 5. Metrics Models

```python
from prometheus_client import Counter, Histogram, Gauge

class Metrics:
    """Prometheus metrics collector"""
    
    # MCP metrics
    mcp_requests_total = Counter(
        "mcp_requests_total",
        "Total MCP requests",
        ["method", "status"]  # labels
    )
    
    mcp_request_duration = Histogram(
        "mcp_request_duration_seconds",
        "MCP request duration",
        ["method"]
    )
    
    mcp_active_connections = Gauge(
        "mcp_active_connections",
        "Number of active MCP client connections"
    )
    
    # Loxone metrics
    loxone_websocket_connected = Gauge(
        "loxone_websocket_connected",
        "Loxone WebSocket connection status (1=connected, 0=disconnected)"
    )
    
    loxone_auth_attempts_total = Counter(
        "loxone_auth_attempts_total",
        "Loxone authentication attempts",
        ["method", "status"]  # method: token/hash, status: success/failure
    )
    
    loxone_api_duration = Histogram(
        "loxone_api_duration_seconds",
        "Loxone API call duration",
        ["endpoint"]
    )
    
    loxone_state_updates_total = Counter(
        "loxone_state_updates_total",
        "Total Loxone state updates received"
    )
    
    # Cache metrics
    structure_cache_hits = Counter(
        "structure_cache_hits_total",
        "Structure file cache hits"
    )
    
    structure_cache_misses = Counter(
        "structure_cache_misses_total",
        "Structure file cache misses"
    )
    
    cache_size_bytes = Gauge(
        "cache_size_bytes",
        "Approximate cache size in bytes"
    )
```

## 6. Audit Models

```python
from enum import Enum

class AuditEventType(Enum):
    """Types of audit events"""
    AUTH_SUCCESS = "authentication_success"
    AUTH_FAILURE = "authentication_failure"
    CONTROL_COMMAND = "component_control"
    CONFIG_CHANGE = "configuration_change"
    ACCESS_DENIED = "access_denied"

@dataclass
class AuditEntry:
    """Audit log entry"""
    timestamp: datetime
    event_type: AuditEventType
    user: Optional[str]  # MCP client identifier
    source_ip: Optional[str]
    success: bool
    details: Dict[str, Any]
    
    def to_json(self) -> str:
        """Serialize to JSON for logging"""
        import json
        return json.dumps({
            "timestamp": self.timestamp.isoformat(),
            "event": self.event_type.value,
            "user": self.user,
            "source_ip": self.source_ip,
            "success": self.success,
            **self.details
        })
```

## Summary

### Model Count
- **Loxone Domain**: 4 models (Component, Room, Category, StructureFile)
- **MCP Domain**: 3 models (MCPResource, MCPTool, MCPNotification)
- **Configuration**: 6 models (ServerConfig, LoxoneConfig, AccessControlConfig, MetricsConfig, AuditConfig, RootConfig)
- **State Management**: 1 class (StateCache)
- **Metrics**: 1 class (Metrics)
- **Audit**: 2 models (AuditEventType, AuditEntry)

**Total**: 17 models/classes

### Validation Rules
- All configuration uses Pydantic validators
- UUIDs validated on parsing
- State updates schema-validated before caching
- Audit entries include all required fields

### Relationships
```text
StructureFile
    ├── contains many Components
    ├── contains many Rooms
    └── contains many Categories

Component
    ├── belongs to one Room
    └── belongs to one Category

StateCache
    ├── stores one StructureFile
    └── stores many Component states

MCPResource/MCPTool
    └── access StateCache for data
```

---

**Data Model Version**: 1.0  
**Last Updated**: 2026-02-10  
**Status**: Complete - Ready for contracts
