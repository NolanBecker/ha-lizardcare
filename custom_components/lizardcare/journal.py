"""Persistent per-pet care journal for Lizard Care."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, TypedDict
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

JOURNAL_STORAGE_VERSION = 1
JOURNAL_STORAGE_KEY = f"{DOMAIN}.journal"


class JournalEventType(StrEnum):
    """Built-in journal event types."""

    NOTE = "note"
    FEEDING = "feeding"
    FOOD_REMOVED = "food_removed"
    SPOT_CLEAN = "spot_clean"
    FULL_CLEAN = "full_clean"
    SHED = "shed"
    WEIGHT = "weight"
    ENCLOSURE = "enclosure"
    HEALTH = "health"
    OTHER = "other"


class JournalSource(StrEnum):
    """Journal entry origins."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


class JournalEntryStorage(TypedDict):
    """JSON representation of one journal entry."""

    entry_id: str
    pet_id: str
    event_type: str
    timestamp: str
    note: str | None
    source: str
    metadata: dict[str, Any]


class JournalStorage(TypedDict):
    """Versioned journal payload."""

    format_version: int
    entries: list[JournalEntryStorage]


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One immutable pet journal entry."""

    entry_id: str
    pet_id: str
    event_type: str
    timestamp: datetime
    note: str | None
    source: str
    metadata: dict[str, Any]

    def as_storage(self) -> JournalEntryStorage:
        """Return a JSON-serializable representation."""
        stored = asdict(self)
        stored["timestamp"] = self.timestamp.isoformat()
        return stored  # type: ignore[return-value]


class JournalManager:
    """Load and mutate one pet's persistent journal."""

    def __init__(
        self,
        hass: HomeAssistant,
        pet_id: str,
        *,
        store: Store[JournalStorage] | None = None,
    ) -> None:
        """Initialize the journal manager."""
        self._pet_id = pet_id
        self._entries: list[JournalEntry] = []
        self._lock = asyncio.Lock()
        self._store = store or Store[JournalStorage](
            hass,
            JOURNAL_STORAGE_VERSION,
            f"{JOURNAL_STORAGE_KEY}.{pet_id}",
        )

    @property
    def latest_entry(self) -> JournalEntry | None:
        """Return the newest journal entry."""
        return self._entries[-1] if self._entries else None

    async def async_load(self) -> None:
        """Load valid entries and safely ignore malformed records."""
        stored = await self._store.async_load()
        if not isinstance(stored, dict):
            return
        raw_entries = stored.get("entries")
        if not isinstance(raw_entries, list):
            return
        entries = [
            entry
            for raw in raw_entries
            if (entry := self._parse_entry(raw)) is not None
        ]
        self._entries = sorted(entries, key=lambda entry: entry.timestamp)

    async def async_add_entry(
        self,
        event_type: str,
        *,
        timestamp: datetime | None = None,
        note: str | None = None,
        source: JournalSource = JournalSource.MANUAL,
        metadata: dict[str, Any] | None = None,
    ) -> JournalEntry:
        """Append and persist one journal entry."""
        value = timestamp or dt_util.utcnow()
        if value.tzinfo is None:
            raise ValueError("Journal timestamps must be timezone-aware")
        normalized_type = event_type.strip().lower()
        if not normalized_type:
            raise ValueError("Journal event type must not be empty")
        entry = JournalEntry(
            entry_id=uuid4().hex,
            pet_id=self._pet_id,
            event_type=normalized_type,
            timestamp=dt_util.as_utc(value),
            note=note.strip() if isinstance(note, str) and note.strip() else None,
            source=source.value,
            metadata=dict(metadata or {}),
        )
        async with self._lock:
            self._entries.append(entry)
            self._entries.sort(key=lambda item: item.timestamp)
            await self._async_save()
        return entry

    async def async_delete_entry(self, entry_id: str) -> bool:
        """Delete one entry, returning whether it existed."""
        async with self._lock:
            remaining = [
                entry for entry in self._entries if entry.entry_id != entry_id
            ]
            if len(remaining) == len(self._entries):
                return False
            self._entries = remaining
            await self._async_save()
        return True

    def entries(
        self,
        *,
        event_type: str | None = None,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        limit: int | None = None,
    ) -> list[JournalEntry]:
        """Return filtered newest-first entries, limited after filtering."""
        entries = list(reversed(self._entries))
        if event_type is not None:
            entries = [
                entry for entry in entries if entry.event_type == event_type
            ]
        if start_datetime is not None:
            start = dt_util.as_utc(start_datetime)
            entries = [entry for entry in entries if entry.timestamp >= start]
        if end_datetime is not None:
            end = dt_util.as_utc(end_datetime)
            entries = [entry for entry in entries if entry.timestamp <= end]
        return entries if limit is None else entries[:limit]

    async def _async_save(self) -> None:
        """Persist the current versioned journal."""
        await self._store.async_save(
            {
                "format_version": JOURNAL_STORAGE_VERSION,
                "entries": [entry.as_storage() for entry in self._entries],
            }
        )

    def _parse_entry(self, raw: object) -> JournalEntry | None:
        """Parse one stored record without allowing corruption to block setup."""
        if not isinstance(raw, dict):
            return None
        entry_id = raw.get("entry_id")
        pet_id = raw.get("pet_id")
        event_type = raw.get("event_type")
        source = raw.get("source")
        timestamp = raw.get("timestamp")
        if not all(
            isinstance(value, str) and value
            for value in (entry_id, pet_id, event_type, source, timestamp)
        ):
            return None
        if pet_id != self._pet_id:
            return None
        parsed = dt_util.parse_datetime(timestamp)
        if parsed is None or parsed.tzinfo is None:
            return None
        note = raw.get("note")
        metadata = raw.get("metadata", {})
        return JournalEntry(
            entry_id=entry_id,
            pet_id=pet_id,
            event_type=event_type,
            timestamp=dt_util.as_utc(parsed),
            note=note if isinstance(note, str) and note else None,
            source=source,
            metadata=metadata if isinstance(metadata, dict) else {},
        )


def normalize_manual_metadata(
    event_type: str,
    metadata: dict[str, Any] | None,
    *,
    weight_value: object = None,
    weight_unit: object = None,
) -> dict[str, Any]:
    """Validate Weight fields while retaining generic metadata elsewhere."""
    normalized = dict(metadata or {})
    if event_type != JournalEventType.WEIGHT:
        return normalized
    if isinstance(weight_value, bool) or not isinstance(
        weight_value, int | float
    ):
        raise TypeError("Weight value must be numeric")
    value = float(weight_value)
    if value <= 0:
        raise ValueError("Weight value must be greater than zero")
    if weight_unit not in ("g", "oz"):
        raise ValueError("Weight unit must be g or oz")
    normalized.update({"value": value, "unit": weight_unit})
    return normalized
