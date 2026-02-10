"""Prometheus metrics collector for Loxone MCP Server.

Defines all prometheus metrics and provides helper functions
for instrumenting MCP requests, Loxone API calls, and cache operations.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram, generate_latest

if TYPE_CHECKING:
    from collections.abc import Generator

# --- MCP Metrics ---

mcp_requests_total = Counter(
    "mcp_requests_total",
    "Total MCP requests",
    ["method", "status"],
)

mcp_request_duration = Histogram(
    "mcp_request_duration_seconds",
    "MCP request duration",
    ["method"],
)

mcp_active_connections = Gauge(
    "mcp_active_connections",
    "Number of active MCP client connections",
)

# --- Loxone Metrics ---

loxone_websocket_connected = Gauge(
    "loxone_websocket_connected",
    "Loxone WebSocket connection status (1=connected, 0=disconnected)",
)

loxone_auth_attempts_total = Counter(
    "loxone_auth_attempts_total",
    "Loxone authentication attempts",
    ["method", "status"],
)

loxone_api_duration = Histogram(
    "loxone_api_duration_seconds",
    "Loxone API call duration",
    ["endpoint"],
)

loxone_state_updates_total = Counter(
    "loxone_state_updates_total",
    "Total Loxone state updates received",
)

# --- Cache Metrics ---

structure_cache_hits = Counter(
    "structure_cache_hits_total",
    "Structure file cache hits",
)

structure_cache_misses = Counter(
    "structure_cache_misses_total",
    "Structure file cache misses",
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Approximate cache size in bytes",
)


# --- Helper Functions ---


@contextmanager
def track_request_duration(method: str) -> Generator[None]:
    """Context manager to track MCP request duration.

    Args:
        method: MCP method name (e.g., "resources/list", "tools/call")
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        mcp_request_duration.labels(method=method).observe(duration)


@contextmanager
def track_api_duration(endpoint: str) -> Generator[None]:
    """Context manager to track Loxone API call duration.

    Args:
        endpoint: API endpoint name (e.g., "fetch_structure", "send_command")
    """
    start = time.monotonic()
    try:
        yield
    finally:
        duration = time.monotonic() - start
        loxone_api_duration.labels(endpoint=endpoint).observe(duration)


def record_request(method: str, status: str = "success") -> None:
    """Record an MCP request.

    Args:
        method: MCP method name
        status: Request status ("success" or "error")
    """
    mcp_requests_total.labels(method=method, status=status).inc()


def record_auth_attempt(method: str, status: str) -> None:
    """Record a Loxone authentication attempt.

    Args:
        method: Auth method ("token" or "hash")
        status: Attempt result ("success" or "failure")
    """
    loxone_auth_attempts_total.labels(method=method, status=status).inc()


def record_state_update() -> None:
    """Record a Loxone state update received via WebSocket."""
    loxone_state_updates_total.inc()


def set_websocket_status(connected: bool) -> None:
    """Set the WebSocket connection status gauge.

    Args:
        connected: Whether the WebSocket is connected
    """
    loxone_websocket_connected.set(1 if connected else 0)


def record_cache_hit() -> None:
    """Record a structure cache hit."""
    structure_cache_hits.inc()


def record_cache_miss() -> None:
    """Record a structure cache miss."""
    structure_cache_misses.inc()


def set_cache_size(size_bytes: int) -> None:
    """Set the approximate cache size gauge.

    Args:
        size_bytes: Cache size in bytes
    """
    cache_size_bytes.set(size_bytes)


def get_metrics() -> bytes:
    """Generate metrics in Prometheus exposition format.

    Returns:
        Metrics data as bytes
    """
    return generate_latest()
