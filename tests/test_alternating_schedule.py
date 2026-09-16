"""Tests for fixed-cadence alternating cleaning schedules."""

import asyncio
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.lizardcare.const import (
    CLEANING_SCHEDULE_ALTERNATING,
    CLEANING_SCHEDULE_INTERVAL,
    CLEANING_SCHEDULE_MONTHLY,
    CONF_ALTERNATING_ANCHOR_TYPE,
    CONF_ALTERNATING_CLEANING_ANCHOR_DATE,
    CONF_ALTERNATING_CLEANING_INTERVAL_DAYS,
    CONF_CLEANING_SCHEDULE_MODE,
)
from custom_components.lizardcare.coordinator import LizardCareData
from custom_components.lizardcare.journal import JournalEventType, JournalManager
from custom_components.lizardcare.schedule import (
    CareSchedule,
    CareStatus,
    CleaningOccurrenceType,
    alternating_occurrence_date,
    alternating_occurrence_type,
    calculate_alternating_cleaning_plan,
    calculate_care_status,
    first_alternating_occurrence_after,
    get_care_schedule,
)


class FakeEntry:
    """Small config-entry shape for schedule resolution."""

    def __init__(self, options=None, data=None):
        self.options = options or {}
        self.data = data or {}


class FakeStore:
    """In-memory journal store."""

    def __init__(self):
        self.stored = None

    async def async_load(self):
        return self.stored

    async def async_save(self, data):
        self.stored = data


class FakeBus:
    def async_fire(self, *_args):
        pass


def _schedule(
    *,
    anchor: date = date(2027, 1, 1),
    anchor_type: CleaningOccurrenceType = CleaningOccurrenceType.SPOT_CLEAN,
    interval: int = 45,
) -> CareSchedule:
    return CareSchedule(
        feeding_interval_days=2,
        spot_clean_enabled=True,
        spot_clean_interval_days=7,
        full_clean_interval_days=30,
        full_clean_satisfies_spot_clean=True,
        cleaning_schedule_mode=CLEANING_SCHEDULE_ALTERNATING,
        cleaning_day_of_month=1,
        full_clean_every=3,
        cleaning_cycle_anchor=date(2027, 1, 1),
        alternating_interval_days=interval,
        alternating_anchor_date=anchor,
        alternating_anchor_type=anchor_type,
    )


def _data() -> LizardCareData:
    data = object.__new__(LizardCareData)
    data.last_fed = None
    data.last_food_removed = None
    data.food_in_enclosure = False
    data.last_spot_clean = None
    data.last_full_clean = None
    data.alternating_completed_occurrence = None
    data.alternating_occurrence_outcomes = {}
    data.alternating_schedule_definition = None
    data._alternating_definition_was_loaded = False
    data._update_lock = asyncio.Lock()
    data._listeners = set()
    data._async_save = AsyncMock()
    data._hass = SimpleNamespace(bus=FakeBus())
    data.entry_id = "pet-one"
    data.journal = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    return data


def test_existing_entries_default_to_independent() -> None:
    """Missing mode/options retain all legacy scheduling semantics."""
    schedule = get_care_schedule(FakeEntry())  # type: ignore[arg-type]
    assert schedule.cleaning_schedule_mode == "interval"
    assert schedule.alternating_interval_days == 45


def test_saved_options_override_data_and_reach_recreated_runtime() -> None:
    """A real options replacement changes the effective runtime cadence."""
    old_definition = {
        CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_ALTERNATING,
        CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
        CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 45,
        CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
    }
    entry = FakeEntry(options=dict(old_definition), data=dict(old_definition))
    initial_schedule = get_care_schedule(entry)  # type: ignore[arg-type]
    initial_plan = calculate_alternating_cleaning_plan(initial_schedule, None)
    assert initial_schedule.alternating_anchor_date == date(2026, 9, 1)
    assert initial_plan.next_cleaning.date() == date(2026, 9, 1)

    # Home Assistant replaces config_entry.options with the Options Flow result.
    entry.options = {
        **old_definition,
        CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-07-01",
    }
    recreated_schedule = get_care_schedule(entry)  # type: ignore[arg-type]
    recreated_runtime = _configured_progression()
    changed = asyncio.run(
        recreated_runtime.async_reconcile_alternating_definition(
            recreated_schedule
        )
    )
    recreated_plan = calculate_alternating_cleaning_plan(
        recreated_schedule,
        recreated_runtime.alternating_completed_occurrence,
    )

    assert changed is True
    assert recreated_schedule.alternating_anchor_date == date(2026, 7, 1)
    assert recreated_plan.next_cleaning.date() == date(2026, 7, 1)
    assert recreated_plan.next_cleaning.isoformat().startswith("2026-07-01")
    assert recreated_plan.occurrence_number == 1
    assert recreated_runtime.alternating_occurrence_outcomes == {}


