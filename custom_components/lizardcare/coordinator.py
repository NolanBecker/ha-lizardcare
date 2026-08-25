"""Shared care state for Lizard Care."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    STATE_FOOD_IN_ENCLOSURE,
    STATE_LAST_FED,
    STORAGE_VERSION,
)


class CareStateStorage(TypedDict):
    """JSON-serializable persisted care state."""

    last_fed: str | None
    food_in_enclosure: bool


class LizardCareData:
    """Manage persisted care state for one pet config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize care state."""
        self.last_fed: datetime | None = None
        self.food_in_enclosure = False
        self._listeners: set[Callable[[], None]] = set()
        self._update_lock = asyncio.Lock()
        self._store = Store[CareStateStorage](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )

    async def async_load(self) -> None:
        """Load this pet's persisted care state."""
        stored = await self._store.async_load()
        if stored is None:
            return

        stored_last_fed = stored.get(STATE_LAST_FED)
        if isinstance(stored_last_fed, str):
            parsed_last_fed = dt_util.parse_datetime(stored_last_fed)
            if parsed_last_fed is not None and parsed_last_fed.tzinfo is not None:
                self.last_fed = dt_util.as_utc(parsed_last_fed)

        stored_food_state = stored.get(STATE_FOOD_IN_ENCLOSURE)
        if isinstance(stored_food_state, bool):
            self.food_in_enclosure = stored_food_state

    async def async_feed(self) -> None:
        """Record a feeding and mark food as present."""
        async with self._update_lock:
            self.last_fed = dt_util.utcnow()
            self.food_in_enclosure = True
            self._async_notify_listeners()
            await self._async_save()

    async def async_remove_food(self) -> None:
        """Mark food as removed, persisting only when state changes."""
        async with self._update_lock:
            if not self.food_in_enclosure:
                return

            self.food_in_enclosure = False
            self._async_notify_listeners()
            await self._async_save()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a care-state listener."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify entities that care state changed."""
        for listener in tuple(self._listeners):
            listener()

    async def _async_save(self) -> None:
        """Persist current care state."""
        await self._store.async_save(
            {
                STATE_LAST_FED: (
                    self.last_fed.isoformat() if self.last_fed is not None else None
                ),
                STATE_FOOD_IN_ENCLOSURE: self.food_in_enclosure,
            }
        )
