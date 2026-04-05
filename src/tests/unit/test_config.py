"""Unit tests for configuration management (config.py).

Tests YAML loading, environment variable loading, validation,
logging setup, and sensitive data redaction.
"""

from __future__ import annotations

import os
import textwrap
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from loxone_mcp.config import (
    AccessControlConfig,
    AccessMode,
    AuditConfig,
    LoxoneConfig,
    MetricsConfig,
    RootConfig,
    ServerConfig,
    StructureCacheConfig,
    TransportType,
    _redact_sensitive,
    setup_logging,
)

# --- Enum Tests ---


class TestEnums:
    def test_access_mode_values(self) -> None:
        assert AccessMode.READ_WRITE.value == "read-write"
        assert AccessMode.READ_ONLY.value == "read-only"
        assert AccessMode.WRITE_ONLY.value == "write-only"

    def test_transport_type_values(self) -> None:
        assert TransportType.HTTP.value == "http"
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.BOTH.value == "both"


# --- Model Defaults ---


class TestServerConfig:
    def test_defaults(self) -> None:
        cfg = ServerConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8080
        assert cfg.transport == TransportType.HTTP
        assert cfg.log_level == "INFO"
        assert cfg.debug is False
        assert cfg.tls_cert is None
        assert cfg.tls_key is None

    def test_custom_values(self) -> None:
        cfg = ServerConfig(host="127.0.0.1", port=9090, transport=TransportType.BOTH, debug=True)
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9090
        assert cfg.transport == TransportType.BOTH
        assert cfg.debug is True

    def test_port_range_validation(self) -> None:
        with pytest.raises(ValueError):
            ServerConfig(port=0)
        with pytest.raises(ValueError):
            ServerConfig(port=70000)


class TestLoxoneConfig:
    def test_valid_config(self) -> None:
        cfg = LoxoneConfig(host="192.168.1.1", username="user", password="pass")
        assert cfg.host == "192.168.1.1"
        assert cfg.port == 80
        assert cfg.use_tls is False

    def test_empty_host_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            LoxoneConfig(host="", username="user", password="pass")

    def test_whitespace_host_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            LoxoneConfig(host="   ", username="user", password="pass")

    def test_host_stripped(self) -> None:
        cfg = LoxoneConfig(host="  192.168.1.1  ", username="user", password="pass")
        assert cfg.host == "192.168.1.1"


class TestOtherConfigs:
    def test_access_control_default(self) -> None:
        cfg = AccessControlConfig()
        assert cfg.mode == AccessMode.READ_WRITE

    def test_metrics_default(self) -> None:
        cfg = MetricsConfig()
        assert cfg.enabled is True
        assert cfg.endpoint == "/metrics"

    def test_audit_default(self) -> None:
        cfg = AuditConfig()
        assert cfg.enabled is True
        assert cfg.retention_days == 90

    def test_structure_cache_default(self) -> None:
        cfg = StructureCacheConfig()
        assert cfg.ttl_seconds == 3600
        assert cfg.change_detection_interval == 300


# --- YAML Loading ---


