"""Audit logging for Loxone MCP Server.

Writes JSON Lines audit entries to logs/audit.jsonl with daily rotation,
retention management, and sensitive data redaction.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# --- Models (T059) ---


class EventType(StrEnum):
    """Audit event types."""

    AUTH_SUCCESS = "AUTH_SUCCESS"
    AUTH_FAILURE = "AUTH_FAILURE"
    RESOURCE_READ = "RESOURCE_READ"
    TOOL_EXECUTION = "TOOL_EXECUTION"
    ACCESS_DENIED = "ACCESS_DENIED"
    STRUCTURE_RELOAD = "STRUCTURE_RELOAD"
    ERROR = "ERROR"


class AuditEntry(BaseModel):
    """A single audit log entry.

    Required fields: timestamp, event_type, user, action, success.
    """

    timestamp: str = Field(description="ISO 8601 timestamp (UTC)")
    event_type: EventType = Field(description="Category of audit event")
    user: str = Field(description="Username from authentication")
    source_ip: str | None = Field(default=None, description="Client IP address")
    action: str = Field(description="Specific action performed")
    method: str | None = Field(default=None, description="Control action for tool executions")
    target: str | None = Field(default=None, description="Target component UUID or resource")
    success: bool = Field(description="Operation result")
    duration_ms: float | None = Field(default=None, description="Operation duration in ms")
    error_message: str | None = Field(default=None, description="Error message if failed")
    details: dict[str, Any] = Field(default_factory=dict, description="Additional context")


# --- Sensitive Data Redaction (T065) ---

_SENSITIVE_PATTERNS = [
    (re.compile(r'"password"\s*:\s*"[^"]*"', re.IGNORECASE), '"password": "***REDACTED***"'),
    (re.compile(r'"token"\s*:\s*"([^"]{8})[^"]*"', re.IGNORECASE), '"token": "\\1..."'),
    (re.compile(r'"key"\s*:\s*"[^"]*"', re.IGNORECASE), '"key": "***REDACTED***"'),
    (re.compile(r'"secret"\s*:\s*"[^"]*"', re.IGNORECASE), '"secret": "***REDACTED***"'),
]


def redact_sensitive(text: str) -> str:
    """Redact sensitive data from a string.

    Redacts passwords, tokens (keeps first 8 chars), keys, and secrets.

    Args:
        text: Text potentially containing sensitive data

    Returns:
        Text with sensitive data redacted
    """
    result = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_entry_details(details: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive values from audit entry details dict.

    Args:
        details: Raw details dictionary

    Returns:
        Sanitized details dictionary
    """
    sanitized = {}
    for key, value in details.items():
        lower_key = key.lower()
        if any(s in lower_key for s in ("password", "secret", "key", "credential")):
            sanitized[key] = "***REDACTED***"
        elif "token" in lower_key and isinstance(value, str) and len(value) > 8:
            sanitized[key] = value[:8] + "..."
        else:
            sanitized[key] = value
    return sanitized


# --- Audit Logger (T058) ---


class AuditLogger:
    """JSON Lines audit log writer with rotation and retention.

    Writes to logs/audit.jsonl by default with daily rotation.
    Old log files are cleaned up based on retention_days config.
    """

    def __init__(
        self,
        log_dir: str | Path = "logs",
        retention_days: int = 90,
        enabled: bool = True,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._retention_days = retention_days
        self._enabled = enabled
        self._current_date: str | None = None
        self._file: Any = None

        if self._enabled:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_old_logs()

    def _get_log_path(self) -> Path:
        """Get the current log file path (daily rotation)."""
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        if today != self._current_date:
            self._rotate(today)
        return self._log_dir / f"audit-{today}.jsonl"

    def _rotate(self, new_date: str) -> None:
        """Rotate to a new daily log file."""
        if self._file:
            self._file.close()
            self._file = None
        self._current_date = new_date

    def _ensure_file(self) -> Any:
        """Ensure the log file is open for writing."""
        path = self._get_log_path()
        if self._file is None or self._file.closed:
            self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115
        return self._file

    def _cleanup_old_logs(self) -> None:
        """Delete audit log files older than retention_days (T064)."""
        if not self._log_dir.exists():
            return

        cutoff = datetime.now(tz=UTC) - timedelta(days=self._retention_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        for path in self._log_dir.glob("audit-*.jsonl"):
            # Extract date from filename: audit-YYYY-MM-DD.jsonl
            name = path.stem  # audit-YYYY-MM-DD
            date_part = name.replace("audit-", "")
            if date_part < cutoff_str:
                try:
                    path.unlink()
                    logger.info("audit_log_cleaned", file=str(path))
                except OSError:
                    logger.warning("audit_log_cleanup_failed", file=str(path))

    def log(self, entry: AuditEntry) -> None:
        """Write an audit entry to the log file.

        Applies sensitive data redaction before writing.

        Args:
            entry: The audit entry to log
        """
        if not self._enabled:
            return

        # Redact sensitive details
        sanitized_entry = entry.model_copy(
            update={"details": redact_entry_details(entry.details)}
        )

        try:
            line = sanitized_entry.model_dump_json()
            # Apply pattern-based redaction to the whole line
            line = redact_sensitive(line)
            f = self._ensure_file()
            f.write(line + "\n")
            f.flush()
        except Exception:
            logger.exception("audit_log_write_failed")

    def close(self) -> None:
        """Close the log file and flush pending writes."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()
            self._file = None


# --- Convenience Functions ---

# Module-level singleton (set during server startup)
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger | None:
    """Get the global audit logger instance."""
    return _audit_logger


def set_audit_logger(logger_instance: AuditLogger) -> None:
    """Set the global audit logger instance."""
    global _audit_logger
    _audit_logger = logger_instance


def log_event(
    event_type: EventType,
    user: str,
    action: str,
    success: bool,
    *,
    source_ip: str | None = None,
    method: str | None = None,
    target: str | None = None,
    duration_ms: float | None = None,
    error_message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Log an audit event using the global logger.

    This is the primary interface for audit logging throughout the application.

    Args:
        event_type: Category of audit event
        user: Username
        action: Specific action
        success: Whether the operation succeeded
        source_ip: Client IP address
        method: Control action (for tool executions)
        target: Target component/resource
        duration_ms: Operation duration
        error_message: Error message if failed
        details: Additional context
    """
    audit = _audit_logger
    if audit is None:
        return

    entry = AuditEntry(
        timestamp=datetime.now(tz=UTC).isoformat(),
        event_type=event_type,
        user=user,
        action=action,
        success=success,
        source_ip=source_ip,
        method=method,
        target=target,
        duration_ms=duration_ms,
        error_message=error_message,
        details=details or {},
    )
    audit.log(entry)
