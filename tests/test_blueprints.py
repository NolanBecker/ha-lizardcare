"""Structural checks for the bundled automation blueprints."""

from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

BLUEPRINT_DIR = (
    Path(__file__).parents[1] / "blueprints" / "automation" / "lizardcare"
)
LOCAL_TZ = ZoneInfo("America/Chicago")


def _local_datetime(*args: int) -> datetime:
    """Return a timezone-aware local test datetime."""
    return datetime(*args, tzinfo=LOCAL_TZ)


class BlueprintLoader(yaml.SafeLoader):
    """Parse Home Assistant's blueprint input tag for structural tests."""


BlueprintLoader.add_constructor(
    "!input",
    lambda loader, node: {"input": loader.construct_scalar(node)},
)


def test_blueprints_are_valid_yaml_with_automation_schema() -> None:
    """Both distributable files contain their required top-level sections."""
    expected = {
        "care_reminders.yaml",
        "food_removal_reminder.yaml",
        "vacation_care_reminder.yaml",
    }
    paths = set(BLUEPRINT_DIR.glob("*.yaml"))
    assert {path.name for path in paths} == expected
    for path in paths:
        document = yaml.load(path.read_text(), Loader=BlueprintLoader)
        assert document["blueprint"]["domain"] == "automation"
        assert document["triggers"]
        assert document["actions"]


def test_food_removal_blueprint_uses_event_driven_architecture() -> None:
    """Food removal uses immediate, boundary, periodic, and recovery triggers."""
    path = BLUEPRINT_DIR / "food_removal_reminder.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    trigger_ids = {trigger["id"] for trigger in document["triggers"]}

    assert trigger_ids == {
        "due",
        "overdue",
        "overdue_progression",
        "reminder_boundary",
        "overdue_repeat",
        "startup",
        "notification_action",
        "care_completed",
    }
    assert "delay:" not in path.read_text()


def test_food_removal_blueprint_inputs_and_defaults() -> None:
    """Repeat units and daily window inputs are exposed through selectors."""
    path = BLUEPRINT_DIR / "food_removal_reminder.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]

    assert inputs["reminder_time"]["default"] == "19:00:00"
    assert inputs["overdue_reminder_end_time"]["default"] == "23:00:00"
    assert inputs["food_removal_repeat_interval"]["default"] == 1
    unit_input = inputs["food_removal_repeat_interval_unit"]
    assert unit_input["default"] == "hours"
    assert {
        option["value"]
        for option in unit_input["selector"]["select"]["options"]
    } == {"minutes", "hours"}
    assert "repeat_interval" not in inputs
    assert inputs["vacation_calendar"]["default"] == ""
    assert inputs["notification_services"]["default"] == []
    assert inputs["notification_services"]["selector"]["text"]["multiple"]
    assert inputs["completion_notifications_enabled"]["default"] is True
    assert "completion_message" in inputs


def test_food_removal_blueprint_uses_status_due_at_for_boundaries() -> None:
    """Recurring reminders consume the integration's authoritative due time."""
    blueprint = (
        BLUEPRINT_DIR / "food_removal_reminder.yaml"
    ).read_text()

    assert "state_attr(status_entity, 'due_at')" in blueprint
    assert "minutes_from_due_boundary" in blueprint
    assert "repeat_value | int * 60" in blueprint
    assert "is_within_overdue_window and is_repeat_boundary" in blueprint
    assert blueprint.count("not automation_ran_this_minute") == 3
    assert "trigger.id in ['due', 'overdue'] or" in blueprint
    assert "trigger.id == 'overdue_progression'" in blueprint
    assert "elapsed >= 60" in blueprint
    assert "delay:" not in blueprint


@pytest.mark.parametrize(
    ("value", "unit", "expected_minutes"),
    [
        (30, "minutes", 30),
        (1, "hours", 60),
    ],
)
def test_food_removal_repeat_interval_normalization(
    value: int,
    unit: str,
    expected_minutes: int,
) -> None:
    """Food removal repeat values normalize to one minute representation."""
    assert _normalize_interval(value, unit) == expected_minutes


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
        "notification_action",
        "cleaning_status_changed",
        "care_completed",
    }
    assert "delay:" not in path.read_text()


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
        "notification_services",
        "reminder_time",
        "overdue_reminder_end_time",
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
        "notification_message",
        "dashboard_url",
        "feed_button",
        "spot_clean_button",
        "full_clean_button",
        "vacation_calendar",
        "cleaning_status",
        "completion_notifications_enabled",
        "feeding_completion_message",
        "spot_clean_completion_message",
        "full_clean_completion_message",
    } <= inputs.keys()
    assert inputs["cleaning_status"]["default"] == ""


