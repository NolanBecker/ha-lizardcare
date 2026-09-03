"""Regression tests for care status behavior retained by the refactor."""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.lizardcare.instructions import get_care_instructions
from custom_components.lizardcare.schedule import (
    CareStatus,
    OverallCareStatus,
    calculate_care_status,
    calculate_effective_last_spot_clean,
    calculate_next_due,
    calculate_overall_care_status,
    get_care_schedule,
)


def test_feeding_and_cleaning_statuses_are_unchanged() -> None:
    """All three scheduled task types retain shared status semantics."""
    completed = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    today = date(2026, 8, 29)
    for interval, expected in (
        (3, CareStatus.NOT_DUE),
        (2, CareStatus.DUE_TODAY),
        (1, CareStatus.OVERDUE),
    ):
        assert (
            calculate_care_status(
                calculate_next_due(completed, interval),
                today,
            )
            is expected
        )


def test_overall_care_status_priority_is_unchanged() -> None:
    """Overdue continues to take priority over due-today tasks."""
    result = calculate_overall_care_status(
        {
            "feeding": CareStatus.DUE_TODAY,
            "spot_clean": CareStatus.OVERDUE,
            "full_clean": CareStatus.NOT_DUE,
        }
    )
    assert result.status is OverallCareStatus.OVERDUE
    assert result.attention_items == ("feeding",)
    assert result.overdue_items == ("spot_clean",)


def test_full_clean_still_satisfies_spot_clean() -> None:
    """A newer full clean remains the effective spot-clean event."""
    spot_clean = datetime(2026, 8, 1, tzinfo=timezone.utc)
    full_clean = spot_clean + timedelta(days=5)
    assert calculate_effective_last_spot_clean(
        spot_clean,
        full_clean,
        full_clean_satisfies_spot_clean=True,
    ) == full_clean
    assert calculate_effective_last_spot_clean(
        spot_clean,
        full_clean,
        full_clean_satisfies_spot_clean=False,
    ) == spot_clean


def test_legacy_notification_options_do_not_affect_care_helpers() -> None:
    """Obsolete options are ignored while schedules/instructions still load."""
    entry = SimpleNamespace(
        options={
            "feeding_interval_days": 3,
            "feeding_instructions": "Offer insects",
            "notification_recipients": ["notify.phone"],
            "feeding_reminders": True,
            "feeding_reminder_time": "19:00:00",
        }
    )
    assert get_care_schedule(entry).feeding_interval_days == 3
    assert get_care_instructions(entry).feeding == "Offer insects"
