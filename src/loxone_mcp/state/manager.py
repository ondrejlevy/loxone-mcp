"""State manager coordinating cache updates and notifications.

Bridges Loxone state updates with MCP notification delivery.
"""

from __future__ import annotations

from typing import Any, Callable, Coroutine
from uuid import UUID

import structlog

from loxone_mcp.loxone.models import StructureFile
from loxone_mcp.state.cache import StateCache

logger = structlog.get_logger()

# Type for notification callback: async function that sends MCP notifications
NotificationCallback = Callable[[str], Coroutine[Any, Any, None]]


class StateManager:
    """Coordinates state cache updates and triggers MCP notifications.

    Sits between the Loxone WebSocket client and the MCP notification sender.
    When state changes occur, it updates the cache and triggers notifications.
    """

    def __init__(self, cache: StateCache) -> None:
        self._cache = cache
        self._notification_callbacks: list[NotificationCallback] = []
        self._changed_components: set[str] = set()

    @property
    def cache(self) -> StateCache:
        """Access the underlying cache."""
        return self._cache

    def register_notification_callback(self, callback: NotificationCallback) -> None:
        """Register a callback for state change notifications."""
        self._notification_callbacks.append(callback)

    async def on_structure_loaded(self, structure: StructureFile) -> None:
        """Handle structure file load/reload."""
        self._cache.set_structure(structure)
        await self._notify_resource_changed("loxone://structure")
        await self._notify_resource_changed("loxone://components")
        await self._notify_resource_changed("loxone://rooms")
        await self._notify_resource_changed("loxone://categories")

    async def on_state_update(self, uuid: str, key: str, value: Any) -> None:
        """Handle a single component state update from WebSocket.

        Args:
            uuid: Component UUID string
            key: State key (e.g., "active", "position")
            value: New state value
        """
        self._cache.update_component_state(uuid, key, value)
        self._changed_components.add(uuid)

    async def flush_notifications(self) -> None:
        """Send notifications for all changed components since last flush.

        Called periodically or after processing a batch of state updates.
        """
        if not self._changed_components:
            return

        changed = self._changed_components.copy()
        self._changed_components.clear()

        # Notify that components resource has changed
        await self._notify_resource_changed("loxone://components")

        logger.debug(
            "state_notifications_flushed",
            changed_count=len(changed),
        )

    async def on_websocket_reconnect(self) -> None:
        """Handle WebSocket reconnection.

        Invalidates structure cache to force reload,
        clears component states since they may be stale.
        """
        logger.info("websocket_reconnect_detected")
        self._cache.invalidate_structure()
        self._cache.clear_states()

    async def _notify_resource_changed(self, uri: str) -> None:
        """Send resource change notification to all registered callbacks."""
        for callback in self._notification_callbacks:
            try:
                await callback(uri)
            except Exception:
                logger.exception("notification_callback_error", uri=uri)