def test_alternating_cleaning_reminder_uses_authoritative_type() -> None:
    """The optional combined sensor selects the matching copy and button."""
    blueprint = (BLUEPRINT_DIR / "care_reminders.yaml").read_text()

    assert "state_attr(cleaning_entity, 'cleaning_type')" in blueprint
    assert "entity_id: !input cleaning_status" in blueprint
    assert "changed_entity == cleaning_entity" in blueprint
    assert "old_state.state != 'overdue'" in blueprint
    assert "combined_cleaning_type == 'spot_clean'" in blueprint
    assert "spot_clean_button_entity" in blueprint
    assert "full_clean_button_entity" in blueprint
    assert "cleaning_entity | trim == ''" in blueprint


def test_existing_reminders_query_and_suppress_active_vacations() -> None:
    """Both reminder blueprints use generic event queries and fail open."""
    for filename in ("care_reminders.yaml", "food_removal_reminder.yaml"):
        blueprint = (BLUEPRINT_DIR / filename).read_text()
        assert "action: calendar.get_events" in blueprint
        assert "continue_on_error: true" in blueprint
        assert "current >= start and current < end" in blueprint
        assert "['unknown', 'unavailable']" in blueprint
        assert "vacation_is_active" in blueprint


def test_vacation_reminder_queries_tomorrow_once() -> None:
    """The advisory blueprint checks start dates from one daily trigger."""
    path = BLUEPRINT_DIR / "vacation_care_reminder.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]
    blueprint = path.read_text()

    assert inputs["reminder_time"]["default"] == "16:00:00"
    assert {trigger["id"] for trigger in document["triggers"]} == {
        "reminder",
        "startup",
        "notification_action",
    }
    assert "action: calendar.get_events" in blueprint
    assert "timedelta(days=1)" in blueprint
    assert "timedelta(days=2)" in blueprint
    assert "start_date == tomorrow" in blueprint
    assert blueprint.count('action: "{{ repeat.item }}"') == 1
    assert inputs["feeding_status"]["default"] == ""
    assert "reminder_time_has_passed" in blueprint
    assert "reminder_already_handled_today" in blueprint
    assert "this.attributes.last_triggered" in blueprint


def _resolved_text(custom: str, default: str) -> str:
    """Mirror blank-aware blueprint text selection."""
    return custom.strip() or default


@pytest.mark.parametrize(
    ("title", "message", "expected_title", "expected_message"),
    [
        ("", "", "Lizard Care — Feeding", "Pixel's feeding is due today."),
        ("Care alert", "", "Care alert", "Pixel's feeding is due today."),
        ("", "Feed before sunset", "Lizard Care — Feeding", "Feed before sunset"),
        ("Care alert", "Feed now", "Care alert", "Feed now"),
    ],
)
def test_custom_notification_text_overrides_independently(
    title: str,
    message: str,
    expected_title: str,
    expected_message: str,
) -> None:
    """Blank and custom title/message values resolve independently."""
    assert _resolved_text(title, "Lizard Care — Feeding") == expected_title
    assert _resolved_text(
        message, "Pixel's feeding is due today."
    ) == expected_message


def test_notification_ux_inputs_and_payloads_are_complete() -> None:
    """Every blueprint exposes custom text, dashboard URL, and one action."""
    expectations = {
        "care_reminders.yaml": {
            "Mark as Fed",
            "Mark as Cleaned",
        },
        "food_removal_reminder.yaml": {"Mark Food Removed"},
        "vacation_care_reminder.yaml": {"Mark as Fed"},
    }
    for filename, labels in expectations.items():
        path = BLUEPRINT_DIR / filename
        document = yaml.load(path.read_text(), Loader=BlueprintLoader)
        inputs = document["blueprint"]["input"]
        blueprint = path.read_text()

        assert inputs["dashboard_url"]["default"] == "/mobile-dashboard/pixel"
        assert "notification_message" in inputs
        assert "multiline" in inputs["notification_message"]["selector"]["text"]
        assert 'url: "{{ configured_dashboard_url }}"' in blueprint
        assert "event_type: mobile_app_notification_action" in blueprint
        assert "action: notify.send_message" not in blueprint
        assert 'action: "{{ repeat.item }}"' in blueprint
        assert 'for_each: "{{ notification_service_list }}"' in blueprint
        service_input = inputs["notification_services"]
        assert service_input["default"] == []
        assert service_input["selector"]["text"]["multiple"] is True
        for label in labels:
            assert f"'title': '{label}'" in blueprint

    care_inputs = yaml.load(
        (BLUEPRINT_DIR / "care_reminders.yaml").read_text(),
        Loader=BlueprintLoader,
    )["blueprint"]["input"]
    assert care_inputs["feed_button"]["default"] == ""
    assert care_inputs["spot_clean_button"]["default"] == ""
    assert care_inputs["full_clean_button"]["default"] == ""


