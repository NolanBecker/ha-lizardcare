"""Vacation calendar configuration helpers for Lizard Care."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry

from .const import CONF_VACATION_CALENDAR


def get_vacation_calendar(entry: ConfigEntry) -> str | None:
    """Return the configured calendar, with options overriding entry data."""
    value = entry.options.get(
        CONF_VACATION_CALENDAR,
        entry.data.get(CONF_VACATION_CALENDAR),
    )
    if not isinstance(value, str) or not (calendar := value.strip()):
        return None
    return calendar
