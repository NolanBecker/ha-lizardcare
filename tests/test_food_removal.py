"""Tests for derived food-removal care state."""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.lizardcare.const import (
    CONF_FOOD_REMOVAL_ANCHOR_TIME,
    CONF_FOOD_REMOVAL_DELAY,
    CONF_FOOD_REMOVAL_DELAY_UNIT,
    CONF_REMOVE_FOOD_AFTER_HOURS,
    DEFAULT_FOOD_REMOVAL_DELAY,
    TIME_UNIT_HOURS,
    TIME_UNIT_MINUTES,
)
from custom_components.lizardcare.food_removal import (
    FoodRemovalStatus,
    calculate_food_removal_due_at,
    calculate_food_removal_status,
    get_food_removal_settings,
)

FED_AT = datetime(2026, 8, 29, 17, tzinfo=timezone.utc)


def _status(
    now: datetime,
    *,
    food_in_enclosure: bool = True,
):
    return calculate_food_removal_status(
        food_in_enclosure=food_in_enclosure,
        last_fed=FED_AT,
        delay_minutes=4 * 60,
        anchor_time=time(17),
        now=now,
    )


def test_not_needed_without_food() -> None:
    """Removed food never contributes a removal requirement."""
    result = _status(FED_AT + timedelta(hours=10), food_in_enclosure=False)
    assert result.status is FoodRemovalStatus.NOT_NEEDED
    assert result.due_at is None


def test_pending_after_feeding() -> None:
    """Present food is pending before its configured removal time."""
    result = _status(FED_AT + timedelta(hours=1))
    assert result.status is FoodRemovalStatus.PENDING
    assert result.due_at == FED_AT + timedelta(hours=4)
    assert result.minutes_until_due == 180
    assert result.minutes_overdue == 0


def test_due_at_removal_time() -> None:
    """Food becomes due at the exact configured removal time."""
    result = _status(FED_AT + timedelta(hours=4))
    assert result.status is FoodRemovalStatus.DUE
    assert result.minutes_until_due == 0
    assert result.minutes_overdue == 0


def test_overdue_after_meaningful_delay() -> None:
    """Food becomes overdue after one hour in the due state."""
    result = _status(FED_AT + timedelta(hours=5))
    assert result.status is FoodRemovalStatus.OVERDUE
    assert result.minutes_overdue == 60


def test_legacy_delay_option_is_retained() -> None:
    """The former notification delay remains the care timing setting."""
    entry = SimpleNamespace(options={CONF_REMOVE_FOOD_AFTER_HOURS: 6})
    settings = get_food_removal_settings(entry)
    assert settings.delay_value == 6
    assert settings.delay_unit == TIME_UNIT_HOURS
    assert settings.delay_minutes == 360


def test_invalid_or_missing_delay_uses_default() -> None:
    """Old entries without a usable delay load with a safe default."""
    for options in ({}, {CONF_REMOVE_FOOD_AFTER_HOURS: -1}):
        entry = SimpleNamespace(options=options)
        settings = get_food_removal_settings(entry)
        assert settings.delay_value == DEFAULT_FOOD_REMOVAL_DELAY
        assert settings.delay_unit == TIME_UNIT_HOURS


def test_new_delay_units_are_normalized_to_minutes() -> None:
    """New value/unit options support both hours and minutes."""
    minute_entry = SimpleNamespace(
        options={
            CONF_FOOD_REMOVAL_DELAY: 30,
            CONF_FOOD_REMOVAL_DELAY_UNIT: TIME_UNIT_MINUTES,
        }
    )
    hour_entry = SimpleNamespace(
        options={
            CONF_FOOD_REMOVAL_DELAY: 12,
            CONF_FOOD_REMOVAL_DELAY_UNIT: TIME_UNIT_HOURS,
        }
    )
    assert get_food_removal_settings(minute_entry).delay_minutes == 30
    assert get_food_removal_settings(hour_entry).delay_minutes == 720


@pytest.mark.parametrize(
    ("delay_minutes", "expected"),
    [
        (24 * 60, datetime(2026, 8, 30, 16, tzinfo=timezone.utc)),
        (12 * 60, datetime(2026, 8, 30, 4, tzinfo=timezone.utc)),
        (6 * 60, datetime(2026, 8, 29, 22, tzinfo=timezone.utc)),
        (30, datetime(2026, 8, 29, 16, 30, tzinfo=timezone.utc)),
    ],
)
def test_due_time_is_anchored_to_daily_care_time(
    delay_minutes: int,
    expected: datetime,
) -> None:
    """The exact feeding minute does not shift the removal boundary."""
    fed_at = datetime(2026, 8, 29, 16, 37, tzinfo=timezone.utc)
    assert calculate_food_removal_due_at(
        fed_at,
        delay_minutes,
        time(16),
    ) == expected


def test_anchor_time_loads_from_options() -> None:
    """The configured local anchor is available to the status calculation."""
    entry = SimpleNamespace(
        options={CONF_FOOD_REMOVAL_ANCHOR_TIME: "16:00:00"}
    )
    assert get_food_removal_settings(entry).anchor_time == time(16)