def test_companion_payload_preserves_nested_mobile_data() -> None:
    """Companion service calls retain URL and actionable-notification data."""
    for filename in (
        "care_reminders.yaml",
        "food_removal_reminder.yaml",
        "vacation_care_reminder.yaml",
    ):
        blueprint = (BLUEPRINT_DIR / filename).read_text()
        assert 'action: "{{ repeat.item }}"' in blueprint
        assert 'url: "{{ configured_dashboard_url }}"' in blueprint
        assert "actions: >" in blueprint
        assert "notification_service_list: !input notification_services" in blueprint


def test_completion_events_replace_or_clear_reminders() -> None:
    """Completion branches use stable task tags for every recipient."""
    care = (BLUEPRINT_DIR / "care_reminders.yaml").read_text()
    food = (BLUEPRINT_DIR / "food_removal_reminder.yaml").read_text()
    vacation = (BLUEPRINT_DIR / "vacation_care_reminder.yaml").read_text()

    for blueprint in (care, food):
        assert "event_type: lizardcare_care_completed" in blueprint
        assert "message: clear_notification" in blueprint
        assert "send_completion_notifications" in blueprint
        assert "trigger.event.data.entry_id == pet_config_entry_id" in blueprint

    assert (
        "trigger.event.data.task in ['feeding', 'spot_clean', 'full_clean']"
        in care
    )
    assert "completed_task == 'feeding'" in care
    assert "completed_task == 'spot_clean'" in care
    assert "full clean was completed" in care
    assert "trigger.event.data.task == 'food_removal'" in food

    for suffix in ("feeding", "spot_clean", "full_clean"):
        assert f"}}_{suffix}" in care
    assert "}_food_removal" in food
    assert "}_feeding" in vacation

    completion_section = care.split("trigger.id == 'care_completed'", 1)[1]
    completion_section = completion_section.split("vacation_events_response", 1)[0]
    assert "actions:" not in completion_section


def test_vacation_feeding_tag_can_share_pet_identity() -> None:
    """Vacation feeding can use the same config-entry-scoped notification tag."""
    path = BLUEPRINT_DIR / "vacation_care_reminder.yaml"
    document = yaml.load(path.read_text(), Loader=BlueprintLoader)
    inputs = document["blueprint"]["input"]
    blueprint = path.read_text()

    assert inputs["feeding_status"]["default"] == ""
    assert "config_entry_id(feeding_status_entity)" in blueprint
    assert 'tag: "{{ feeding_notification_tag }}"' in blueprint


def test_multiple_companion_recipients_use_for_each_delivery() -> None:
    """Each configured mobile service receives the same payload."""
    services = [
        "notify.mobile_app_android_phone",
        "notify.mobile_app_iphone",
    ]

    assert list(services) == [
        "notify.mobile_app_android_phone",
        "notify.mobile_app_iphone",
    ]


def test_contextual_actions_route_to_selected_buttons() -> None:
    """Each action event calls its corresponding configured button."""
    care = (BLUEPRINT_DIR / "care_reminders.yaml").read_text()
    food = (BLUEPRINT_DIR / "food_removal_reminder.yaml").read_text()
    vacation = (BLUEPRINT_DIR / "vacation_care_reminder.yaml").read_text()

    for entity_variable in (
        "feed_button_entity",
        "spot_clean_button_entity",
        "full_clean_button_entity",
    ):
        assert f'entity_id: "{{{{ {entity_variable} }}}}"' in care
    assert 'entity_id: "{{ remove_food_button_entity }}"' in food
    assert 'entity_id: "{{ feed_button_entity }}"' in vacation
    assert care.count("action: button.press") == 3
    assert food.count("action: button.press") == 1
    assert vacation.count("action: button.press") == 1


