"""Structural checks for the bundled automation blueprints."""

from pathlib import Path

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
        "pet_name_override",
        "notification_title_prefix",
    } <= inputs.keys()
