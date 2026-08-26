"""Derived care information and relative-time helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from homeassistant.util import dt as dt_util


class CareActivity(StrEnum):
    """Tracked care activity types."""

    FED = "fed"
    FOOD_REMOVED = "food_removed"
    SPOT_CLEAN = "spot_clean"
    FULL_CLEAN = "full_clean"


@dataclass(frozen=True, slots=True)
class LastCareActivity:
    """Most recent valid care activity."""

    activity: CareActivity
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class DueDayCounts:
    """Nonnegative local-calendar distance from a due date."""

    days_until_due: int
    days_overdue: int


def find_last_care_activity(
    timestamps: Mapping[CareActivity, datetime | None],
) -> LastCareActivity | None:
    """Return the newest timezone-aware care timestamp."""
    valid: list[tuple[CareActivity, datetime]] = []
    for activity, timestamp in timestamps.items():
        if timestamp is not None and timestamp.tzinfo is not None:
            valid.append((activity, timestamp))
    if not valid:
        return None
    activity, timestamp = max(valid, key=lambda item: item[1])
    return LastCareActivity(activity, timestamp)


def calculate_due_day_counts(
    next_due: datetime | None,
    today: date | None = None,
) -> DueDayCounts | None:
    """Calculate due distance using Home Assistant's local calendar dates."""
    if next_due is None:
        return None
    local_today = today or dt_util.now().date()
    difference = (dt_util.as_local(next_due).date() - local_today).days
    return DueDayCounts(max(difference, 0), max(-difference, 0))


def format_past_relative_time(
    value: datetime,
    now: datetime | None = None,
) -> str:
    """Format a past activity timestamp using useful human granularity."""
    local_value = dt_util.as_local(value)
    local_now = dt_util.as_local(now or dt_util.utcnow())
    elapsed_seconds = max((local_now - local_value).total_seconds(), 0)
    if elapsed_seconds < 60:
        return "Just now"

    day_difference = (local_now.date() - local_value.date()).days
    if day_difference == 1:
        return "Yesterday"
    if day_difference <= 0 and elapsed_seconds < 3600:
        minutes = max(int(elapsed_seconds // 60), 1)
        return f"{minutes} {'minute' if minutes == 1 else 'minutes'} ago"
    if day_difference <= 0:
        hours = max(int(elapsed_seconds // 3600), 1)
        return f"{hours} {'hour' if hours == 1 else 'hours'} ago"
    if day_difference < 14:
        return f"{day_difference} days ago"
    if day_difference < 60:
        weeks = max(round(day_difference / 7), 2)
        return f"{weeks} weeks ago"
    months = max(round(day_difference / 30), 2)
    return f"{months} months ago"


def format_scheduled_relative_time(
    next_due: datetime,
    today: date | None = None,
) -> str:
    """Format a due timestamp using local-calendar terminology."""
    counts = calculate_due_day_counts(next_due, today)
    if counts is None:  # pragma: no cover - guarded by the required argument
        return "Unknown"
    if counts.days_overdue:
        days = counts.days_overdue
        return f"{days} {'day' if days == 1 else 'days'} overdue"
    if counts.days_until_due == 0:
        return "Today"
    if counts.days_until_due == 1:
        return "Tomorrow"
    if counts.days_until_due < 14:
        return f"In {counts.days_until_due} days"
    weeks = max(round(counts.days_until_due / 7), 2)
    return f"In {weeks} weeks"
