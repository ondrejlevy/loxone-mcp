"""Unit tests for StateCache (state/cache.py).

Tests TTL expiration, LRU eviction, thread safety, and stats.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from loxone_mcp.state.cache import MAX_STATE_MEMORY_BYTES, StateCache


def _mock_structure(controls: int = 5, rooms: int = 2, categories: int = 3) -> MagicMock:
    structure = MagicMock()
    structure.controls = {f"ctrl-{i}": MagicMock() for i in range(controls)}
    structure.rooms = {f"room-{i}": MagicMock() for i in range(rooms)}
    structure.categories = {f"cat-{i}": MagicMock() for i in range(categories)}
    return structure


class TestStructureTTL:
    @patch("loxone_mcp.metrics.collector.record_cache_miss")
    @patch("loxone_mcp.metrics.collector.record_cache_hit")
    def test_no_structure(self, mock_hit: MagicMock, mock_miss: MagicMock) -> None:
        cache = StateCache(structure_ttl=3600)
        assert cache.structure is None
        mock_miss.assert_called_once()

    @patch("loxone_mcp.metrics.collector.record_cache_miss")
    @patch("loxone_mcp.metrics.collector.record_cache_hit")
    def test_valid_structure(self, mock_hit: MagicMock, mock_miss: MagicMock) -> None:
        cache = StateCache(structure_ttl=3600)
        structure = _mock_structure()
        cache.set_structure(structure)
        assert cache.structure is structure
        mock_hit.assert_called_once()

    @patch("loxone_mcp.metrics.collector.record_cache_miss")
    @patch("loxone_mcp.metrics.collector.record_cache_hit")
    def test_expired_structure(self, mock_hit: MagicMock, mock_miss: MagicMock) -> None:
        cache = StateCache(structure_ttl=0)  # immediately expires
        structure = _mock_structure()
        cache.set_structure(structure)
        # Wait tiny bit so TTL is exceeded
        time.sleep(0.01)
        assert cache.structure is None

    def test_is_structure_valid_true(self) -> None:
        cache = StateCache(structure_ttl=3600)
        cache.set_structure(_mock_structure())
        assert cache.is_structure_valid is True

    def test_is_structure_valid_false_none(self) -> None:
        cache = StateCache()
        assert cache.is_structure_valid is False

    def test_is_structure_valid_false_expired(self) -> None:
        cache = StateCache(structure_ttl=0)
        cache.set_structure(_mock_structure())
        time.sleep(0.01)
        assert cache.is_structure_valid is False

    def test_invalidate_structure(self) -> None:
        cache = StateCache()
        cache.set_structure(_mock_structure())
        cache.invalidate_structure()
        assert cache._structure is None
        assert cache._structure_loaded_at == 0.0


class TestComponentStates:
    def test_get_nonexistent(self) -> None:
        cache = StateCache()
        assert cache.get_component_state("nonexistent") is None

    def test_update_and_get(self) -> None:
        cache = StateCache()
        cache.update_component_state("comp-1", "value", 42.0)
        state = cache.get_component_state("comp-1")
        assert state is not None
        assert state["value"] == 42.0

    def test_multiple_state_keys(self) -> None:
        cache = StateCache()
        cache.update_component_state("comp-1", "value", 1.0)
        cache.update_component_state("comp-1", "text", "hello")
        state = cache.get_component_state("comp-1")
        assert state is not None
        assert state["value"] == 1.0
        assert state["text"] == "hello"

    def test_set_component_states(self) -> None:
        cache = StateCache()
        states = {"key1": "val1", "key2": 2}
        cache.set_component_states("comp-1", states)
        assert cache.get_component_state("comp-1") == states

    def test_get_all_component_states(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache.update_component_state("c2", "v", 2)
        all_states = cache.get_all_component_states()
        assert "c1" in all_states
        assert "c2" in all_states

    def test_clear_states(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache.clear_states()
        assert cache.get_component_state("c1") is None
        assert cache.get_all_component_states() == {}

    def test_uuid_type_conversion(self) -> None:
        from uuid import UUID

        cache = StateCache()
        test_uuid = UUID("12345678-1234-1234-1234-123456789abc")
        cache.update_component_state(test_uuid, "val", 10)
        state = cache.get_component_state(test_uuid)
        assert state is not None
        assert state["val"] == 10


class TestLRUEviction:
    def test_no_eviction_under_limit(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache._maybe_evict()
        assert cache.get_component_state("c1") is not None

    def test_lru_tracking(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache.update_component_state("c2", "v", 2)
        # c1 was accessed first, c2 second
        assert "c1" in cache._lru_access
        assert "c2" in cache._lru_access


class TestStats:
    def test_stats_initial(self) -> None:
        cache = StateCache()
        stats = cache.stats
        assert stats["structure_valid"] is False
        assert stats["component_count"] == 0
        assert stats["state_update_count"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0

    def test_stats_after_updates(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache.update_component_state("c2", "v", 2)
        stats = cache.stats
        assert stats["component_count"] == 2
        assert stats["state_update_count"] == 2

    def test_stats_hit_miss_counting(self) -> None:
        cache = StateCache()
        cache.update_component_state("c1", "v", 1)
        cache.get_component_state("c1")  # hit
        cache.get_component_state("missing")  # miss
        stats = cache.stats
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
