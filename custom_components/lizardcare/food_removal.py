"""Derived food-removal timing for Lizard Care."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FOOD_REMOVAL_ANCHOR_TIME,
    CONF_FOOD_REMOVAL_DELAY,
    CONF_FOOD_REMOVAL_DELAY_UNIT,
    CONF_REMOVE_FOOD_AFTER_HOURS,
    DEFAULT_FOOD_REMOVAL_ANCHOR_TIME,
    DEFAULT_FOOD_REMOVAL_DELAY,
    DEFAULT_FOOD_REMOVAL_DELAY_UNIT,
    DEFAULT_REMOVE_FOOD_AFTER_HOURS,
    FOOD_REMOVAL_OVERDUE_AFTER_MINUTES,
    TIME_UNIT_HOURS,
    TIME_UNIT_MINUTES,
)


class FoodRemovalStatus(StrEnum):
    """Possible derived food-removal states."""

    NOT_NEEDED = "not_needed"
    PENDING = "pending"
    DUE = "due"
    OVERDUE = "overdue"


@dataclass(frozen=True, slots=True)
class FoodRemovalSettings:
    """Resolved food-removal care settings for one pet."""

    anchor_time: time
    delay_value: int
    delay_unit: str
    delay_minutes: int


@dataclass(frozen=True, slots=True)
class FoodRemovalResult:
    """Derived state and timing details for the current feeding event."""

    status: FoodRemovalStatus
    due_at: datetime | None
    minutes_until_due: int
    minutes_overdue: int


def get_food_removal_settings(entry: ConfigEntry) -> FoodRemovalSettings:
    """Resolve anchored care timing while accepting the legacy delay key."""
    anchor_value = entry.options.get(
        CONF_FOOD_REMOVAL_ANCHOR_TIME,
        DEFAULT_FOOD_REMOVAL_ANCHOR_TIME,
    )
    if isinstance(anchor_value, str):
        try:
            anchor_value = time.fromisoformat(anchor_value)
        except ValueError:
            anchor_value = None
    if not isinstance(anchor_value, time):
        anchor_value = time.fromisoformat(DEFAULT_FOOD_REMOVAL_ANCHOR_TIME)

    delay_value = entry.options.get(CONF_FOOD_REMOVAL_DELAY)
    delay_unit = entry.options.get(
        CONF_FOOD_REMOVAL_DELAY_UNIT,
        DEFAULT_FOOD_REMOVAL_DELAY_UNIT,
    )
    if delay_unit not in (TIME_UNIT_MINUTES, TIME_UNIT_HOURS):
        delay_unit = DEFAULT_FOOD_REMOVAL_DELAY_UNIT
    if (
        isinstance(delay_value, bool)
        or not isinstance(delay_value, int)
        or delay_value < 1
    ):
        legacy_hours = entry.options.get(
            CONF_REMOVE_FOOD_AFTER_HOURS,
            DEFAULT_REMOVE_FOOD_AFTER_HOURS,
        )
        if (
            isinstance(legacy_hours, bool)
            or not isinstance(legacy_hours, int)
            or legacy_hours < 1
        ):
            legacy_hours = DEFAULT_FOOD_REMOVAL_DELAY
        delay_value = legacy_hours
        delay_unit = TIME_UNIT_HOURS

    delay_minutes = (
        delay_value * 60 if delay_unit == TIME_UNIT_HOURS else delay_value
    )
    return FoodRemovalSettings(
        anchor_time=anchor_value,
        delay_value=delay_value,
        delay_unit=delay_unit,
        delay_minutes=delay_minutes,
    )


def calculate_food_removal_due_at(
    last_fed: datetime,
    delay_minutes: int,
    anchor_time: time,
) -> datetime:
    """Return the UTC removal time anchored to the feeding day's care time."""
    local_fed = dt_util.as_local(last_fed)
    local_anchor = datetime.combine(
        local_fed.date(),
        anchor_time,
        tzinfo=dt_util.get_default_time_zone(),
    )
    return dt_util.as_utc(local_anchor + timedelta(minutes=delay_minutes))


def calculate_food_removal_status(
    *,
    food_in_enclosure: bool,
    last_fed: datetime | None,
    delay_minutes: int,
    anchor_time: time,
    now: datetime | None = None,
) -> FoodRemovalResult:
    """Calculate current food-removal state without notification behavior."""
    if not food_in_enclosure or last_fed is None:
        return FoodRemovalResult(FoodRemovalStatus.NOT_NEEDED, None, 0, 0)

    now = dt_util.as_utc(now or dt_util.utcnow())
    due_at = calculate_food_removal_due_at(
        last_fed,
        delay_minutes,
        anchor_time,
    )
    seconds_from_due = (now - due_at).total_seconds()
    if seconds_from_due < 0:
        return FoodRemovalResult(
            FoodRemovalStatus.PENDING,
            due_at,
            math.ceil(-seconds_from_due / 60),
            0,
        )

    minutes_overdue = max(math.floor(seconds_from_due / 60), 0)
    status = (
        FoodRemovalStatus.OVERDUE
        if minutes_overdue >= FOOD_REMOVAL_OVERDUE_AFTER_MINUTES
        else FoodRemovalStatus.DUE
    )
    return FoodRemovalResult(status, due_at, 0, minutes_overdue)
