"""In-memory state cache for Loxone component data.

Thread-safe cache with TTL-based expiration for structure data
and real-time updates for component states via WebSocket.
Includes LRU eviction when component states exceed 5MB.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from uuid import UUID

    from loxone_mcp.loxone.models import StructureFile

logger = structlog.get_logger()

# Maximum memory for component states (5 MB)
MAX_STATE_MEMORY_BYTES = 5 * 1024 * 1024


class StateCache:
    """Thread-safe in-memory cache for Loxone state data.

    Structure file data uses TTL-based expiration (default 1 hour).
    Component state values are updated in real-time from WebSocket.
    """

    def __init__(self, structure_ttl: int = 3600) -> None:
        self._lock = threading.Lock()
        self._structure: StructureFile | None = None
        self._structure_loaded_at: float = 0.0
        self._structure_ttl = structure_ttl
        self._component_states: dict[str, dict[str, Any]] = {}
        self._state_update_count: int = 0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        # LRU tracking: maps component UUID → last access time
        self._lru_access: dict[str, float] = {}

    @property
    def structure(self) -> StructureFile | None:
        """Get cached structure file if not expired."""
        from loxone_mcp.metrics.collector import record_cache_hit, record_cache_miss

        with self._lock:
            if self._structure is None:
                self._cache_misses += 1
                record_cache_miss()
                return None
            if time.monotonic() - self._structure_loaded_at > self._structure_ttl:
                logger.info("structure_cache_expired", ttl=self._structure_ttl)
                self._cache_misses += 1
                record_cache_miss()
                return None
            self._cache_hits += 1
            record_cache_hit()
            return self._structure

    @property
    def is_structure_valid(self) -> bool:
        """Check if structure cache is valid (not expired)."""
        with self._lock:
            if self._structure is None:
                return False
            return time.monotonic() - self._structure_loaded_at <= self._structure_ttl

    def set_structure(self, structure: StructureFile) -> None:
        """Update the cached structure file."""
        with self._lock:
            self._structure = structure
            self._structure_loaded_at = time.monotonic()
            logger.info(
                "structure_cache_updated",
                components=len(structure.controls),
                rooms=len(structure.rooms),
                categories=len(structure.categories),
            )

    def invalidate_structure(self) -> None:
        """Force structure cache invalidation."""
        with self._lock:
            self._structure = None
            self._structure_loaded_at = 0.0
            logger.info("structure_cache_invalidated")

    def get_component_state(self, uuid: str | UUID) -> dict[str, Any] | None:
        """Get current state values for a component."""
        key = str(uuid)
        with self._lock:
            state = self._component_states.get(key)
            if state is not None:
                self._cache_hits += 1
                self._lru_access[key] = time.monotonic()
            else:
                self._cache_misses += 1
            return state

    def update_component_state(self, uuid: str | UUID, key: str, value: Any) -> None:
        """Update a single state value for a component.

        This is called from WebSocket binary state updates.
        Triggers LRU eviction if memory exceeds MAX_STATE_MEMORY_BYTES.
        """
        str_uuid = str(uuid)
        with self._lock:
            if str_uuid not in self._component_states:
                self._component_states[str_uuid] = {}
            self._component_states[str_uuid][key] = value
            self._lru_access[str_uuid] = time.monotonic()
            self._state_update_count += 1

        # Check memory usage outside lock (approximate)
        self._maybe_evict()

    def set_component_states(self, uuid: str | UUID, states: dict[str, Any]) -> None:
        """Set all state values for a component at once."""
        str_uuid = str(uuid)
        with self._lock:
            self._component_states[str_uuid] = states

    def get_all_component_states(self) -> dict[str, dict[str, Any]]:
        """Get all cached component states."""
        with self._lock:
            return dict(self._component_states)

    def clear_states(self) -> None:
        """Clear all component state data (e.g., on WebSocket reconnect)."""
        with self._lock:
            self._component_states.clear()
            self._lru_access.clear()
            logger.info("component_states_cleared")

    def _maybe_evict(self) -> None:
        """Evict least-recently-used component states if memory exceeds 5MB."""
        with self._lock:
            estimated_size = sys.getsizeof(self._component_states)
            for states in self._component_states.values():
                estimated_size += sys.getsizeof(states)
                for v in states.values():
                    estimated_size += sys.getsizeof(v)

            if estimated_size <= MAX_STATE_MEMORY_BYTES:
                return

            # Sort by LRU access time (oldest first) and evict 10%
            sorted_uuids = sorted(
                self._lru_access.items(), key=lambda x: x[1]
            )
            evict_count = max(1, len(sorted_uuids) // 10)
            for uuid, _ in sorted_uuids[:evict_count]:
                self._component_states.pop(uuid, None)
                self._lru_access.pop(uuid, None)

            logger.info(
                "cache_lru_eviction",
                evicted=evict_count,
                remaining=len(self._component_states),
                estimated_bytes=estimated_size,
            )

    @property
    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            return {
                "structure_valid": self._structure is not None
                and (time.monotonic() - self._structure_loaded_at <= self._structure_ttl),
                "component_count": len(self._component_states),
                "state_update_count": self._state_update_count,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
            }
