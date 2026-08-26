"""Shared food-removal timing helpers for Lizard Care."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.util import dt as dt_util

from .const import FOOD_REMOVAL_BASIS_ACTUAL


@dataclass(frozen=True, slots=True)
class FoodRemovalTiming:
    """Resolved timing for one feeding event."""

    reminder_at: datetime
    notification_at: datetime | None


def calculate_food_removal_timing(
    last_fed: datetime,
    *,
    delay_hours: int,
    basis: str,
    feeding_reminder_time: time,
    now: datetime,
) -> FoodRemovalTiming:
    """Resolve status timing while preserving late-feeding fallback behavior."""
    actual_due = dt_util.as_utc(
        last_fed + timedelta(hours=delay_hours)
    )
    if basis == FOOD_REMOVAL_BASIS_ACTUAL:
        return FoodRemovalTiming(actual_due, actual_due)

    local_fed = dt_util.as_local(last_fed)
    anchor_date = local_fed.date()
    if local_fed.timetz().replace(tzinfo=None) < feeding_reminder_time:
        anchor_date -= timedelta(days=1)
    local_anchor = datetime.combine(
        anchor_date,
        feeding_reminder_time,
        tzinfo=dt_util.get_default_time_zone(),
    )
    scheduled_due = dt_util.as_utc(
        local_anchor + timedelta(hours=delay_hours)
    )
    now = dt_util.as_utc(now)
    if scheduled_due > now:
        return FoodRemovalTiming(scheduled_due, scheduled_due)
    if actual_due > now:
        return FoodRemovalTiming(actual_due, actual_due)

    # Both candidates are stale. The notification manager intentionally avoids
    # an immediate initial alert, while status still uses the newer due time.
    return FoodRemovalTiming(max(scheduled_due, actual_due), None)
