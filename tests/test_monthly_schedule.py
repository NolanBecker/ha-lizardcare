"""Tests for deterministic monthly cleaning schedules."""

from datetime import date, datetime, timezone
from types import SimpleNamespace

from custom_components.lizardcare.const import (
    CLEANING_SCHEDULE_INTERVAL,
    CLEANING_SCHEDULE_MONTHLY,
    CONF_CLEANING_CYCLE_ANCHOR,
    CONF_CLEANING_DAY_OF_MONTH,
    CONF_CLEANING_SCHEDULE_MODE,
    CONF_FULL_CLEAN_EVERY,
)
from custom_components.lizardcare.schedule import (
    CareSchedule,
    CareStatus,
    CleaningOccurrenceType,
    OverallCareStatus,
    calculate_care_status,
    calculate_monthly_cleaning_plan,
    calculate_overall_care_status,
    get_care_schedule,
    monthly_occurrence_date,
    monthly_occurrence_type,
)


def _schedule(
    *,
    anchor: date = date(2026, 10, 1),
    day: int = 1,
    full_clean_every: int = 3,
) -> CareSchedule:
    return CareSchedule(
        feeding_interval_days=2,
        spot_clean_interval_days=7,
        full_clean_interval_days=30,
        full_clean_satisfies_spot_clean=True,
        cleaning_schedule_mode=CLEANING_SCHEDULE_MONTHLY,
        cleaning_day_of_month=day,
        full_clean_every=full_clean_every,
        cleaning_cycle_anchor=anchor,
    )


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, 12, tzinfo=timezone.utc)


def test_monthly_schedule_starts_on_anchor_day() -> None:
    """Occurrence one is the configured anchored calendar date."""
    plan = calculate_monthly_cleaning_plan(_schedule(), None, None)
    assert plan.next_cleaning.date() == date(2026, 10, 1)
    assert plan.next_spot_clean.date() == date(2026, 10, 1)
    assert plan.next_full_clean.date() == date(2026, 12, 1)
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.SPOT_CLEAN


def test_late_completion_does_not_shift_calendar() -> None:
    """Completing October late still leaves November anchored to the first."""
    plan = calculate_monthly_cleaning_plan(_schedule(), _at(2026, 10, 3), None)
    assert plan.next_cleaning.date() == date(2026, 11, 1)


def test_early_completion_does_not_shift_calendar() -> None:
    """A cleaning within seven days before occurrence one satisfies it."""
    plan = calculate_monthly_cleaning_plan(_schedule(), _at(2026, 9, 29), None)
    assert plan.next_cleaning.date() == date(2026, 11, 1)


def test_every_third_occurrence_is_full_clean() -> None:
    """The calendar index, rather than elapsed days, controls task type."""
    assert monthly_occurrence_type(1, 3) is CleaningOccurrenceType.SPOT_CLEAN
    assert monthly_occurrence_type(2, 3) is CleaningOccurrenceType.SPOT_CLEAN
    assert monthly_occurrence_type(3, 3) is CleaningOccurrenceType.FULL_CLEAN
    assert monthly_occurrence_type(6, 3) is CleaningOccurrenceType.FULL_CLEAN


def test_full_clean_replaces_third_spot_clean() -> None:
    """December exposes Full Clean while the next Spot Clean is January."""
    plan = calculate_monthly_cleaning_plan(
        _schedule(),
        _at(2026, 11, 1),
        None,
    )
    assert plan.next_cleaning.date() == date(2026, 12, 1)
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.FULL_CLEAN
    assert plan.next_full_clean.date() == date(2026, 12, 1)
    assert plan.next_spot_clean.date() == date(2027, 1, 1)


def test_completing_full_clean_advances_one_occurrence() -> None:
    """A late Full Clean satisfies December without making Spot Clean due."""
    schedule = _schedule()
    plan = calculate_monthly_cleaning_plan(
        schedule,
        _at(2026, 11, 1),
        _at(2026, 12, 3),
    )
    assert plan.next_cleaning.date() == date(2027, 1, 1)
    assert plan.next_spot_clean.date() == date(2027, 1, 1)
    assert calculate_care_status(
        plan.next_spot_clean,
        date(2026, 12, 3),
    ) is CareStatus.NOT_DUE


def test_every_occurrence_full_clean_has_no_spot_clean_due() -> None:
    """A cadence of one intentionally suppresses monthly Spot Clean dates."""
    plan = calculate_monthly_cleaning_plan(
        _schedule(full_clean_every=1),
        None,
        None,
    )
    assert plan.cleaning_occurrence_type is CleaningOccurrenceType.FULL_CLEAN
    assert plan.next_spot_clean is None
    assert plan.next_full_clean == plan.next_cleaning


def test_overall_status_reflects_monthly_full_clean_due() -> None:
    """A Full Clean occurrence contributes attention without Spot Clean."""
    plan = calculate_monthly_cleaning_plan(
        _schedule(),
        _at(2026, 11, 1),
        None,
    )
    result = calculate_overall_care_status(
        {
            "feeding": CareStatus.NOT_DUE,
            "spot_clean": calculate_care_status(
                plan.next_spot_clean,
                date(2026, 12, 1),
            ),
            "full_clean": calculate_care_status(
                plan.next_full_clean,
                date(2026, 12, 1),
            ),
        }
    )
    assert result.status is OverallCareStatus.ATTENTION_NEEDED
    assert result.attention_items == ("full_clean",)


def test_duplicate_completion_and_reload_do_not_advance_cycle() -> None:
    """The occurrence derives from dates and has no mutable counter."""
    schedule = _schedule()
    first = calculate_monthly_cleaning_plan(
        schedule,
        _at(2026, 11, 1),
        _at(2026, 12, 3),
    )
    duplicate = calculate_monthly_cleaning_plan(
        schedule,
        _at(2026, 11, 1),
        _at(2026, 12, 4),
    )
    reloaded = calculate_monthly_cleaning_plan(
        schedule,
        _at(2026, 11, 1),
        _at(2026, 12, 3),
    )
    assert duplicate.occurrence_number == first.occurrence_number
    assert reloaded == first


def test_short_months_clamp_to_final_day() -> None:
    """Day 31 uses each month's final valid calendar day."""
    anchor = date(2026, 1, 31)
    assert monthly_occurrence_date(anchor, 2, 31) == date(2026, 2, 28)
    assert monthly_occurrence_date(anchor, 4, 31) == date(2026, 4, 30)


def test_leap_year_february_uses_twenty_ninth() -> None:
    """Monthly clamping respects leap years."""
    assert monthly_occurrence_date(date(2028, 1, 31), 2, 31) == date(
        2028, 2, 29
    )


def test_schedule_mode_switches_without_migration() -> None:
    """Mode is an option override and defaults old entries to interval."""
    old_entry = SimpleNamespace(options={})
    assert (
        get_care_schedule(old_entry).cleaning_schedule_mode
        == CLEANING_SCHEDULE_INTERVAL
    )

    monthly_entry = SimpleNamespace(
        options={
            CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_MONTHLY,
            CONF_CLEANING_DAY_OF_MONTH: 1,
            CONF_FULL_CLEAN_EVERY: 3,
            CONF_CLEANING_CYCLE_ANCHOR: "2026-10-01",
        }
    )
    assert (
        get_care_schedule(monthly_entry).cleaning_schedule_mode
        == CLEANING_SCHEDULE_MONTHLY
    )

    interval_entry = SimpleNamespace(
        options={CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_INTERVAL}
    )
    assert (
        get_care_schedule(interval_entry).cleaning_schedule_mode
        == CLEANING_SCHEDULE_INTERVAL
    )