def test_action_ids_are_unique_by_automation_and_task() -> None:
    """Action identifiers combine automation identity with a task suffix."""
    care = (BLUEPRINT_DIR / "care_reminders.yaml").read_text()
    food = (BLUEPRINT_DIR / "food_removal_reminder.yaml").read_text()
    vacation = (BLUEPRINT_DIR / "vacation_care_reminder.yaml").read_text()

    for blueprint in (care, food, vacation):
        assert "this.entity_id | replace('.', '_') | upper" in blueprint
    assert 'feeding_action_id: "{{ action_id_prefix }}_FEED"' in care
    assert 'spot_clean_action_id: "{{ action_id_prefix }}_SPOT_CLEAN"' in care
    assert 'full_clean_action_id: "{{ action_id_prefix }}_FULL_CLEAN"' in care
    assert "_REMOVE_FOOD" in food


def test_unrelated_notification_actions_stop_before_reminder_logic() -> None:
    """An unmatched mobile action cannot press a button or send a reminder."""
    for filename in (
        "care_reminders.yaml",
        "food_removal_reminder.yaml",
        "vacation_care_reminder.yaml",
    ):
        blueprint = (BLUEPRINT_DIR / filename).read_text()
        handler = blueprint.index("trigger.event.data.action")
        stop = blueprint.index(
            'value_template: "{{ trigger.id != \'notification_action\' }}"'
        )
        calendar_query = blueprint.index("action: calendar.get_events")
        assert handler < stop < calendar_query


def _vacation_is_active(
    now: datetime,
    start: datetime,
    end: datetime,
) -> bool:
    """Mirror the blueprints' inclusive-start/exclusive-end rule."""
    return now >= start and now < end


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (_local_datetime(2026, 9, 18, 17, 59), False),
        (_local_datetime(2026, 9, 18, 18, 0), True),
        (_local_datetime(2026, 9, 19, 0, 30), True),
        (_local_datetime(2026, 9, 21, 13, 59), True),
        (_local_datetime(2026, 9, 21, 14, 0), False),
    ],
)
def test_timed_vacation_uses_actual_event_boundaries(
    current: datetime,
    expected: bool,
) -> None:
    """Timed, multi-day, and midnight-spanning events use exact instants."""
    assert _vacation_is_active(
        current,
        _local_datetime(2026, 9, 18, 18, 0),
        _local_datetime(2026, 9, 21, 14, 0),
    ) is expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (_local_datetime(2026, 9, 17, 23, 59), False),
        (_local_datetime(2026, 9, 18, 0, 0), True),
        (_local_datetime(2026, 9, 20, 23, 59), True),
        (_local_datetime(2026, 9, 21, 0, 0), False),
    ],
)
def test_all_day_vacation_uses_calendar_window(
    current: datetime,
    expected: bool,
) -> None:
    """All-day events cover start midnight through exclusive end midnight."""
    assert _vacation_is_active(
        current,
        _local_datetime(2026, 9, 18, 0, 0),
        _local_datetime(2026, 9, 21, 0, 0),
    ) is expected


def test_pre_vacation_detection_compares_local_start_date() -> None:
    """Reminder selection is based on tomorrow's date, not 24-hour distance."""
    reminder_at = _local_datetime(2026, 9, 17, 16, 0)
    tomorrow = (reminder_at + timedelta(days=1)).date()

    assert _local_datetime(2026, 9, 18, 8, 0).date() == tomorrow
    assert _local_datetime(2026, 9, 18, 18, 0).date() == tomorrow
    assert _local_datetime(2026, 9, 19, 8, 0).date() != tomorrow


def _should_check_pre_vacation(
    trigger_id: str,
    now: datetime,
    reminder_time: time,
    previous_trigger: datetime | None,
) -> bool:
    """Mirror the advisory blueprint's startup recovery gate."""
    scheduled = datetime.combine(now.date(), reminder_time, tzinfo=now.tzinfo)
    handled = (
        previous_trigger is not None
        and previous_trigger.date() == now.date()
        and previous_trigger >= scheduled
    )
    return trigger_id == "reminder" or (
        trigger_id == "startup" and now >= scheduled and not handled
    )


def test_normal_pre_vacation_reminder_runs_at_scheduled_time() -> None:
    """The normal daily trigger remains eligible exactly once."""
    assert _should_check_pre_vacation(
        "reminder",
        _local_datetime(2026, 9, 17, 16, 0),
        time(16, 0),
        _local_datetime(2026, 9, 16, 16, 0),
    )


def test_startup_before_reminder_does_not_send_early() -> None:
    """An early startup leaves delivery to the later time trigger."""
    assert not _should_check_pre_vacation(
        "startup",
        _local_datetime(2026, 9, 17, 15, 0),
        time(16, 0),
        None,
    )


