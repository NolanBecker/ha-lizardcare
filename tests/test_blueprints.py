"""Structural checks for the bundled automation blueprints."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

BLUEPRINT_DIR = (
    Path(__file__).parents[1] / "blueprints" / "automation" / "lizardcare"
)


class BlueprintLoader(yaml.SafeLoader):
    """Parse Home Assistant's blueprint input tag for structural tests."""


BlueprintLoader.add_constructor(
    "!input",
    lambda loader, node: {"input": loader.construct_scalar(node)},
)


def test_blueprints_are_valid_yaml_with_automation_schema() -> None:
    """Both distributable files contain their required top-level sections."""
    expected = {"care_reminders.yaml", "food_removal_reminder.yaml"}
    paths = set(BLUEPRINT_DIR.glob("*.yaml"))
    assert {path.name for path in paths} == expected
    for path in paths:
        document = yaml.load(path.read_text(), Loader=BlueprintLoader)
        assert document["blueprint"]["domain"] == "automation"
        assert document["triggers"]
        assert document["actions"]


def test_care_reminder_blueprint_trigger_architecture() -> None:
    """Due-today, immediate-overdue, repeat, and recovery triggers coexist."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    trigger_ids = {trigger["id"] for trigger in document["triggers"]}
    assert trigger_ids == {
        "due_today",
        "feeding_overdue",
        "spot_clean_overdue",
        "full_clean_overdue",
        "overdue_repeat",
        "startup",
    }
    assert not any("repeat" in action for action in document["actions"])


def test_care_reminder_blueprint_inputs_remain_compatible() -> None:
    """Existing automations retain all previously configurable input names."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]
    assert {
        "feeding_status",
        "spot_clean_status",
        "full_clean_status",
        "notification_target",
        "reminder_time",
        "feeding_enabled",
        "spot_clean_enabled",
        "full_clean_enabled",
        "due_today_enabled",
        "overdue_enabled",
        "feeding_overdue_repeat_interval",
        "feeding_overdue_repeat_interval_unit",
        "cleaning_overdue_repeat_interval",
        "cleaning_overdue_repeat_interval_unit",
        "pet_name_override",
        "notification_title_prefix",
    } <= inputs.keys()


def test_separate_repeat_interval_inputs() -> None:
    """Category-specific value and unit controls have clear defaults."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]

    for prefix, expected_default in (
        ("feeding", 1),
        ("cleaning", 24),
    ):
        repeat_input = inputs[f"{prefix}_overdue_repeat_interval"]
        selector = repeat_input["selector"]["number"]
        assert repeat_input["default"] == expected_default
        assert selector["min"] == 1
        assert selector["max"] == 10080
        assert selector["step"] == 1
        unit_input = inputs[f"{prefix}_overdue_repeat_interval_unit"]
        assert unit_input["default"] == "hours"
        assert {option["value"] for option in unit_input["selector"]["select"]["options"]} == {
            "minutes",
            "hours",
        }


@pytest.mark.parametrize(
    ("value", "unit", "expected_minutes"),
    [
        (30, "minutes", 30),
        (1, "hours", 60),
        (2, "hours", 120),
        (24, "hours", 1440),
        (48, "hours", 2880),
    ],
)
def test_repeat_interval_resolution(
    value: int, unit: str, expected_minutes: int
) -> None:
    """Minute values remain unchanged and hour values normalize to minutes."""
    interval_minutes = _normalize_interval(value, unit)
    assert interval_minutes == expected_minutes


def _normalize_interval(value: int, unit: str) -> int:
    """Mirror the blueprint's shared value/unit normalization."""
    return value * 60 if unit == "hours" else value


def test_feeding_and_cleaning_intervals_normalize_independently() -> None:
    """Each category can use a different value and unit."""
    feeding_minutes = _normalize_interval(30, "minutes")
    cleaning_minutes = _normalize_interval(24, "hours")

    assert feeding_minutes == 30
    assert cleaning_minutes == 1440


