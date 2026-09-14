"""Tests for durable per-pet Care History journals."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from custom_components.lizardcare.coordinator import LizardCareData
from custom_components.lizardcare.journal import (
    JOURNAL_STORAGE_VERSION,
    JournalEventType,
    JournalManager,
    JournalSource,
    normalize_manual_metadata,
)


class FakeStore:
    """Minimal persistent Store replacement shared across manager instances."""

    def __init__(self, stored: object = None) -> None:
        self.stored = stored
        self.save_count = 0

    async def async_load(self) -> object:
        """Return stored data."""
        return self.stored

    async def async_save(self, data: object) -> None:
        """Persist data in memory."""
        self.stored = data
        self.save_count += 1


class FakeBus:
    """Capture journal refresh events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, str]]] = []

    def async_fire(self, event_type: str, data: dict[str, str]) -> None:
        """Record one event."""
        self.events.append((event_type, data))


class FakeHass:
    """Provide the event bus used by the runtime."""

    def __init__(self) -> None:
        self.bus = FakeBus()


def test_first_run_and_manual_entry_persist_across_reload() -> None:
    """An absent journal is safe and a saved entry survives recreation."""
    store = FakeStore()
    manager = JournalManager(None, "pet-one", store=store)  # type: ignore[arg-type]
    asyncio.run(manager.async_load())
    assert manager.entries() == []

    created = asyncio.run(
        manager.async_add_entry(
            JournalEventType.NOTE,
            note="  Calm during handling  ",
        )
    )
    assert store.stored["format_version"] == JOURNAL_STORAGE_VERSION

    reloaded = JournalManager(None, "pet-one", store=store)  # type: ignore[arg-type]
    asyncio.run(reloaded.async_load())
    assert reloaded.entries() == [created]
    assert reloaded.latest_entry.note == "Calm during handling"