def test_startup_after_missed_reminder_recovers() -> None:
    """A late startup runs the query when no later trigger was restored."""
    assert _should_check_pre_vacation(
        "startup",
        _local_datetime(2026, 9, 17, 17, 15),
        time(16, 0),
        _local_datetime(2026, 9, 17, 15, 0),
    )


def test_startup_after_sent_reminder_does_not_duplicate() -> None:
    """A restored post-reminder last-triggered value suppresses recovery."""
    assert not _should_check_pre_vacation(
        "startup",
        _local_datetime(2026, 9, 17, 17, 15),
        time(16, 0),
        _local_datetime(2026, 9, 17, 16, 0),
    )


def test_vacation_start_and_query_failure_guards_are_present() -> None:
    """No matching event or a failed query cannot emit a notification."""
    blueprint = (
        BLUEPRINT_DIR / "vacation_care_reminder.yaml"
    ).read_text()

    assert "continue_on_error: true" in blueprint
    assert "vacation_events_response | default({})" in blueprint
    assert 'value_template: "{{ vacation_starts_tomorrow }}"' in blueprint


def test_disabled_spot_clean_never_notifies() -> None:
    """Every Spot Clean notification path explicitly rejects disabled state."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    assert blueprint.count(
        "not is_state(spot_clean_entity, 'disabled')"
    ) == 2


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
    assert blueprint.count("is_cleaning_repeat_boundary and") == 3
    assert blueprint.count(
        "trigger.id in ['due_today', 'overdue_repeat']"
    ) == 4
    assert blueprint.count("not automation_ran_this_minute") == 8
    assert blueprint.count("elapsed >= 60") == 4
    assert blueprint.count("is_within_overdue_window and") == 8
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


def _is_within_window(
    value: datetime,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
) -> bool:
    """Mirror the blueprint's inclusive local notification window."""
    current_minutes = value.hour * 60 + value.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


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
    assert blueprint.count("trigger.id == 'startup'") == 4


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


def test_hourly_repeats_are_limited_to_daily_window() -> None:
    """A 4 PM through 11 PM window admits only its eight hourly boundaries."""
    timezone = ZoneInfo("America/Chicago")
    allowed_hours = [
        hour
        for hour in range(24)
        if _is_boundary(
            datetime(2026, 9, 3, hour, 0, tzinfo=timezone), 60
        )
        and _is_within_window(
            datetime(2026, 9, 3, hour, 0, tzinfo=timezone),
            16,
            0,
            23,
            0,
        )
    ]
    assert allowed_hours == [16, 17, 18, 19, 20, 21, 22, 23]


def test_overdue_window_resumes_at_reminder_time_next_day() -> None:
    """Morning repeats are suppressed and the next 4 PM boundary is allowed."""
    timezone = ZoneInfo("America/Chicago")
    morning = datetime(2026, 9, 4, 10, 0, tzinfo=timezone)
    reminder_time = datetime(2026, 9, 4, 16, 0, tzinfo=timezone)

    assert not _is_within_window(morning, 16, 0, 23, 0)
    assert _is_within_window(reminder_time, 16, 0, 23, 0)
    assert _is_boundary(reminder_time, 60)
    assert _is_boundary(reminder_time, 1440)


def test_window_can_cross_midnight() -> None:
    """An 8 PM through 1 AM window includes late night and early morning."""
    timezone = ZoneInfo("America/Chicago")
    assert _is_within_window(
        datetime(2026, 9, 3, 20, 0, tzinfo=timezone), 20, 0, 1, 0
    )
    assert _is_within_window(
        datetime(2026, 9, 4, 0, 30, tzinfo=timezone), 20, 0, 1, 0
    )
    assert _is_within_window(
        datetime(2026, 9, 4, 1, 0, tzinfo=timezone), 20, 0, 1, 0
    )
    assert not _is_within_window(
        datetime(2026, 9, 4, 1, 1, tzinfo=timezone), 20, 0, 1, 0
    )


def test_immediate_overdue_is_not_gated_by_window() -> None:
    """Only startup and recurring paths reference the window guard."""
    blueprint = (
        BLUEPRINT_DIR / "care_reminders.yaml"
    ).read_text()

    for trigger_id in (
        "feeding_overdue",
        "spot_clean_overdue",
        "full_clean_overdue",
    ):
        assert f"trigger.id == '{trigger_id}' or" in blueprint
