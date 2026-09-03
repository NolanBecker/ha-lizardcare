"""Derived food-removal timing for Lizard Care."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_REMOVE_FOOD_AFTER_HOURS,
    DEFAULT_REMOVE_FOOD_AFTER_HOURS,
    FOOD_REMOVAL_OVERDUE_AFTER_MINUTES,
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

    remove_after_hours: int


@dataclass(frozen=True, slots=True)
class FoodRemovalResult:
    """Derived state and timing details for the current feeding event."""

    status: FoodRemovalStatus
    due_at: datetime | None
    minutes_until_due: int
    minutes_overdue: int


def get_food_removal_settings(entry: ConfigEntry) -> FoodRemovalSettings:
    """Resolve care timing while accepting the legacy option key."""
    value = entry.options.get(
        CONF_REMOVE_FOOD_AFTER_HOURS,
        DEFAULT_REMOVE_FOOD_AFTER_HOURS,
    )
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        value = DEFAULT_REMOVE_FOOD_AFTER_HOURS
    return FoodRemovalSettings(remove_after_hours=value)


def calculate_food_removal_due_at(
    last_fed: datetime,
    remove_after_hours: int,
) -> datetime:
    """Return the UTC removal time anchored to the actual feeding event."""
    return dt_util.as_utc(last_fed) + timedelta(hours=remove_after_hours)


def calculate_food_removal_status(
    *,
    food_in_enclosure: bool,
    last_fed: datetime | None,
    remove_after_hours: int,
    now: datetime | None = None,
) -> FoodRemovalResult:
    """Calculate current food-removal state without notification behavior."""
    if not food_in_enclosure or last_fed is None:
        return FoodRemovalResult(FoodRemovalStatus.NOT_NEEDED, None, 0, 0)

    now = dt_util.as_utc(now or dt_util.utcnow())
    due_at = calculate_food_removal_due_at(last_fed, remove_after_hours)
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
