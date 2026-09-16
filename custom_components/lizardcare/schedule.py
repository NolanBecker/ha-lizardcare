"""Care schedule helpers for Lizard Care."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .config import get_config_value
from .const import (
    CLEANING_SCHEDULE_ALTERNATING,
    CLEANING_SCHEDULE_INTERVAL,
    CLEANING_SCHEDULE_MONTHLY,
    CONF_ALTERNATING_ANCHOR_TYPE,
    CONF_ALTERNATING_CLEANING_ANCHOR_DATE,
    CONF_ALTERNATING_CLEANING_INTERVAL_DAYS,
    CONF_CLEANING_CYCLE_ANCHOR,
    CONF_CLEANING_DAY_OF_MONTH,
    CONF_CLEANING_SCHEDULE_MODE,
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FULL_CLEAN_EVERY,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    CONF_SPOT_CLEAN_ENABLED,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    DEFAULT_ALTERNATING_ANCHOR_TYPE,
    DEFAULT_ALTERNATING_CLEANING_INTERVAL_DAYS,
    DEFAULT_CLEANING_DAY_OF_MONTH,
    DEFAULT_CLEANING_SCHEDULE_MODE,
    DEFAULT_FEEDING_INTERVAL_DAYS,
    DEFAULT_FULL_CLEAN_EVERY,
    DEFAULT_FULL_CLEAN_INTERVAL_DAYS,
    DEFAULT_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    DEFAULT_SPOT_CLEAN_ENABLED,
    DEFAULT_SPOT_CLEAN_INTERVAL_DAYS,
)


class CareStatus(StrEnum):
    """Possible calculated care schedule states."""

    NOT_DUE = "not_due"
    DUE_TODAY = "due_today"
    OVERDUE = "overdue"
    DISABLED = "disabled"


class OverallCareStatus(StrEnum):
    """Possible aggregate care states."""

    ALL_GOOD = "all_good"
    ATTENTION_NEEDED = "attention_needed"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


class CleaningOccurrenceType(StrEnum):
    """Care action assigned to one monthly occurrence."""

    SPOT_CLEAN = "spot_clean"
    FULL_CLEAN = "full_clean"


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
    spot_clean_enabled: bool
    spot_clean_interval_days: int
    full_clean_interval_days: int
    full_clean_satisfies_spot_clean: bool
    cleaning_schedule_mode: str
    cleaning_day_of_month: int
    full_clean_every: int
    cleaning_cycle_anchor: date
    alternating_interval_days: int = 45
    alternating_anchor_date: date = date(1970, 1, 1)
    alternating_anchor_type: CleaningOccurrenceType = (
        CleaningOccurrenceType.SPOT_CLEAN
    )


@dataclass(frozen=True, slots=True)
class MonthlyCleaningPlan:
    """Next deterministic dates in a monthly cleaning cycle."""

    next_cleaning: datetime
    cleaning_occurrence_type: CleaningOccurrenceType
    next_spot_clean: datetime | None
    next_full_clean: datetime
    occurrence_number: int


@dataclass(frozen=True, slots=True)
class AlternatingCleaningPlan:
    """The authoritative next slot in a fixed alternating cadence."""

    next_cleaning: datetime
    cleaning_occurrence_type: CleaningOccurrenceType
    occurrence_number: int


def _positive_option(entry: ConfigEntry, key: str, default: int) -> int:
    """Return a positive integer option or its default."""
    value = get_config_value(entry, key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return default
    return value


def _boolean_option(entry: ConfigEntry, key: str, default: bool) -> bool:
    """Return a boolean schedule option or its default."""
    value = get_config_value(entry, key, default)
    return value if isinstance(value, bool) else default


def _cleaning_anchor(entry: ConfigEntry, day_of_month: int) -> date:
    """Resolve the persisted cycle anchor or a stable upcoming default."""
    value = get_config_value(entry, CONF_CLEANING_CYCLE_ANCHOR)
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            value = None
    if isinstance(value, date):
        return monthly_occurrence_date(value, 1, day_of_month)

    today = dt_util.now().date()
    this_month = monthly_occurrence_date(today, 1, day_of_month)
    if this_month >= today:
        return this_month
    return monthly_occurrence_date(this_month, 2, day_of_month)


def _date_option(entry: ConfigEntry, key: str, default: date) -> date:
    """Resolve an ISO date option without breaking older entries."""
    value = get_config_value(entry, key, default)
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return default
    return value if isinstance(value, date) else default


def get_care_schedule(entry: ConfigEntry) -> CareSchedule:
    """Resolve current schedule options, including legacy defaults."""
    mode = get_config_value(
        entry,
        CONF_CLEANING_SCHEDULE_MODE,
        DEFAULT_CLEANING_SCHEDULE_MODE,
    )
    if mode not in (
        CLEANING_SCHEDULE_INTERVAL,
        CLEANING_SCHEDULE_MONTHLY,
        CLEANING_SCHEDULE_ALTERNATING,
    ):
        mode = DEFAULT_CLEANING_SCHEDULE_MODE
    cleaning_day = _positive_option(
        entry,
        CONF_CLEANING_DAY_OF_MONTH,
        DEFAULT_CLEANING_DAY_OF_MONTH,
    )
    if cleaning_day > 31:
        cleaning_day = DEFAULT_CLEANING_DAY_OF_MONTH
    full_clean_every = _positive_option(
        entry,
        CONF_FULL_CLEAN_EVERY,
        DEFAULT_FULL_CLEAN_EVERY,
    )
    alternating_type = get_config_value(
        entry,
        CONF_ALTERNATING_ANCHOR_TYPE,
        DEFAULT_ALTERNATING_ANCHOR_TYPE,
    )
    if alternating_type not in (
        CleaningOccurrenceType.SPOT_CLEAN,
        CleaningOccurrenceType.FULL_CLEAN,
    ):
        alternating_type = DEFAULT_ALTERNATING_ANCHOR_TYPE
    return CareSchedule(
        feeding_interval_days=_positive_option(
            entry,
            CONF_FEEDING_INTERVAL_DAYS,
            DEFAULT_FEEDING_INTERVAL_DAYS,
        ),
        spot_clean_enabled=_boolean_option(
            entry,
            CONF_SPOT_CLEAN_ENABLED,
            DEFAULT_SPOT_CLEAN_ENABLED,
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
        cleaning_schedule_mode=mode,
        cleaning_day_of_month=cleaning_day,
        full_clean_every=full_clean_every,
        cleaning_cycle_anchor=_cleaning_anchor(entry, cleaning_day),
        alternating_interval_days=_positive_option(
            entry,
            CONF_ALTERNATING_CLEANING_INTERVAL_DAYS,
            DEFAULT_ALTERNATING_CLEANING_INTERVAL_DAYS,
        ),
        alternating_anchor_date=_date_option(
            entry,
            CONF_ALTERNATING_CLEANING_ANCHOR_DATE,
            dt_util.now().date(),
        ),
        alternating_anchor_type=CleaningOccurrenceType(alternating_type),
    )


def alternating_occurrence_type(
    occurrence_number: int,
    anchor_type: CleaningOccurrenceType,
) -> CleaningOccurrenceType:
    """Return the task type for a one-based alternating occurrence."""
    if occurrence_number % 2 == 1:
        return anchor_type
    return (
        CleaningOccurrenceType.FULL_CLEAN
        if anchor_type is CleaningOccurrenceType.SPOT_CLEAN
        else CleaningOccurrenceType.SPOT_CLEAN
    )


def alternating_schedule_definition(schedule: CareSchedule) -> str | None:
    """Return the persisted identity of the effective alternating cadence."""
    if schedule.cleaning_schedule_mode != CLEANING_SCHEDULE_ALTERNATING:
        return None
    return "|".join(
        (
            schedule.alternating_anchor_date.isoformat(),
            str(schedule.alternating_interval_days),
            schedule.alternating_anchor_type.value,
        )
    )


def alternating_occurrence_date(
    anchor: date,
    occurrence_number: int,
    interval_days: int,
) -> date:
    """Return a fixed-cadence date using exact calendar-day increments."""
    return anchor + timedelta(days=(occurrence_number - 1) * interval_days)


def first_alternating_occurrence_after(
    value: date,
    schedule: CareSchedule,
) -> int:
    """Return the first occurrence whose date is strictly after value."""
    elapsed = (value - schedule.alternating_anchor_date).days
    if elapsed < 0:
        return 1
    return elapsed // schedule.alternating_interval_days + 2


def calculate_alternating_cleaning_plan(
    schedule: CareSchedule,
    completed_occurrence: int | None,
) -> AlternatingCleaningPlan:
    """Calculate the next fixed slot from separately persisted progression."""
    occurrence = max(0, completed_occurrence or 0) + 1
    due_date = alternating_occurrence_date(
        schedule.alternating_anchor_date,
        occurrence,
        schedule.alternating_interval_days,
    )
    local_value = datetime.combine(
        due_date,
        time.min,
        tzinfo=dt_util.get_default_time_zone(),
    )
    return AlternatingCleaningPlan(
        next_cleaning=dt_util.as_utc(local_value),
        cleaning_occurrence_type=alternating_occurrence_type(
            occurrence,
            schedule.alternating_anchor_type,
        ),
        occurrence_number=occurrence,
    )


def monthly_occurrence_date(
    anchor: date,
    occurrence_number: int,
    day_of_month: int,
) -> date:
    """Return a monthly occurrence, clamping to the month's final day."""
    month_number = anchor.year * 12 + anchor.month - 1 + occurrence_number - 1
    year, zero_based_month = divmod(month_number, 12)
    month = zero_based_month + 1
    day = min(day_of_month, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def monthly_occurrence_type(
    occurrence_number: int,
    full_clean_every: int,
) -> CleaningOccurrenceType:
    """Return the deterministic task type for one occurrence."""
    if occurrence_number % full_clean_every == 0:
        return CleaningOccurrenceType.FULL_CLEAN
    return CleaningOccurrenceType.SPOT_CLEAN


def _month_difference(value: date, anchor: date) -> int:
    """Return whole calendar months between two dates' months."""
    return (value.year - anchor.year) * 12 + value.month - anchor.month


def completion_occurrence_number(
    completed_at: datetime | None,
    schedule: CareSchedule,
    *,
    early_window_days: int = 7,
) -> int | None:
    """Map a completion to its nearest eligible calendar occurrence."""
    if completed_at is None:
        return None
    completed_date = dt_util.as_local(completed_at).date()
    same_month_number = (
        _month_difference(completed_date, schedule.cleaning_cycle_anchor) + 1
    )
    same_month_date = monthly_occurrence_date(
        schedule.cleaning_cycle_anchor,
        same_month_number,
        schedule.cleaning_day_of_month,
    )
    if completed_date < same_month_date:
        previous_number = same_month_number - 1
        next_number = same_month_number
        next_date = same_month_date
    else:
        previous_number = same_month_number
        next_number = same_month_number + 1
        next_date = monthly_occurrence_date(
            schedule.cleaning_cycle_anchor,
            next_number,
            schedule.cleaning_day_of_month,
        )
    if next_number >= 1 and (next_date - completed_date).days <= early_window_days:
        return next_number
    return previous_number if previous_number >= 1 else None


def calculate_monthly_cleaning_plan(
    schedule: CareSchedule,
    last_spot_clean: datetime | None,
    last_full_clean: datetime | None,
) -> MonthlyCleaningPlan:
    """Calculate upcoming cleaning tasks without completion-date drift."""
    completed_occurrences: list[int] = []
    spot_occurrence = completion_occurrence_number(last_spot_clean, schedule)
    if spot_occurrence is not None and monthly_occurrence_type(
        spot_occurrence, schedule.full_clean_every
    ) is CleaningOccurrenceType.SPOT_CLEAN:
        completed_occurrences.append(spot_occurrence)
    full_occurrence = completion_occurrence_number(last_full_clean, schedule)
    if full_occurrence is not None and (
        monthly_occurrence_type(
            full_occurrence,
            schedule.full_clean_every,
        )
        is CleaningOccurrenceType.FULL_CLEAN
        or schedule.full_clean_satisfies_spot_clean
    ):
        completed_occurrences.append(full_occurrence)

    next_number = max(completed_occurrences, default=0) + 1
    next_type = monthly_occurrence_type(next_number, schedule.full_clean_every)
    next_spot_number = (
        None
        if schedule.full_clean_every == 1
        else (
            next_number + 1
            if next_type is CleaningOccurrenceType.FULL_CLEAN
            else next_number
        )
    )
    next_full_number = (
        (next_number + schedule.full_clean_every - 1)
        // schedule.full_clean_every
        * schedule.full_clean_every
    )

    def as_datetime(occurrence_number: int) -> datetime:
        occurrence_date = monthly_occurrence_date(
            schedule.cleaning_cycle_anchor,
            occurrence_number,
            schedule.cleaning_day_of_month,
        )
        local_value = datetime.combine(
            occurrence_date,
            time.min,
            tzinfo=dt_util.get_default_time_zone(),
        )
        return dt_util.as_utc(local_value)

    return MonthlyCleaningPlan(
        next_cleaning=as_datetime(next_number),
        cleaning_occurrence_type=next_type,
        next_spot_clean=(
            as_datetime(next_spot_number)
            if next_spot_number is not None
            else None
        ),
        next_full_clean=as_datetime(next_full_number),
        occurrence_number=next_number,
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
