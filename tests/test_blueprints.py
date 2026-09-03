"""Structural checks for the bundled automation blueprints."""

from pathlib import Path

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


@pytest.mark.parametrize(
    ("minutes", "legacy_hours", "expected_seconds"),
    [
        (30, 0, 30 * 60),
        (60, 0, 60 * 60),
        (90, 0, 90 * 60),
        (240, 0, 4 * 60 * 60),
        (60, 1, 60 * 60),
    ],
)
def test_repeat_interval_resolution(
    minutes: int,
    legacy_hours: int,
    expected_seconds: int,
) -> None:
    """Minute intervals work and a saved legacy hour value takes precedence."""
    interval_seconds = (
        legacy_hours * 3600 if legacy_hours > 0 else minutes * 60
    )
    assert interval_seconds == expected_seconds


def test_repeat_calculation_uses_resolved_seconds() -> None:
    """Every care branch uses the shared backward-compatible interval."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    assert "legacy_repeat_hours | int * 3600" in blueprint
    assert "repeat_minutes | int * 60" in blueprint
    assert blueprint.count(
        "{% set interval = repeat_interval_seconds | int %}"
    ) == 3
    assert "\n  repeat_hours:" not in blueprint