def test_each_saved_definition_option_reaches_schedule_resolution() -> None:
    """Interval and anchor type changes are read from current entry options."""
    entry = FakeEntry(
        options={
            CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_ALTERNATING,
            CONF_ALTERNATING_CLEANING_ANCHOR_DATE: date(2026, 7, 1),
            CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 30,
            CONF_ALTERNATING_ANCHOR_TYPE: "full_clean",
        },
        data={
            CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
            CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 45,
            CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
        },
    )
    schedule = get_care_schedule(entry)  # type: ignore[arg-type]
    assert schedule.alternating_anchor_date == date(2026, 7, 1)
    assert schedule.alternating_interval_days == 30
    assert schedule.alternating_anchor_type is CleaningOccurrenceType.FULL_CLEAN


def test_options_use_standard_home_assistant_reload_flow() -> None:
    """Options retain Home Assistant's standard automatic reload helper."""
    root = Path(__file__).parents[1] / "custom_components/lizardcare"
    flow_source = (root / "config_flow.py").read_text()
    setup_source = (root / "__init__.py").read_text()

    assert "class LizardCareOptionsFlow(OptionsFlowWithReload):" in flow_source
    assert "entry.add_update_listener" not in setup_source
    assert "_async_reload_entry" not in setup_source


def test_exact_45_day_sequence_and_anchor_types() -> None:
    """Occurrence dates use exact days and types derive from slot parity."""
    schedule = _schedule()
    assert [
        alternating_occurrence_date(
            schedule.alternating_anchor_date, number, 45
        )
        for number in range(1, 6)
    ] == [
        date(2027, 1, 1),
        date(2027, 2, 15),
        date(2027, 4, 1),
        date(2027, 5, 16),
        date(2027, 6, 30),
    ]
    assert [
        alternating_occurrence_type(number, schedule.alternating_anchor_type)
        for number in range(1, 5)
    ] == [
        CleaningOccurrenceType.SPOT_CLEAN,
        CleaningOccurrenceType.FULL_CLEAN,
        CleaningOccurrenceType.SPOT_CLEAN,
        CleaningOccurrenceType.FULL_CLEAN,
    ]
    assert alternating_occurrence_type(
        1, CleaningOccurrenceType.FULL_CLEAN
    ) is CleaningOccurrenceType.FULL_CLEAN


def test_plan_status_and_option_changes_are_deterministic() -> None:
    """Anchor, interval, and type changes recalculate the same slot safely."""
    plan = calculate_alternating_cleaning_plan(_schedule(), 1)
    assert plan.next_cleaning.date() == date(2027, 2, 15)
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.FULL_CLEAN
    assert calculate_care_status(plan.next_cleaning, date(2027, 2, 14)) is CareStatus.NOT_DUE
    assert calculate_care_status(plan.next_cleaning, date(2027, 2, 15)) is CareStatus.DUE_TODAY
    assert calculate_care_status(plan.next_cleaning, date(2027, 2, 16)) is CareStatus.OVERDUE
    assert calculate_alternating_cleaning_plan(
        _schedule(interval=30), 1
    ).next_cleaning.date() == date(2027, 1, 31)
    assert calculate_alternating_cleaning_plan(
        _schedule(anchor=date(2027, 1, 10)), 1
    ).next_cleaning.date() == date(2027, 2, 24)
    assert calculate_alternating_cleaning_plan(
        _schedule(anchor_type=CleaningOccurrenceType.FULL_CLEAN), 1
    ).cleaning_occurrence_type is CleaningOccurrenceType.SPOT_CLEAN


