"""Regression tests for care status behavior retained by the refactor."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from custom_components.lizardcare.const import CONF_SPOT_CLEAN_ENABLED
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
        data={},
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


def test_spot_clean_defaults_enabled_and_can_be_disabled() -> None:
    """Existing entries retain Spot Clean unless the option is turned off."""
    existing_entry = SimpleNamespace(options={})
    disabled_entry = SimpleNamespace(
        options={
            CONF_SPOT_CLEAN_ENABLED: False,
            "spot_clean_interval_days": 12,
        }
    )
    reenabled_entry = SimpleNamespace(
        options={
            CONF_SPOT_CLEAN_ENABLED: True,
            "spot_clean_interval_days": 12,
        }
    )

    assert get_care_schedule(existing_entry).spot_clean_enabled is True
    assert get_care_schedule(disabled_entry).spot_clean_enabled is False
    assert get_care_schedule(disabled_entry).spot_clean_interval_days == 12
    assert get_care_schedule(reenabled_entry).spot_clean_interval_days == 12


def test_disabled_status_is_ignored_by_overall_care() -> None:
    """Disabled Spot Clean cannot worsen aggregate care state."""
    all_good = calculate_overall_care_status(
        {
            "feeding": CareStatus.NOT_DUE,
            "spot_clean": CareStatus.DISABLED,
            "full_clean": CareStatus.NOT_DUE,
        }
    )
    full_clean_overdue = calculate_overall_care_status(
        {
            "feeding": CareStatus.NOT_DUE,
            "spot_clean": CareStatus.DISABLED,
            "full_clean": CareStatus.OVERDUE,
        }
    )

    assert all_good.status is OverallCareStatus.ALL_GOOD
    assert full_clean_overdue.status is OverallCareStatus.OVERDUE
    assert full_clean_overdue.overdue_items == ("full_clean",)


def test_spot_clean_button_uses_schedule_availability() -> None:
    """The existing Spot Clean button is unavailable through a schedule guard."""
    button_source = (
        Path(__file__).parents[1]
        / "custom_components/lizardcare/button.py"
    ).read_text()
    assert "get_care_schedule(entry).spot_clean_enabled" in button_source
    assert "def available(self) -> bool:" in button_source
