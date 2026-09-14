"""Tests for vacation calendar configuration."""

from types import SimpleNamespace

from custom_components.lizardcare.const import CONF_VACATION_CALENDAR
from custom_components.lizardcare.vacation import get_vacation_calendar


def test_existing_entry_without_calendar_remains_disabled() -> None:
    """Existing pets need no migration and retain normal reminder behavior."""
    entry = SimpleNamespace(data={}, options={})

    assert get_vacation_calendar(entry) is None


def test_options_calendar_overrides_entry_data() -> None:
    """Editable options take precedence over any older data value."""
    entry = SimpleNamespace(
        data={CONF_VACATION_CALENDAR: "calendar.old_vacation"},
        options={CONF_VACATION_CALENDAR: "calendar.vacation"},
    )

    assert get_vacation_calendar(entry) == "calendar.vacation"


def test_blank_calendar_clears_configuration() -> None:
    """An empty option explicitly disables vacation behavior."""
    entry = SimpleNamespace(
        data={CONF_VACATION_CALENDAR: "calendar.old_vacation"},
        options={CONF_VACATION_CALENDAR: ""},
    )

    assert get_vacation_calendar(entry) is None