def test_late_completion_skips_elapsed_slots_without_drift() -> None:
    """A matching late action advances to the first future anchored slot."""
    data = _data()
    completed = datetime(2027, 2, 20, 12, tzinfo=timezone.utc)
    with patch(
        "custom_components.lizardcare.coordinator.dt_util.utcnow",
        return_value=completed,
    ):
        asyncio.run(data.async_spot_clean(_schedule()))

    assert data.last_spot_clean == completed
    assert data.alternating_completed_occurrence == 2
    plan = calculate_alternating_cleaning_plan(
        _schedule(), data.alternating_completed_occurrence
    )
    assert plan.next_cleaning.date() == date(2027, 4, 1)
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.SPOT_CLEAN
    assert [entry.event_type for entry in data.journal.entries()] == [
        JournalEventType.SPOT_CLEAN
    ]


def test_exact_and_slightly_late_completion_never_shift_cadence() -> None:
    """Completing a Full Clean on or after Feb 15 leaves Apr 1 fixed."""
    for completed_day in (15, 18):
        data = _data()
        data.alternating_completed_occurrence = 1
        completed = datetime(
            2027, 2, completed_day, 12, tzinfo=timezone.utc
        )
        with patch(
            "custom_components.lizardcare.coordinator.dt_util.utcnow",
            return_value=completed,
        ):
            asyncio.run(data.async_full_clean(_schedule()))
        plan = calculate_alternating_cleaning_plan(
            _schedule(), data.alternating_completed_occurrence
        )
        assert plan.next_cleaning.date() == date(2027, 4, 1)


def test_wrong_button_and_override_do_not_advance() -> None:
    """History actions and corrections cannot satisfy a mismatched slot."""
    data = _data()
    with patch(
        "custom_components.lizardcare.coordinator.dt_util.utcnow",
        return_value=datetime(2027, 1, 1, 12, tzinfo=timezone.utc),
    ):
        asyncio.run(data.async_full_clean(_schedule()))
    assert data.last_full_clean is not None
    assert data.alternating_completed_occurrence is None
    asyncio.run(
        data.async_set_last_spot_clean(
            datetime(2027, 1, 2, tzinfo=timezone.utc)
        )
    )
    assert data.alternating_completed_occurrence is None


def test_backward_spot_correction_reopens_only_unsupported_spot_slot() -> None:
    """Moving Spot history back invalidates the later satisfied Spot slot."""
    data = _data()
    data.alternating_occurrence_outcomes = {
        1: "spot_clean",
        2: "full_clean",
        3: "spot_clean",
    }
    data.alternating_completed_occurrence = 3
    data.last_spot_clean = datetime(2027, 4, 1, tzinfo=timezone.utc)
    data.last_full_clean = datetime(2027, 2, 15, tzinfo=timezone.utc)

    asyncio.run(
        data.async_set_last_spot_clean(
            datetime(2027, 1, 1, tzinfo=timezone.utc), _schedule()
        )
    )

    assert data.alternating_occurrence_outcomes == {
        1: "spot_clean",
        2: "full_clean",
    }
    assert data.alternating_completed_occurrence == 2
    plan = calculate_alternating_cleaning_plan(_schedule(), 2)
    assert plan.next_cleaning.date() == date(2027, 4, 1)
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.SPOT_CLEAN
    assert data.journal.entries() == []


def test_backward_full_correction_preserves_spot_outcomes() -> None:
    """A Full correction removes only unsupported Full satisfaction records."""
    data = _data()
    data.alternating_occurrence_outcomes = {
        1: "spot_clean",
        2: "full_clean",
        3: "spot_clean",
        4: "full_clean",
    }
    data.alternating_completed_occurrence = 4
    data.last_full_clean = datetime(2027, 5, 16, tzinfo=timezone.utc)

    asyncio.run(
        data.async_set_last_full_clean(
            datetime(2027, 2, 15, tzinfo=timezone.utc), _schedule()
        )
    )

    assert data.alternating_occurrence_outcomes == {
        1: "spot_clean",
        2: "full_clean",
        3: "spot_clean",
    }
    assert data.alternating_completed_occurrence == 3