def test_repeat_calculation_uses_wall_clock_boundaries() -> None:
    """Every care branch uses the shared wall-clock boundary calculation."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    assert "feeding_repeat_value | int * 60" in blueprint
    assert "cleaning_repeat_value | int * 60" in blueprint
    assert "today_at(configured_reminder_time)" in blueprint
    assert "minutes_from_reminder_anchor" in blueprint
    assert blueprint.count("is_feeding_repeat_boundary and") == 1
    assert blueprint.count("is_cleaning_repeat_boundary and") == 2
    assert blueprint.count(
        "trigger.id in ['due_today', 'overdue_repeat']"
    ) == 3
    assert blueprint.count("not automation_ran_this_minute") == 6
    assert blueprint.count("elapsed >= 60") == 3
    assert "\n  repeat_hours:" not in blueprint


def test_removed_legacy_inputs_are_absent() -> None:
    """The blueprint schema no longer exposes compatibility-only controls."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]

    assert "separate_overdue_repeat_intervals" not in inputs
    assert "overdue_repeat_interval_minutes" not in inputs
    assert "overdue_repeat_interval" not in inputs


def _is_boundary(
    value: datetime,
    interval_minutes: int,
    anchor_hour: int = 16,
    anchor_minute: int = 0,
) -> bool:
    """Mirror the blueprint's Reminder Time anchored calculation."""
    anchor_minutes = anchor_hour * 60 + anchor_minute
    wall_clock_minutes = (
        value.toordinal() * 1440 + value.hour * 60 + value.minute
    )
    return (wall_clock_minutes - anchor_minutes) % interval_minutes == 0


@pytest.mark.parametrize(
    ("interval", "boundary", "between"),
    [
        (60, (17, 0), (16, 23)),
        (720, (4, 0), (8, 15)),
        (1440, (16, 0), (0, 0)),
    ],
)
def test_repeat_intervals_align_to_reminder_time(
    interval: int,
    boundary: tuple[int, int],
    between: tuple[int, int],
) -> None:
    """Supported intervals align predictably from a 4 PM Reminder Time."""
    timezone = ZoneInfo("America/Chicago")
    assert _is_boundary(
        datetime(2026, 9, 3, *boundary, tzinfo=timezone), interval
    )
    assert not _is_boundary(
        datetime(2026, 9, 3, *between, tzinfo=timezone), interval
    )


def test_due_today_and_recovery_triggers_are_unchanged() -> None:
    """Wall-clock repeats retain daily, immediate, and startup paths."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    assert "trigger.id == 'due_today'" in blueprint
    assert "trigger.id == 'feeding_overdue'" in blueprint
    assert "trigger.id == 'spot_clean_overdue'" in blueprint
    assert "trigger.id == 'full_clean_overdue'" in blueprint
    assert blueprint.count("trigger.id == 'startup'") == 3


def test_feeding_and_cleaning_share_anchor_with_different_intervals() -> None:
    """Feeding can repeat hourly while cleaning repeats daily from 4 PM."""
    timezone = ZoneInfo("America/Chicago")
    five_pm = datetime(2026, 9, 3, 17, 0, tzinfo=timezone)
    next_day_four_pm = datetime(2026, 9, 4, 16, 0, tzinfo=timezone)

    assert _is_boundary(five_pm, 60)
    assert not _is_boundary(five_pm, 1440)
    assert _is_boundary(next_day_four_pm, 60)
    assert _is_boundary(next_day_four_pm, 1440)


def test_daily_anchor_stays_at_same_local_time_across_dst() -> None:
    """Calendar-minute arithmetic keeps a daily boundary at 4 PM local."""
    timezone = ZoneInfo("America/Chicago")
    before_fall_back = datetime(2026, 10, 31, 16, 0, tzinfo=timezone)
    after_fall_back = datetime(2026, 11, 1, 16, 0, tzinfo=timezone)

    assert before_fall_back.utcoffset() != after_fall_back.utcoffset()
    assert _is_boundary(before_fall_back, 1440)
    assert _is_boundary(after_fall_back, 1440)