class TestRootConfigFromYaml:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            loxone:
              host: 192.168.1.100
              port: 80
              username: testuser
              password: testpass
            server:
              port: 9090
              debug: true
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        cfg = RootConfig.from_yaml(config_file)
        assert cfg.loxone.host == "192.168.1.100"
        assert cfg.server.port == 9090
        assert cfg.server.debug is True

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            RootConfig.from_yaml("/nonexistent/config.yaml")

    def test_invalid_yaml_format(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("just a string")
        with pytest.raises(ValueError, match="Invalid configuration"):
            RootConfig.from_yaml(config_file)


# --- Environment Variable Loading ---


class TestRootConfigFromEnv:
    def test_load_minimal_env(self) -> None:
        env = {
            "LOXONE_HOST": "192.168.1.100",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RootConfig.from_env()
        assert cfg.loxone.host == "192.168.1.100"
        assert cfg.loxone.username == "user"

    def test_missing_host_raises(self) -> None:
        env = {"LOXONE_USERNAME": "user", "LOXONE_PASSWORD": "pass"}
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="LOXONE_HOST"),
        ):
            RootConfig.from_env()

    def test_missing_username_raises(self) -> None:
        env = {"LOXONE_HOST": "host", "LOXONE_PASSWORD": "pass"}
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="LOXONE_USERNAME"),
        ):
            RootConfig.from_env()

    def test_missing_password_raises(self) -> None:
        env = {"LOXONE_HOST": "host", "LOXONE_USERNAME": "user"}
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="LOXONE_PASSWORD"),
        ):
            RootConfig.from_env()

    def test_invalid_loxone_port(self) -> None:
        env = {
            "LOXONE_HOST": "host",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
            "LOXONE_PORT": "abc",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="LOXONE_PORT must be an integer"),
        ):
            RootConfig.from_env()

    def test_out_of_range_loxone_port(self) -> None:
        env = {
            "LOXONE_HOST": "host",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
            "LOXONE_PORT": "99999",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="between 1 and 65535"),
        ):
            RootConfig.from_env()

    def test_invalid_mcp_port(self) -> None:
        env = {
            "LOXONE_HOST": "host",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
            "MCP_PORT": "notanumber",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="MCP_PORT must be an integer"),
        ):
            RootConfig.from_env()

    def test_invalid_transport(self) -> None:
        env = {
            "LOXONE_HOST": "host",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
            "MCP_TRANSPORT": "grpc",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="MCP_TRANSPORT"),
        ):
            RootConfig.from_env()

    def test_invalid_access_mode(self) -> None:
        env = {
            "LOXONE_HOST": "host",
            "LOXONE_USERNAME": "user",
            "LOXONE_PASSWORD": "pass",
            "LOXONE_ACCESS_MODE": "admin",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            pytest.raises(ValueError, match="LOXONE_ACCESS_MODE"),
        ):
            RootConfig.from_env()

    def test_all_env_vars(self) -> None:
        env = {
            "LOXONE_HOST": "10.0.0.1",
            "LOXONE_PORT": "443",
            "LOXONE_USERNAME": "admin",
            "LOXONE_PASSWORD": "secret",
            "LOXONE_USE_TLS": "true",
            "LOXONE_ACCESS_MODE": "read-only",
            "MCP_HOST": "0.0.0.0",
            "MCP_PORT": "9090",
            "MCP_TRANSPORT": "both",
            "MCP_LOG_LEVEL": "DEBUG",
            "MCP_DEBUG": "true",
            "MCP_TLS_CERT": "/certs/cert.pem",
            "MCP_TLS_KEY": "/certs/key.pem",
            "METRICS_ENABLED": "false",
            "AUDIT_ENABLED": "false",
            "AUDIT_LOG_FILE": "/var/log/audit.jsonl",
            "AUDIT_RETENTION_DAYS": "30",
            "STRUCTURE_CACHE_TTL": "7200",
            "STRUCTURE_CHANGE_INTERVAL": "600",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = RootConfig.from_env()
        assert cfg.loxone.host == "10.0.0.1"
        assert cfg.loxone.port == 443
        assert cfg.loxone.use_tls is True
        assert cfg.server.port == 9090
        assert cfg.server.transport == TransportType.BOTH
        assert cfg.server.log_level == "DEBUG"
        assert cfg.server.debug is True
        assert cfg.server.tls_cert == "/certs/cert.pem"
        assert cfg.server.tls_key == "/certs/key.pem"
        assert cfg.access_control.mode == AccessMode.READ_ONLY
        assert cfg.metrics.enabled is False
        assert cfg.audit.enabled is False
        assert cfg.audit.log_file == "/var/log/audit.jsonl"
        assert cfg.audit.retention_days == 30
        assert cfg.structure_cache.ttl_seconds == 7200
        assert cfg.structure_cache.change_detection_interval == 600


# --- Redact Sensitive ---


class TestRedactSensitive:
    def test_redacts_password(self) -> None:
        event: dict[str, Any] = {"password": "supersecretpassword"}
        result = _redact_sensitive(None, "", event)
        assert "***REDACTED***" in result["password"]

    def test_redacts_token(self) -> None:
        event: dict[str, Any] = {"auth_token": "longtoken12345678"}
        result = _redact_sensitive(None, "", event)
        assert result["auth_token"] == "longtoke***REDACTED***"

    def test_short_value_fully_redacted(self) -> None:
        event: dict[str, Any] = {"password": "short"}
        result = _redact_sensitive(None, "", event)
        assert result["password"] == "***REDACTED***"

    def test_safe_key_not_redacted(self) -> None:
        event: dict[str, Any] = {"username": "admin", "host": "192.168.1.1"}
        result = _redact_sensitive(None, "", event)
        assert result["username"] == "admin"
        assert result["host"] == "192.168.1.1"


# --- Logging Setup ---


class TestSetupLogging:
    def test_setup_default(self) -> None:
        setup_logging()

    def test_setup_debug(self) -> None:
        setup_logging(log_level="DEBUG", debug=True)

    def test_setup_invalid_level(self) -> None:
        # Should fall back to INFO (20) without error
        setup_logging(log_level="NONEXISTENT")
