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
        "separate_overdue_repeat_intervals",
        "feeding_overdue_repeat_interval_minutes",
        "cleaning_overdue_repeat_interval_minutes",
        "overdue_repeat_interval",
        "overdue_repeat_interval_minutes",
        "pet_name_override",
        "notification_title_prefix",
    } <= inputs.keys()


def test_care_reminder_minute_interval_selector() -> None:
    """The primary repeat input supports quarter-hour through weekly values."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]
    minute_input = inputs["overdue_repeat_interval_minutes"]
    selector = minute_input["selector"]["number"]

    assert minute_input["default"] == 60
    assert selector == {
        "min": 15,
        "max": 10080,
        "step": 15,
        "unit_of_measurement": "minutes",
        "mode": "box",
    }


def test_legacy_hour_interval_remains_backward_compatible() -> None:
    """Saved hourly values remain available while omitted values use minutes."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    legacy_input = document["blueprint"]["input"][
        "overdue_repeat_interval"
    ]

    assert legacy_input["default"] == 0
    assert legacy_input["selector"]["number"]["unit_of_measurement"] == "hours"


def test_separate_repeat_interval_inputs() -> None:
    """Category-specific controls have clear defaults and minute selectors."""
    path = BLUEPRINT_DIR / "care_reminders.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]

    assert inputs["separate_overdue_repeat_intervals"]["default"] is False
    for key, expected_default in (
        ("feeding_overdue_repeat_interval_minutes", 60),
        ("cleaning_overdue_repeat_interval_minutes", 1440),
    ):
        repeat_input = inputs[key]
        selector = repeat_input["selector"]["number"]
        assert repeat_input["default"] == expected_default
        assert selector["min"] == 15
        assert selector["max"] == 10080
        assert selector["step"] == 15
        assert selector["unit_of_measurement"] == "minutes"


@pytest.mark.parametrize(
    ("minutes", "legacy_hours", "expected_minutes"),
    [
        (30, 0, 30),
        (60, 0, 60),
        (90, 0, 90),
        (240, 0, 240),
        (60, 1, 60),
    ],
)
def test_repeat_interval_resolution(
    minutes: int,
    legacy_hours: int,
    expected_minutes: int,
) -> None:
    """Minute intervals work and a saved legacy hour value takes precedence."""
    interval_minutes = legacy_hours * 60 if legacy_hours > 0 else minutes
    assert interval_minutes == expected_minutes


def test_repeat_calculation_uses_wall_clock_boundaries() -> None:
    """Every care branch uses the shared wall-clock boundary calculation."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    assert "legacy_repeat_hours | int * 60" in blueprint
    assert "now().toordinal() * 1440" in blueprint
    assert blueprint.count("is_feeding_repeat_boundary and") == 1
    assert blueprint.count("is_cleaning_repeat_boundary and") == 2
    assert blueprint.count("not automation_ran_this_minute") == 6
    assert blueprint.count("elapsed >= 60") == 3
    assert "\n  repeat_hours:" not in blueprint


@pytest.mark.parametrize(
    (
        "separate",
        "global_minutes",
        "legacy_hours",
        "feeding_minutes",
        "cleaning_minutes",
        "expected_feeding",
        "expected_cleaning",
    ),
    [
        (True, 60, 0, 60, 1440, 60, 1440),
        (False, 30, 0, 60, 1440, 30, 30),
        (False, 60, 1, 60, 1440, 60, 60),
    ],
)
def test_category_repeat_interval_resolution(
    separate: bool,
    global_minutes: int,
    legacy_hours: int,
    feeding_minutes: int,
    cleaning_minutes: int,
    expected_feeding: int,
    expected_cleaning: int,
) -> None:
    """Separate settings are opt-in and legacy global settings stay stable."""
    global_interval = (
        legacy_hours * 60 if legacy_hours > 0 else global_minutes
    )
    resolved_feeding = feeding_minutes if separate else global_interval
    resolved_cleaning = cleaning_minutes if separate else global_interval
    assert resolved_feeding == expected_feeding
    assert resolved_cleaning == expected_cleaning


def _is_boundary(value: datetime, interval_minutes: int) -> bool:
    """Mirror the blueprint's local wall-clock boundary calculation."""
    wall_clock_minutes = (
        value.toordinal() * 1440 + value.hour * 60 + value.minute
    )
    return wall_clock_minutes % interval_minutes == 0


@pytest.mark.parametrize(
    ("interval", "boundary", "between"),
    [
        (15, (11, 15), (11, 7)),
        (30, (11, 30), (11, 17)),
        (60, (12, 0), (11, 17)),
        (90, (13, 30), (12, 15)),
        (240, (16, 0), (15, 0)),
    ],
)
def test_repeat_intervals_align_to_local_wall_clock(
    interval: int,
    boundary: tuple[int, int],
    between: tuple[int, int],
) -> None:
    """Supported intervals align predictably from local midnight."""
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
