"""Unit tests for User Story 5: Audit User Actions.

Tests audit entry creation, log file writing, rotation,
sensitive data redaction, and convenience logging functions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loxone_mcp.audit.logger import (
    AuditEntry,
    AuditLogger,
    EventType,
    get_audit_logger,
    log_event,
    redact_entry_details,
    redact_sensitive,
    set_audit_logger,
)

if TYPE_CHECKING:
    from pathlib import Path

# --- AuditEntry Model Tests (T059) ---


class TestAuditEntry:
    """Test AuditEntry model creation and serialization."""

    def test_create_minimal_entry(self) -> None:
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.AUTH_SUCCESS,
            user="admin",
            action="token_websocket",
            success=True,
        )
        assert entry.event_type == EventType.AUTH_SUCCESS
        assert entry.user == "admin"
        assert entry.success is True

    def test_create_full_entry(self) -> None:
        entry = AuditEntry(
            timestamp="2026-02-10T14:32:15.342Z",
            event_type=EventType.TOOL_EXECUTION,
            user="ai_assistant",
            source_ip="192.168.1.50",
            action="control_component",
            method="On",
            target="0f1e2c44-0004-1a2b-ffff403fb0c34b9e",
            success=True,
            duration_ms=157,
            error_message=None,
            details={"component_name": "Living Room Light"},
        )
        assert entry.method == "On"
        assert entry.target == "0f1e2c44-0004-1a2b-ffff403fb0c34b9e"
        assert entry.duration_ms == 157

    def test_entry_serialization(self) -> None:
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.RESOURCE_READ,
            user="test",
            action="loxone://components",
            success=True,
        )
        data = json.loads(entry.model_dump_json())
        assert data["event_type"] == "RESOURCE_READ"
        assert data["timestamp"] == "2026-02-10T14:30:00Z"

    def test_all_event_types(self) -> None:
        for event_type in EventType:
            entry = AuditEntry(
                timestamp="2026-02-10T14:30:00Z",
                event_type=event_type,
                user="test",
                action="test",
                success=True,
            )
            assert entry.event_type == event_type


# --- Sensitive Data Redaction Tests (T065) ---


class TestRedactSensitive:
    """Test pattern-based sensitive data redaction."""

    def test_redact_password(self) -> None:
        text = '{"password": "mysecret123"}'
        result = redact_sensitive(text)
        assert "mysecret123" not in result
        assert "***REDACTED***" in result

    def test_redact_token_keeps_prefix(self) -> None:
        text = '{"token": "eyJhbGciOiJSUzI1NiIsInR5cCI"}'
        result = redact_sensitive(text)
        assert "eyJhbGci" in result
        assert "OiJSUzI1NiIsInR5cCI" not in result

    def test_redact_key(self) -> None:
        text = '{"key": "super-secret-encryption-key-12345"}'
        result = redact_sensitive(text)
        assert "super-secret" not in result
        assert "***REDACTED***" in result

    def test_redact_secret(self) -> None:
        text = '{"secret": "api_secret_value"}'
        result = redact_sensitive(text)
        assert "api_secret_value" not in result

    def test_safe_data_not_redacted(self) -> None:
        text = '{"username": "admin", "uuid": "abc-123"}'
        result = redact_sensitive(text)
        assert "admin" in result
        assert "abc-123" in result


class TestRedactEntryDetails:
    """Test dict-level sensitive data redaction."""

    def test_redact_password_key(self) -> None:
        details = {"username": "admin", "password": "secret123"}
        result = redact_entry_details(details)
        assert result["username"] == "admin"
        assert result["password"] == "***REDACTED***"

    def test_redact_credential_key(self) -> None:
        details = {"credential": "some-credential-value"}
        result = redact_entry_details(details)
        assert result["credential"] == "***REDACTED***"

    def test_redact_token_keeps_prefix(self) -> None:
        details = {"auth_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.etc"}
        result = redact_entry_details(details)
        assert result["auth_token"] == "eyJhbGci..."

    def test_short_token_not_truncated(self) -> None:
        details = {"token": "short"}
        result = redact_entry_details(details)
        assert result["token"] == "short"

    def test_safe_values_preserved(self) -> None:
        details = {"component_name": "Light", "action": "On"}
        result = redact_entry_details(details)
        assert result == details


# --- AuditLogger Tests (T058) ---


class TestAuditLogger:
    """Test JSON Lines audit log writer."""

    def test_write_entry(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path, retention_days=90)
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.AUTH_SUCCESS,
            user="admin",
            action="token_websocket",
            success=True,
        )
        logger.log(entry)
        logger.close()

        log_files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(log_files) == 1

        content = log_files[0].read_text()
        data = json.loads(content.strip())
        assert data["event_type"] == "AUTH_SUCCESS"
        assert data["user"] == "admin"

    def test_multiple_entries(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        for i in range(3):
            entry = AuditEntry(
                timestamp=f"2026-02-10T14:3{i}:00Z",
                event_type=EventType.RESOURCE_READ,
                user="test",
                action=f"action-{i}",
                success=True,
            )
            logger.log(entry)
        logger.close()

        log_files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 3

    def test_disabled_logger(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path, enabled=False)
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.AUTH_SUCCESS,
            user="admin",
            action="test",
            success=True,
        )
        logger.log(entry)
        logger.close()

        log_files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(log_files) == 0

    def test_redacts_sensitive_in_details(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.AUTH_FAILURE,
            user="admin",
            action="token_websocket",
            success=False,
            details={"password": "secret123"},
        )
        logger.log(entry)
        logger.close()

        content = next(iter(tmp_path.glob("audit-*.jsonl"))).read_text()
        assert "secret123" not in content
        assert "***REDACTED***" in content

    def test_creates_log_directory(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "nested" / "logs"
        logger = AuditLogger(log_dir=log_dir)
        assert log_dir.exists()
        logger.close()


# --- Log Rotation Tests (T064) ---


class TestLogRotation:
    """Test daily log rotation and file cleanup."""

    def test_cleanup_old_logs(self, tmp_path: Path) -> None:
        # Create old log files
        (tmp_path / "audit-2020-01-01.jsonl").write_text("{}\n")
        (tmp_path / "audit-2020-01-15.jsonl").write_text("{}\n")
        # Create a recent file (will be preserved)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        (tmp_path / f"audit-{today}.jsonl").write_text("{}\n")

        logger = AuditLogger(log_dir=tmp_path, retention_days=30)
        logger.close()

        remaining = list(tmp_path.glob("audit-*.jsonl"))
        names = [f.name for f in remaining]
        assert f"audit-{today}.jsonl" in names
        assert "audit-2020-01-01.jsonl" not in names
        assert "audit-2020-01-15.jsonl" not in names

    def test_log_file_named_with_date(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        entry = AuditEntry(
            timestamp="2026-02-10T14:30:00Z",
            event_type=EventType.AUTH_SUCCESS,
            user="admin",
            action="test",
            success=True,
        )
        logger.log(entry)
        logger.close()

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        expected_file = tmp_path / f"audit-{today}.jsonl"
        assert expected_file.exists()


# --- Convenience Function Tests ---


class TestLogEvent:
    """Test the log_event convenience function."""

    def test_log_event_with_logger_set(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        set_audit_logger(logger)

        log_event(
            EventType.TOOL_EXECUTION,
            user="ai_assistant",
            action="control_component",
            success=True,
            method="On",
            target="test-uuid",
            duration_ms=150,
        )
        logger.close()

        content = next(iter(tmp_path.glob("audit-*.jsonl"))).read_text()
        data = json.loads(content.strip())
        assert data["event_type"] == "TOOL_EXECUTION"
        assert data["method"] == "On"

        # Reset global
        set_audit_logger(None)  # type: ignore[arg-type]

    def test_log_event_without_logger_does_not_error(self) -> None:
        set_audit_logger(None)  # type: ignore[arg-type]
        # Should not raise even without a logger set
        log_event(
            EventType.AUTH_SUCCESS,
            user="test",
            action="test",
            success=True,
        )

    def test_get_audit_logger(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        set_audit_logger(logger)
        assert get_audit_logger() is logger
        set_audit_logger(None)  # type: ignore[arg-type]
        logger.close()