def test_forward_and_future_corrections_never_advance_progression() -> None:
    """Overrides may preserve outcomes but cannot satisfy new occurrences."""
    for corrected in (
        datetime(2027, 4, 1, tzinfo=timezone.utc),
        datetime(2030, 1, 1, tzinfo=timezone.utc),
    ):
        data = _data()
        data.alternating_occurrence_outcomes = {1: "spot_clean"}
        data.alternating_completed_occurrence = 1
        asyncio.run(
            data.async_set_last_spot_clean(corrected, _schedule())
        )
        assert data.alternating_occurrence_outcomes == {1: "spot_clean"}
        assert data.alternating_completed_occurrence == 1


def test_skipped_late_occurrence_is_not_resurrected_by_correction() -> None:
    """Explicitly skipped slots survive same-type history reconciliation."""
    data = _data()
    data.alternating_occurrence_outcomes = {
        1: "spot_clean",
        2: "skipped",
    }
    data.alternating_completed_occurrence = 2
    data.last_spot_clean = datetime(2027, 2, 20, tzinfo=timezone.utc)

    asyncio.run(
        data.async_set_last_spot_clean(
            datetime(2027, 1, 1, tzinfo=timezone.utc), _schedule()
        )
    )

    assert data.alternating_occurrence_outcomes == {
        1: "spot_clean",
        2: "skipped",
    }
    assert data.alternating_completed_occurrence == 2


def test_previous_integer_state_migrates_during_correction() -> None:
    """Pre-outcome alternating state becomes reconcilable without reset."""
    data = _data()
    data.alternating_completed_occurrence = 3
    data.last_spot_clean = datetime(2027, 4, 1, tzinfo=timezone.utc)
    data.last_full_clean = datetime(2027, 2, 15, tzinfo=timezone.utc)

    asyncio.run(
        data.async_set_last_spot_clean(
            datetime(2027, 1, 1, tzinfo=timezone.utc), _schedule()
        )
    )

    assert data.alternating_occurrence_outcomes == {
        1: "spot_clean",
        2: "full_clean",
    }
    assert data.alternating_completed_occurrence == 2


def test_future_slot_math_preserves_skipped_type_parity() -> None:
    """Skipped occurrences do not blindly toggle from the completed action."""
    schedule = _schedule()
    assert first_alternating_occurrence_after(
        date(2027, 2, 20), schedule
    ) == 3
    assert alternating_occurrence_type(
        3, schedule.alternating_anchor_type
    ) is CleaningOccurrenceType.SPOT_CLEAN


def test_progression_survives_runtime_recreation_and_is_pet_isolated() -> None:
    """The minimal occurrence marker persists in each pet's own care store."""
    store_one = FakeStore()
    first = _data()
    first._store = store_one
    del first._async_save
    first.alternating_completed_occurrence = 4
    first.alternating_occurrence_outcomes = {
        1: "spot_clean",
        2: "full_clean",
        3: "spot_clean",
        4: "full_clean",
    }
    first.alternating_schedule_definition = "2027-01-01|45|spot_clean"
    first._alternating_definition_was_loaded = True
    asyncio.run(first._async_save())

    restored = _data()
    restored._store = store_one
    asyncio.run(restored.async_load())
    assert restored.alternating_completed_occurrence == 4
    assert restored.alternating_occurrence_outcomes == (
        first.alternating_occurrence_outcomes
    )
    assert restored.alternating_schedule_definition == (
        first.alternating_schedule_definition
    )

    other = _data()
    other.entry_id = "pet-two"
    other._store = FakeStore()
    asyncio.run(other.async_load())
    assert other.alternating_completed_occurrence is None


def _configured_progression() -> LizardCareData:
    """Return runtime state tied to the default alternating fixture."""
    data = _data()
    data.alternating_completed_occurrence = 2
    data.alternating_occurrence_outcomes = {
        1: "spot_clean",
        2: "full_clean",
    }
    data.alternating_schedule_definition = "2027-01-01|45|spot_clean"
    data._alternating_definition_was_loaded = True
    data.last_spot_clean = datetime(2027, 1, 2, tzinfo=timezone.utc)
    data.last_full_clean = datetime(2027, 2, 16, tzinfo=timezone.utc)
    return data


