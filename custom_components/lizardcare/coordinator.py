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
    STATE_LAST_FOOD_REMOVED,
    STATE_LAST_FULL_CLEAN,
    STATE_LAST_SPOT_CLEAN,
    STORAGE_VERSION,
)


class CareStateStorage(TypedDict, total=False):
    """JSON-serializable persisted care state."""

    last_fed: str | None
    last_food_removed: str | None
    food_in_enclosure: bool
    last_spot_clean: str | None
    last_full_clean: str | None


class LizardCareData:
    """Manage persisted care state for one pet config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize care state."""
        self.last_fed: datetime | None = None
        self.last_food_removed: datetime | None = None
        self.food_in_enclosure = False
        self.last_spot_clean: datetime | None = None
        self.last_full_clean: datetime | None = None
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

        self.last_fed = self._parse_stored_datetime(stored.get(STATE_LAST_FED))
        self.last_food_removed = self._parse_stored_datetime(
            stored.get(STATE_LAST_FOOD_REMOVED)
        )
        self.last_spot_clean = self._parse_stored_datetime(
            stored.get(STATE_LAST_SPOT_CLEAN)
        )
        self.last_full_clean = self._parse_stored_datetime(
            stored.get(STATE_LAST_FULL_CLEAN)
        )

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
        """Record food removal and mark food as removed."""
        async with self._update_lock:
            self.last_food_removed = dt_util.utcnow()
            self.food_in_enclosure = False
            self._async_notify_listeners()
            await self._async_save()

    async def async_spot_clean(self) -> None:
        """Record a spot clean."""
        async with self._update_lock:
            self.last_spot_clean = dt_util.utcnow()
            self._async_notify_listeners()
            await self._async_save()

    async def async_full_clean(self) -> None:
        """Record a full enclosure clean."""
        async with self._update_lock:
            self.last_full_clean = dt_util.utcnow()
            self._async_notify_listeners()
            await self._async_save()

    async def async_set_last_fed(self, value: datetime) -> None:
        """Correct the last-fed timestamp and reconcile enclosure state."""
        await self._async_set_timestamp("last_fed", value)

    async def async_set_last_food_removed(self, value: datetime) -> None:
        """Correct food-removal time and reconcile enclosure state."""
        await self._async_set_timestamp("last_food_removed", value)

    async def async_set_last_spot_clean(self, value: datetime) -> None:
        """Correct the last spot-clean timestamp."""
        await self._async_set_timestamp("last_spot_clean", value)

    async def async_set_last_full_clean(self, value: datetime) -> None:
        """Correct the last full-clean timestamp."""
        await self._async_set_timestamp("last_full_clean", value)

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

    @callback
    def reconcile_food_in_enclosure(self) -> bool:
        """Reconcile enclosure state from feeding and removal timestamps."""
        reconciled_state = self.last_fed is not None and (
            self.last_food_removed is None
            or self.last_fed > self.last_food_removed
        )
        if self.food_in_enclosure == reconciled_state:
            return False

        self.food_in_enclosure = reconciled_state
        return True

    @staticmethod
    def _parse_stored_datetime(value: object) -> datetime | None:
        """Parse a stored timezone-aware datetime as UTC."""
        if not isinstance(value, str):
            return None

        parsed = dt_util.parse_datetime(value)
        if parsed is None or parsed.tzinfo is None:
            return None
        return dt_util.as_utc(parsed)

    async def _async_set_timestamp(self, attribute: str, value: datetime) -> None:
        """Correct one care timestamp and persist the changed state."""
        if value.tzinfo is None:
            raise ValueError("Care timestamps must be timezone-aware")

        value = dt_util.as_utc(value)
        async with self._update_lock:
            timestamp_changed = getattr(self, attribute) != value
            if timestamp_changed:
                setattr(self, attribute, value)

            food_state_changed = False
            if attribute in ("last_fed", "last_food_removed"):
                food_state_changed = self.reconcile_food_in_enclosure()

            if not timestamp_changed and not food_state_changed:
                return
            self._async_notify_listeners()
            await self._async_save()

    async def _async_save(self) -> None:
        """Persist current care state."""
        await self._store.async_save(
            {
                STATE_LAST_FED: (
                    self.last_fed.isoformat() if self.last_fed is not None else None
                ),
                STATE_LAST_FOOD_REMOVED: (
                    self.last_food_removed.isoformat()
                    if self.last_food_removed is not None
                    else None
                ),
                STATE_FOOD_IN_ENCLOSURE: self.food_in_enclosure,
                STATE_LAST_SPOT_CLEAN: (
                    self.last_spot_clean.isoformat()
                    if self.last_spot_clean is not None
                    else None
                ),
                STATE_LAST_FULL_CLEAN: (
                    self.last_full_clean.isoformat()
                    if self.last_full_clean is not None
                    else None
                ),
            }
        )