def test_custom_timestamp_metadata_ids_and_ordering() -> None:
    """Entries retain structured data, unique IDs, and newest-first retrieval."""
    store = FakeStore()
    manager = JournalManager(None, "pet-one", store=store)  # type: ignore[arg-type]
    later = datetime(2026, 9, 14, 20, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(hours=2)

    latest = asyncio.run(
        manager.async_add_entry(
            JournalEventType.WEIGHT,
            timestamp=later,
            metadata={"weight": 42, "unit": "g"},
        )
    )
    oldest = asyncio.run(
        manager.async_add_entry(
            JournalEventType.SHED,
            timestamp=earlier,
            note="Nearly complete",
        )
    )

    assert latest.entry_id != oldest.entry_id
    assert manager.entries() == [latest, oldest]
    assert latest.metadata == {"weight": 42, "unit": "g"}
    assert latest.source == JournalSource.MANUAL


def test_pet_journals_are_isolated() -> None:
    """Separate per-entry stores never expose another pet's records."""
    first = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    second = JournalManager(None, "pet-two", store=FakeStore())  # type: ignore[arg-type]
    asyncio.run(first.async_add_entry(JournalEventType.FEEDING))

    assert len(first.entries()) == 1
    assert second.entries() == []
    assert first.latest_entry.pet_id == "pet-one"


def test_delete_entry_and_missing_id_avoid_unnecessary_write() -> None:
    """Single deletion persists, while a missing ID is a safe no-op."""
    store = FakeStore()
    manager = JournalManager(None, "pet-one", store=store)  # type: ignore[arg-type]
    entry = asyncio.run(manager.async_add_entry(JournalEventType.HEALTH))
    writes_after_add = store.save_count

    assert not asyncio.run(manager.async_delete_entry("missing"))
    assert store.save_count == writes_after_add
    assert asyncio.run(manager.async_delete_entry(entry.entry_id))
    assert manager.entries() == []
    assert store.save_count == writes_after_add + 1


@pytest.mark.parametrize(
    "stored",
    [
        "not-a-dictionary",
        {"format_version": 0, "entries": "not-a-list"},
        {"format_version": 1, "entries": [None, {}, {"entry_id": "bad"}]},
    ],
)
def test_malformed_or_older_storage_loads_safely(stored: object) -> None:
    """Invalid old records cannot prevent a pet from loading."""
    manager = JournalManager(None, "pet-one", store=FakeStore(stored))  # type: ignore[arg-type]

    asyncio.run(manager.async_load())
    assert manager.entries() == []


def _care_data(manager: JournalManager) -> LizardCareData:
    """Build the coordinator portion needed to exercise care actions."""
    data = object.__new__(LizardCareData)
    data.last_fed = None
    data.last_food_removed = None
    data.food_in_enclosure = False
    data.last_spot_clean = None
    data.last_full_clean = None
    data._update_lock = asyncio.Lock()
    data._listeners = set()
    data._async_save = AsyncMock()  # type: ignore[method-assign]
    data._hass = FakeHass()
    data.entry_id = "pet-one"
    data.journal = manager
    return data


@pytest.mark.parametrize(
    ("method", "event_type"),
    [
        ("async_feed", JournalEventType.FEEDING),
        ("async_remove_food", JournalEventType.FOOD_REMOVED),
        ("async_spot_clean", JournalEventType.SPOT_CLEAN),
        ("async_full_clean", JournalEventType.FULL_CLEAN),
    ],
)
def test_each_care_action_creates_exactly_one_entry(
    method: str,
    event_type: JournalEventType,
) -> None:
    """Successful button actions append once without changing old semantics."""
    manager = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    data = _care_data(manager)

    asyncio.run(getattr(data, method)())

    entries = manager.entries()
    assert len(entries) == 1
    assert entries[0].event_type == event_type
    assert entries[0].source == JournalSource.AUTOMATIC
    data._async_save.assert_awaited_once()  # type: ignore[attr-defined]
    assert data._hass.bus.events == [
        ("lizardcare_journal_updated", {"entry_id": "pet-one"})
    ]


def test_manual_add_and_delete_emit_update_events() -> None:
    """Manual mutations notify subscribed cards without polling."""
    manager = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    data = _care_data(manager)

    entry = asyncio.run(data.async_add_journal_entry(JournalEventType.NOTE))
    assert asyncio.run(data.async_delete_journal_entry(entry.entry_id))
    assert data._hass.bus.events == [
        ("lizardcare_journal_updated", {"entry_id": "pet-one"}),
        ("lizardcare_journal_updated", {"entry_id": "pet-one"}),
    ]


def test_manual_timestamp_corrections_do_not_log_history() -> None:
    """Only actual action methods contain automatic journal appends."""
    source = (
        Path(__file__).parents[1]
        / "custom_components/lizardcare/coordinator.py"
    ).read_text()
    correction_section = source.split(
        "async def async_set_last_fed", maxsplit=1
    )[1].split("async def async_add_listener", maxsplit=1)[0]
    assert "journal.async_add_entry" not in correction_section


def test_service_descriptions_expose_safe_journal_management() -> None:
    """Service UI includes add/get/single-delete without bulk clearing."""
    root = Path(__file__).parents[1]
    services = yaml.safe_load(
        (root / "custom_components/lizardcare/services.yaml").read_text()
    )
    assert set(services) == {
        "add_journal_entry",
        "delete_journal_entry",
        "get_journal_entries",
    }
    event_options = services["add_journal_entry"]["fields"]["event_type"][
        "selector"
    ]["select"]["options"]
    assert {option["value"] for option in event_options} == {
        event_type.value for event_type in JournalEventType
    }
    assert "clear_journal" not in services


def test_latest_journal_sensor_is_registered_without_full_history() -> None:
    """The sensor exposes one latest record and never the entry collection."""
    root = Path(__file__).parents[1]
    sensor_source = (
        root / "custom_components/lizardcare/sensor.py"
    ).read_text()

    assert "LizardCareLastJournalActivitySensor(entry)" in sensor_source
    assert 'key="last_journal_activity"' in sensor_source
    sensor_class = sensor_source.split(
        "class LizardCareLastJournalActivitySensor", maxsplit=1
    )[1].split("class LizardCareTimestampSensor", maxsplit=1)[0]
    assert "latest_entry" in sensor_class
    assert ".entries(" not in sensor_class


def test_journal_retrieval_filters_and_limits_after_filtering() -> None:
    """Type and inclusive datetime bounds combine before the result limit."""
    manager = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    base = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

    async def add_entries() -> None:
        await manager.async_add_entry(JournalEventType.FEEDING, timestamp=base)
        await manager.async_add_entry(
            JournalEventType.NOTE,
            timestamp=base + timedelta(days=1),
        )
        await manager.async_add_entry(
            JournalEventType.FEEDING,
            timestamp=base + timedelta(days=2),
        )
        await manager.async_add_entry(
            JournalEventType.FEEDING,
            timestamp=base + timedelta(days=3),
        )

    asyncio.run(add_entries())

    assert len(manager.entries()) == 4
    assert [entry.event_type for entry in manager.entries(event_type="note")] == [
        JournalEventType.NOTE
    ]
    assert [
        entry.timestamp
        for entry in manager.entries(start_datetime=base + timedelta(days=2))
    ] == [base + timedelta(days=3), base + timedelta(days=2)]
    assert [
        entry.timestamp
        for entry in manager.entries(end_datetime=base + timedelta(days=1))
    ] == [base + timedelta(days=1), base]
    combined = manager.entries(
        event_type=JournalEventType.FEEDING,
        start_datetime=base,
        end_datetime=base + timedelta(days=2),
    )
    assert [entry.timestamp for entry in combined] == [
        base + timedelta(days=2),
        base,
    ]
    limited = manager.entries(event_type=JournalEventType.FEEDING, limit=2)
    assert [entry.timestamp for entry in limited] == [
        base + timedelta(days=3),
        base + timedelta(days=2),
    ]


@pytest.mark.parametrize(
    ("value", "unit"),
    [(42.5, "g"), (1.75, "oz")],
)
def test_weight_metadata_is_normalized(value: float, unit: str) -> None:
    """Supported positive Weight values produce structured metadata."""
    assert normalize_manual_metadata(
        JournalEventType.WEIGHT,
        {"scale": "kitchen"},
        weight_value=value,
        weight_unit=unit,
    ) == {"scale": "kitchen", "value": value, "unit": unit}


@pytest.mark.parametrize(
    ("value", "unit"),
    [
        (42, "kg"),
        (0, "g"),
        (-1, "oz"),
        ("heavy", "g"),
        (True, "g"),
    ],
)
def test_invalid_weight_metadata_is_rejected(value: object, unit: str) -> None:
    """Weight values must be positive numbers with a supported unit."""
    with pytest.raises((TypeError, ValueError)):
        normalize_manual_metadata(
            JournalEventType.WEIGHT,
            None,
            weight_value=value,
            weight_unit=unit,
        )


def test_non_weight_generic_metadata_remains_supported() -> None:
    """The existing generic metadata contract is unchanged for other events."""
    assert normalize_manual_metadata(
        JournalEventType.OTHER,
        {"category": "behavior"},
        weight_value="ignored",
        weight_unit="kg",
    ) == {"category": "behavior"}
