"""Unit tests for User Story 4: Monitor Server Health.

Tests Prometheus metrics collector, instrumentation helpers,
and /metrics endpoint format.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from loxone_mcp.metrics.collector import (
    cache_size_bytes,
    get_metrics,
    loxone_api_duration,
    loxone_auth_attempts_total,
    loxone_state_updates_total,
    loxone_websocket_connected,
    mcp_active_connections,
    mcp_request_duration,
    mcp_requests_total,
    record_auth_attempt,
    record_cache_hit,
    record_cache_miss,
    record_request,
    record_state_update,
    set_cache_size,
    set_websocket_status,
    structure_cache_hits,
    structure_cache_misses,
    track_api_duration,
    track_request_duration,
)

# --- Metric Definitions ---


class TestMetricDefinitions:
    """Verify all expected Prometheus metrics are defined."""

    def test_mcp_requests_total_defined(self) -> None:
        assert mcp_requests_total._name == "mcp_requests"
        assert "method" in mcp_requests_total._labelnames
        assert "status" in mcp_requests_total._labelnames

    def test_mcp_request_duration_defined(self) -> None:
        assert mcp_request_duration._name == "mcp_request_duration_seconds"
        assert "method" in mcp_request_duration._labelnames

    def test_mcp_active_connections_defined(self) -> None:
        assert mcp_active_connections._name == "mcp_active_connections"

    def test_loxone_websocket_connected_defined(self) -> None:
        assert loxone_websocket_connected._name == "loxone_websocket_connected"

    def test_loxone_auth_attempts_defined(self) -> None:
        assert loxone_auth_attempts_total._name == "loxone_auth_attempts"
        assert "method" in loxone_auth_attempts_total._labelnames
        assert "status" in loxone_auth_attempts_total._labelnames

    def test_loxone_api_duration_defined(self) -> None:
        assert loxone_api_duration._name == "loxone_api_duration_seconds"
        assert "endpoint" in loxone_api_duration._labelnames

    def test_loxone_state_updates_defined(self) -> None:
        assert loxone_state_updates_total._name == "loxone_state_updates"

    def test_cache_hits_defined(self) -> None:
        assert structure_cache_hits._name == "structure_cache_hits"

    def test_cache_misses_defined(self) -> None:
        assert structure_cache_misses._name == "structure_cache_misses"

    def test_cache_size_bytes_defined(self) -> None:
        assert cache_size_bytes._name == "cache_size_bytes"


# --- Helper Functions ---


class TestRecordRequest:
    """Test request recording helper."""

    def test_record_success(self) -> None:
        before = mcp_requests_total.labels(method="test_method", status="success")._value.get()
        record_request("test_method", "success")
        after = mcp_requests_total.labels(method="test_method", status="success")._value.get()
        assert after == before + 1

    def test_record_error(self) -> None:
        before = mcp_requests_total.labels(method="test_method", status="error")._value.get()
        record_request("test_method", "error")
        after = mcp_requests_total.labels(method="test_method", status="error")._value.get()
        assert after == before + 1


class TestTrackRequestDuration:
    """Test request duration tracking context manager."""

    def test_tracks_duration(self) -> None:
        with track_request_duration("test_track"):
            time.sleep(0.01)
        # Just verify it doesn't error; histogram internals are complex

    def test_tracks_duration_on_exception(self) -> None:
        with pytest.raises(ValueError), track_request_duration("test_track_error"):
            msg = "test"
            raise ValueError(msg)
        # Duration should still be recorded even on error


class TestTrackAPIDuration:
    """Test Loxone API duration tracking."""

    def test_tracks_api_duration(self) -> None:
        with track_api_duration("test_endpoint"):
            time.sleep(0.01)


class TestRecordAuthAttempt:
    """Test auth attempt recording."""

    def test_record_token_success(self) -> None:
        before = loxone_auth_attempts_total.labels(method="token", status="success")._value.get()
        record_auth_attempt("token", "success")
        after = loxone_auth_attempts_total.labels(method="token", status="success")._value.get()
        assert after == before + 1

    def test_record_hash_failure(self) -> None:
        before = loxone_auth_attempts_total.labels(method="hash", status="failure")._value.get()
        record_auth_attempt("hash", "failure")
        after = loxone_auth_attempts_total.labels(method="hash", status="failure")._value.get()
        assert after == before + 1


class TestStateUpdateRecording:
    """Test state update counter."""

    def test_record_state_update(self) -> None:
        before = loxone_state_updates_total._value.get()
        record_state_update()
        after = loxone_state_updates_total._value.get()
        assert after == before + 1


class TestWebSocketStatus:
    """Test WebSocket connection gauge."""

    def test_set_connected(self) -> None:
        set_websocket_status(True)
        assert loxone_websocket_connected._value.get() == 1

    def test_set_disconnected(self) -> None:
        set_websocket_status(False)
        assert loxone_websocket_connected._value.get() == 0


class TestCacheMetrics:
    """Test cache metric helpers."""

    def test_record_cache_hit(self) -> None:
        before = structure_cache_hits._value.get()
        record_cache_hit()
        after = structure_cache_hits._value.get()
        assert after == before + 1

    def test_record_cache_miss(self) -> None:
        before = structure_cache_misses._value.get()
        record_cache_miss()
        after = structure_cache_misses._value.get()
        assert after == before + 1

    def test_set_cache_size(self) -> None:
        set_cache_size(1024000)
        assert cache_size_bytes._value.get() == 1024000


# --- Metrics Endpoint ---


class TestGetMetrics:
    """Test Prometheus exposition format output."""

    def test_returns_bytes(self) -> None:
        result = get_metrics()
        assert isinstance(result, bytes)

    def test_contains_metric_names(self) -> None:
        result = get_metrics().decode("utf-8")
        assert "mcp_requests_total" in result
        assert "mcp_request_duration_seconds" in result
        assert "loxone_websocket_connected" in result
        assert "structure_cache_hits_total" in result

    def test_prometheus_format(self) -> None:
        result = get_metrics().decode("utf-8")
        # Prometheus format has HELP and TYPE lines
        assert "# HELP" in result
        assert "# TYPE" in result


# --- HTTP Endpoint Integration ---


class TestMetricsEndpoint:
    """Test /metrics HTTP endpoint via Starlette TestClient."""

    @pytest.fixture
    def app_client(self) -> Any:
        from starlette.testclient import TestClient

        from loxone_mcp.config import (
            AccessControlConfig,
            AuditConfig,
            LoxoneConfig,
            MetricsConfig,
            RootConfig,
            ServerConfig,
            StructureCacheConfig,
        )
        from loxone_mcp.state.cache import StateCache
        from loxone_mcp.state.manager import StateManager
        from loxone_mcp.transport.streamable_http import create_starlette_app

        server = MagicMock()
        server.config = RootConfig(
            server=ServerConfig(),
            loxone=LoxoneConfig(host="192.168.1.100", username="test", password="test"),
            access_control=AccessControlConfig(),
            metrics=MetricsConfig(),
            audit=AuditConfig(),
            structure_cache=StructureCacheConfig(),
        )
        cache = StateCache()
        server.state_manager = StateManager(cache)
        server._cache = cache
        server._ws_client = MagicMock()
        server._ws_client.is_connected = True
        mcp_server = MagicMock()
        mcp_server.run = AsyncMock()
        server.mcp_server = mcp_server
        app = create_starlette_app(server)
        return TestClient(app, raise_server_exceptions=False)

    def test_metrics_endpoint_returns_200(self, app_client: Any) -> None:
        response = app_client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_content_type(self, app_client: Any) -> None:
        response = app_client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_endpoint_body(self, app_client: Any) -> None:
        response = app_client.get("/metrics")
        assert "mcp_requests_total" in response.text
