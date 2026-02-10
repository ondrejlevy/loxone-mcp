"""Configuration management for Loxone MCP Server.

Supports loading from YAML files and environment variables.
Uses Pydantic for validation with sensible defaults.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger()


class AccessMode(str, Enum):
    """Access control mode for MCP operations."""

    READ_WRITE = "read-write"
    READ_ONLY = "read-only"
    WRITE_ONLY = "write-only"


class TransportType(str, Enum):
    """Supported MCP transport types."""

    HTTP = "http"
    STDIO = "stdio"
    BOTH = "both"


class ServerConfig(BaseModel):
    """MCP server configuration."""

    host: str = Field(default="0.0.0.0", description="Server bind address")  # noqa: S104
    port: int = Field(default=8080, ge=1, le=65535, description="Server port")
    transport: TransportType = Field(default=TransportType.HTTP, description="Transport type")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Enable debug mode")
    tls_cert: str | None = Field(default=None, description="Path to TLS certificate file")
    tls_key: str | None = Field(default=None, description="Path to TLS private key file")


class LoxoneConfig(BaseModel):
    """Loxone miniserver connection configuration."""

    host: str = Field(description="Miniserver IP or hostname")
    port: int = Field(default=80, ge=1, le=65535, description="Miniserver port")
    username: str = Field(description="Loxone username")
    password: str = Field(description="Loxone password")
    use_tls: bool = Field(default=False, description="Use TLS for connections")

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            msg = "Loxone host must not be empty"
            raise ValueError(msg)
        return v.strip()


class AccessControlConfig(BaseModel):
    """Access control configuration."""

    mode: AccessMode = Field(
        default=AccessMode.READ_WRITE,
        description="Access mode: read-write, read-only, or write-only",
    )


class MetricsConfig(BaseModel):
    """Prometheus metrics configuration."""

    enabled: bool = Field(default=True, description="Enable metrics collection")
    endpoint: str = Field(default="/metrics", description="Metrics endpoint path")


class AuditConfig(BaseModel):
    """Audit logging configuration."""

    enabled: bool = Field(default=True, description="Enable audit logging")
    log_file: str = Field(default="logs/audit.jsonl", description="Audit log file path")
    retention_days: int = Field(
        default=90,
        ge=1,
        le=365,
        description="Days to retain audit logs",
    )


class StructureCacheConfig(BaseModel):
    """Structure file cache configuration."""

    ttl_seconds: int = Field(
        default=3600,
        ge=60,
        description="Cache TTL in seconds (default: 1 hour)",
    )
    change_detection_interval: int = Field(
        default=300,
        ge=30,
        description="Interval in seconds to poll for structure changes (default: 5 min)",
    )


class RootConfig(BaseModel):
    """Root application configuration combining all subsections."""

    server: ServerConfig = Field(default_factory=ServerConfig)
    loxone: LoxoneConfig
    access_control: AccessControlConfig = Field(default_factory=AccessControlConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    structure_cache: StructureCacheConfig = Field(default_factory=StructureCacheConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> RootConfig:
        """Load configuration from a YAML file."""
        config_path = Path(path)
        if not config_path.exists():
            msg = f"Configuration file not found: {config_path}"
            raise FileNotFoundError(msg)

        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            msg = f"Invalid configuration file format: {config_path}"
            raise ValueError(msg)

        return cls.model_validate(data)

    @classmethod
    def from_env(cls) -> RootConfig:
        """Load configuration from environment variables.

        Environment variable mapping:
            LOXONE_HOST -> loxone.host
            LOXONE_PORT -> loxone.port
            LOXONE_USERNAME -> loxone.username
            LOXONE_PASSWORD -> loxone.password
            LOXONE_USE_TLS -> loxone.use_tls
            LOXONE_ACCESS_MODE -> access_control.mode
            MCP_HOST -> server.host
            MCP_PORT -> server.port
            MCP_TRANSPORT -> server.transport
            MCP_LOG_LEVEL -> server.log_level
            MCP_DEBUG -> server.debug
            METRICS_ENABLED -> metrics.enabled
            AUDIT_ENABLED -> audit.enabled
            AUDIT_LOG_FILE -> audit.log_file
            AUDIT_RETENTION_DAYS -> audit.retention_days
            STRUCTURE_CACHE_TTL -> structure_cache.ttl_seconds
            STRUCTURE_CHANGE_INTERVAL -> structure_cache.change_detection_interval
        """
        data: dict[str, Any] = {}

        # Collect all validation errors for fail-fast reporting
        errors: list[str] = []

        # Loxone config (required)
        loxone_host = os.environ.get("LOXONE_HOST")
        if not loxone_host:
            errors.append("LOXONE_HOST environment variable is required")

        loxone_username = os.environ.get("LOXONE_USERNAME", "")
        if not loxone_username:
            errors.append("LOXONE_USERNAME environment variable is required")

        loxone_password = os.environ.get("LOXONE_PASSWORD", "")
        if not loxone_password:
            errors.append("LOXONE_PASSWORD environment variable is required")

        # Validate numeric env vars
        loxone_port_str = os.environ.get("LOXONE_PORT", "80")
        try:
            loxone_port = int(loxone_port_str)
            if loxone_port < 1 or loxone_port > 65535:
                errors.append(f"LOXONE_PORT must be between 1 and 65535, got {loxone_port}")
        except ValueError:
            errors.append(f"LOXONE_PORT must be an integer, got '{loxone_port_str}'")
            loxone_port = 80

        mcp_port_str = os.environ.get("MCP_PORT", "8080")
        try:
            mcp_port = int(mcp_port_str)
            if mcp_port < 1 or mcp_port > 65535:
                errors.append(f"MCP_PORT must be between 1 and 65535, got {mcp_port}")
        except ValueError:
            errors.append(f"MCP_PORT must be an integer, got '{mcp_port_str}'")
            mcp_port = 8080

        # Validate enum values
        mcp_transport = os.environ.get("MCP_TRANSPORT")
        if mcp_transport and mcp_transport not in ("http", "stdio", "both"):
            errors.append(
                f"MCP_TRANSPORT must be 'http', 'stdio', or 'both', got '{mcp_transport}'"
            )

        access_mode = os.environ.get("LOXONE_ACCESS_MODE")
        if access_mode and access_mode not in ("read-write", "read-only", "write-only"):
            errors.append(
                f"LOXONE_ACCESS_MODE must be 'read-write', 'read-only', or 'write-only', "
                f"got '{access_mode}'"
            )

        # Fail fast with all errors
        if errors:
            msg = "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            raise ValueError(msg)

        data["loxone"] = {
            "host": loxone_host,
            "port": loxone_port,
            "username": loxone_username,
            "password": loxone_password,
            "use_tls": os.environ.get("LOXONE_USE_TLS", "false").lower() == "true",
        }

        # Server config
        server: dict[str, Any] = {}
        if mcp_host := os.environ.get("MCP_HOST"):
            server["host"] = mcp_host
        if os.environ.get("MCP_PORT"):
            server["port"] = mcp_port
        if mcp_transport:
            server["transport"] = mcp_transport
        if mcp_log_level := os.environ.get("MCP_LOG_LEVEL"):
            server["log_level"] = mcp_log_level
        if mcp_debug := os.environ.get("MCP_DEBUG"):
            server["debug"] = mcp_debug.lower() == "true"
        if tls_cert := os.environ.get("MCP_TLS_CERT"):
            server["tls_cert"] = tls_cert
        if tls_key := os.environ.get("MCP_TLS_KEY"):
            server["tls_key"] = tls_key
        if server:
            data["server"] = server

        # Access control
        if access_mode:
            data["access_control"] = {"mode": access_mode}

        # Metrics
        metrics: dict[str, Any] = {}
        if metrics_enabled := os.environ.get("METRICS_ENABLED"):
            metrics["enabled"] = metrics_enabled.lower() == "true"
        if metrics:
            data["metrics"] = metrics

        # Audit
        audit: dict[str, Any] = {}
        if audit_enabled := os.environ.get("AUDIT_ENABLED"):
            audit["enabled"] = audit_enabled.lower() == "true"
        if audit_log_file := os.environ.get("AUDIT_LOG_FILE"):
            audit["log_file"] = audit_log_file
        if audit_retention := os.environ.get("AUDIT_RETENTION_DAYS"):
            audit["retention_days"] = int(audit_retention)
        if audit:
            data["audit"] = audit

        # Structure cache
        cache: dict[str, Any] = {}
        if cache_ttl := os.environ.get("STRUCTURE_CACHE_TTL"):
            cache["ttl_seconds"] = int(cache_ttl)
        if change_interval := os.environ.get("STRUCTURE_CHANGE_INTERVAL"):
            cache["change_detection_interval"] = int(change_interval)
        if cache:
            data["structure_cache"] = cache

        return cls.model_validate(data)


# --- Structured Logging Setup ---


def _redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Redact sensitive fields from log entries."""
    sensitive_keys = {"password", "token", "secret", "key", "authorization"}
    for key in list(event_dict.keys()):
        if any(s in key.lower() for s in sensitive_keys):
            value = event_dict[key]
            if isinstance(value, str) and len(value) > 8:
                event_dict[key] = value[:8] + "***REDACTED***"
            else:
                event_dict[key] = "***REDACTED***"
    return event_dict


def setup_logging(log_level: str = "INFO", debug: bool = False) -> None:
    """Configure structured logging with structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        debug: Enable debug mode with human-readable output
    """
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_sensitive,
    ]

    if debug:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.stdlib._NAME_TO_LEVEL.get(log_level.upper(), 20)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
