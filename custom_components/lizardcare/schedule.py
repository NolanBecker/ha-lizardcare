"""Care schedule helpers for Lizard Care."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    DEFAULT_FEEDING_INTERVAL_DAYS,
    DEFAULT_FULL_CLEAN_INTERVAL_DAYS,
    DEFAULT_SPOT_CLEAN_INTERVAL_DAYS,
)


class CareStatus(StrEnum):
    """Possible calculated care schedule states."""

    NOT_DUE = "not_due"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


@dataclass(frozen=True, slots=True)
class CareSchedule:
    """Resolved care intervals for one pet."""

    feeding_interval_days: int
    spot_clean_interval_days: int
    full_clean_interval_days: int


def _positive_option(entry: ConfigEntry, key: str, default: int) -> int:
    """Return a positive integer option or its default."""
    value = entry.options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


def get_care_schedule(entry: ConfigEntry) -> CareSchedule:
    """Resolve current schedule options, including legacy defaults."""
    return CareSchedule(
        feeding_interval_days=_positive_option(
            entry,
            CONF_FEEDING_INTERVAL_DAYS,
            DEFAULT_FEEDING_INTERVAL_DAYS,
        ),
        spot_clean_interval_days=_positive_option(
            entry,
            CONF_SPOT_CLEAN_INTERVAL_DAYS,
            DEFAULT_SPOT_CLEAN_INTERVAL_DAYS,
        ),
        full_clean_interval_days=_positive_option(
            entry,
            CONF_FULL_CLEAN_INTERVAL_DAYS,
            DEFAULT_FULL_CLEAN_INTERVAL_DAYS,
        ),
    )


def calculate_next_due(
    last_completed: datetime | None, interval_days: int
) -> datetime | None:
    """Calculate the next due timestamp for a care action."""
    if last_completed is None:
        return None
    return last_completed + timedelta(days=interval_days)


def calculate_care_status(
    next_due: datetime | None, today: date | None = None
) -> CareStatus | None:
    """Calculate care status using Home Assistant's local calendar day."""
    if next_due is None:
        return None

    local_today = today or dt_util.now().date()
    due_date = dt_util.as_local(next_due).date()
    if due_date < local_today:
        return CareStatus.OVERDUE
    if due_date == local_today:
        return CareStatus.DUE_TODAY
    return CareStatus.NOT_DUE
