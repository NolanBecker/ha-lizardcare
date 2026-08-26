"""Care schedule helpers for Lizard Care."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    DEFAULT_FEEDING_INTERVAL_DAYS,
    DEFAULT_FULL_CLEAN_INTERVAL_DAYS,
    DEFAULT_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    DEFAULT_SPOT_CLEAN_INTERVAL_DAYS,
)


class CareStatus(StrEnum):
    """Possible calculated care schedule states."""

    NOT_DUE = "not_due"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"


class OverallCareStatus(StrEnum):
    """Possible aggregate care states."""

    ALL_GOOD = "all_good"
    ATTENTION_NEEDED = "attention_needed"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OverallCareResult:
    """Calculated overall state and its contributing items."""

    status: OverallCareStatus
    attention_items: tuple[str, ...]
    overdue_items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CareSchedule:
    """Resolved care intervals for one pet."""

    feeding_interval_days: int
    spot_clean_interval_days: int
    full_clean_interval_days: int
    full_clean_satisfies_spot_clean: bool


def _positive_option(entry: ConfigEntry, key: str, default: int) -> int:
    """Return a positive integer option or its default."""
    value = entry.options.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


def _boolean_option(entry: ConfigEntry, key: str, default: bool) -> bool:
    """Return a boolean schedule option or its default."""
    value = entry.options.get(key, default)
    return value if isinstance(value, bool) else default


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
        full_clean_satisfies_spot_clean=_boolean_option(
            entry,
            CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
            DEFAULT_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
        ),
    )


def calculate_effective_last_spot_clean(
    last_spot_clean: datetime | None,
    last_full_clean: datetime | None,
    *,
    full_clean_satisfies_spot_clean: bool,
) -> datetime | None:
    """Return the newest event satisfying the spot-clean schedule."""
    if not full_clean_satisfies_spot_clean or last_full_clean is None:
        return last_spot_clean
    if last_spot_clean is None:
        return last_full_clean
    return max(last_spot_clean, last_full_clean)


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


def calculate_overall_care_status(
    item_statuses: Mapping[str, CareStatus | None],
) -> OverallCareResult:
    """Combine individual states, giving known actionable states priority."""
    attention_items = tuple(
        key
        for key, status in item_statuses.items()
        if status is CareStatus.DUE_TODAY
    )
    overdue_items = tuple(
        key
        for key, status in item_statuses.items()
        if status is CareStatus.OVERDUE
    )
    if overdue_items:
        overall = OverallCareStatus.OVERDUE
    elif attention_items:
        overall = OverallCareStatus.ATTENTION_NEEDED
    elif any(status is None for status in item_statuses.values()):
        overall = OverallCareStatus.UNKNOWN
    else:
        overall = OverallCareStatus.ALL_GOOD
    return OverallCareResult(overall, attention_items, overdue_items)