def test_each_definition_change_resets_progression_but_preserves_history() -> None:
    """Anchor, interval, and anchor type each define a fresh schedule."""
    changed_schedules = (
        _schedule(anchor=date(2026, 7, 1)),
        _schedule(interval=30),
        _schedule(anchor_type=CleaningOccurrenceType.FULL_CLEAN),
    )
    for schedule in changed_schedules:
        data = _configured_progression()
        journal_entry = asyncio.run(
            data.journal.async_add_entry(
                JournalEventType.NOTE,
                timestamp=datetime(2027, 1, 5, tzinfo=timezone.utc),
            )
        )
        old_spot = data.last_spot_clean
        old_full = data.last_full_clean
        asyncio.run(data.async_reconcile_alternating_definition(schedule))
        assert data.alternating_completed_occurrence is None
        assert data.alternating_occurrence_outcomes == {}
        assert data.last_spot_clean == old_spot
        assert data.last_full_clean == old_full
        assert [entry.entry_id for entry in data.journal.entries()] == [
            journal_entry.entry_id
        ]
        plan = calculate_alternating_cleaning_plan(schedule, None)
        assert plan.occurrence_number == 1


def test_identical_or_unrelated_changes_preserve_progression() -> None:
    """Only the effective alternating definition participates in reset logic."""
    data = _configured_progression()
    unrelated_change = replace(_schedule(), feeding_interval_days=9)
    asyncio.run(data.async_reconcile_alternating_definition(unrelated_change))
    assert data.alternating_completed_occurrence == 2
    assert data.alternating_occurrence_outcomes[2] == "full_clean"
    data._async_save.assert_not_awaited()


def test_mode_transitions_initialize_fresh_alternating_state() -> None:
    """Entering or leaving Alternating clears only schedule progression."""
    for old_mode in (CLEANING_SCHEDULE_INTERVAL, CLEANING_SCHEDULE_MONTHLY):
        data = _data()
        previous = replace(_schedule(), cleaning_schedule_mode=old_mode)
        asyncio.run(data.async_reconcile_alternating_definition(previous))
        data.alternating_completed_occurrence = 2  # stale legacy state
        data.alternating_occurrence_outcomes = {1: "spot_clean", 2: "skipped"}
        asyncio.run(data.async_reconcile_alternating_definition(_schedule()))
        assert data.alternating_completed_occurrence is None
        assert data.alternating_occurrence_outcomes == {}

    data = _configured_progression()
    independent = replace(
        _schedule(), cleaning_schedule_mode=CLEANING_SCHEDULE_INTERVAL
    )
    asyncio.run(data.async_reconcile_alternating_definition(independent))
    assert data.alternating_schedule_definition is None
    assert data.alternating_completed_occurrence is None


def test_pre_signature_state_resets_once_and_restart_preserves_new_definition() -> None:
    """Earlier development state cannot leak outcomes into a new definition."""
    store = FakeStore()
    old = _data()
    old._store = store
    del old._async_save
    old.alternating_completed_occurrence = 3
    old.alternating_occurrence_outcomes = {1: "spot_clean", 2: "skipped", 3: "spot_clean"}
    asyncio.run(old._async_save())

    loaded = _data()
    loaded._store = store
    del loaded._async_save
    asyncio.run(loaded.async_load())
    asyncio.run(loaded.async_reconcile_alternating_definition(_schedule()))
    assert loaded.alternating_occurrence_outcomes == {}
    assert loaded.alternating_completed_occurrence is None

    restarted = _data()
    restarted._store = store
    del restarted._async_save
    asyncio.run(restarted.async_load())
    asyncio.run(restarted.async_reconcile_alternating_definition(_schedule()))
    assert restarted.alternating_schedule_definition == "2027-01-01|45|spot_clean"
    assert restarted.alternating_occurrence_outcomes == {}
