"""Tests for derived food-removal care state."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from custom_components.lizardcare.const import (
    CONF_REMOVE_FOOD_AFTER_HOURS,
    DEFAULT_REMOVE_FOOD_AFTER_HOURS,
)
from custom_components.lizardcare.food_removal import (
    FoodRemovalStatus,
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
        remove_after_hours=4,
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
    assert get_food_removal_settings(entry).remove_after_hours == 6


def test_invalid_or_missing_delay_uses_default() -> None:
    """Old entries without a usable delay load with a safe default."""
    for options in ({}, {CONF_REMOVE_FOOD_AFTER_HOURS: -1}):
        entry = SimpleNamespace(options=options)
        assert (
            get_food_removal_settings(entry).remove_after_hours
            == DEFAULT_REMOVE_FOOD_AFTER_HOURS
        )
