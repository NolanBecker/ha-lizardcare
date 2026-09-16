"""Tests for the feature-oriented Lizard Care Options Flow."""

import asyncio
from types import SimpleNamespace

from homeassistant import config_entries

# The validation environment predates this current Home Assistant helper.
if not hasattr(config_entries, "OptionsFlowWithReload"):

    class OptionsFlowWithReload(config_entries.OptionsFlow):
        """Compatibility shim for exercising the current flow structure."""

    config_entries.OptionsFlowWithReload = OptionsFlowWithReload

from custom_components.lizardcare.config_flow import LizardCareOptionsFlow
from custom_components.lizardcare.const import (
    CLEANING_SCHEDULE_ALTERNATING,
    CLEANING_SCHEDULE_INTERVAL,
    CLEANING_SCHEDULE_MONTHLY,
    CONF_ALTERNATING_ANCHOR_TYPE,
    CONF_ALTERNATING_CLEANING_ANCHOR_DATE,
    CONF_ALTERNATING_CLEANING_INTERVAL_DAYS,
    CONF_BIRTH_DATE,
    CONF_CLEANING_CYCLE_ANCHOR,
    CONF_CLEANING_DAY_OF_MONTH,
    CONF_CLEANING_SCHEDULE_MODE,
    CONF_FEEDING_INSTRUCTIONS,
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FOOD_REMOVAL_ANCHOR_TIME,
    CONF_FOOD_REMOVAL_DELAY,
    CONF_FOOD_REMOVAL_DELAY_UNIT,
    CONF_FULL_CLEAN_EVERY,
    CONF_FULL_CLEAN_INSTRUCTIONS,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    CONF_NOTES,
    CONF_PET_NAME,
    CONF_SEX,
    CONF_SPECIES,
    CONF_SPOT_CLEAN_ENABLED,
    CONF_SPOT_CLEAN_INSTRUCTIONS,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    CONF_VACATION_CALENDAR,
)


class FakeConfigEntries:
    """Provide the small config-entry manager surface used by the flow."""

    def __init__(self, entry: SimpleNamespace) -> None:
        self.entry = entry
        self.title_updates: list[str] = []
        self.reloads: list[str] = []

    def async_entries(self, _domain: str) -> list[SimpleNamespace]:
        """Return the configured pet entry."""
        return [self.entry]

    def async_update_entry(self, entry: SimpleNamespace, **changes: object) -> bool:
        """Apply config-entry changes and report whether anything changed."""
        changed = False
        if (title := changes.get("title")) and entry.title != title:
            entry.title = title
            self.title_updates.append(title)
            changed = True
        if "options" in changes and entry.options != changes["options"]:
            entry.options = dict(changes["options"])
            changed = True
        return changed

    def async_schedule_reload(self, entry_id: str) -> None:
        """Record a standard Home Assistant reload request."""
        self.reloads.append(entry_id)


def _flow(
    *, options: dict[str, object] | None = None, data: dict[str, object] | None = None
) -> tuple[LizardCareOptionsFlow, SimpleNamespace]:
    """Return an initialized Options Flow with one existing entry."""
    entry = SimpleNamespace(
        entry_id="pet-one",
        domain="lizardcare",
        title="Pixel",
        options=dict(options or {}),
        data=dict(data or {}),
    )
    flow = LizardCareOptionsFlow()
    flow._config_entry = entry
    flow.hass = SimpleNamespace(config_entries=FakeConfigEntries(entry))
    return flow, entry


def _schema_keys(result: dict[str, object]) -> set[str]:
    """Return field names from a flow form schema."""
    schema = result["data_schema"]
    return {marker.schema for marker in schema.schema}


def _suggested_value(result: dict[str, object], key: str) -> object:
    """Return Home Assistant's suggested value for one form field."""
    schema = result["data_schema"]
    marker = next(item for item in schema.schema if item.schema == key)
    return marker.description["suggested_value"]


def test_top_level_options_menu_is_feature_oriented() -> None:
    """Configure opens a concise native menu rather than a flat form."""
    flow, _entry = _flow()

    result = asyncio.run(flow.async_step_init())

    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "feeding",
        "cleaning",
        "food_removal",
        "instructions",
        "vacation",
        "profile",
        "finish",
    ]


def test_feeding_form_contains_only_feeding_settings() -> None:
    """The Feeding page is pre-populated without unrelated fields."""
    flow, _entry = _flow(options={CONF_FEEDING_INTERVAL_DAYS: 5})

    result = asyncio.run(flow.async_step_feeding())

    assert _schema_keys(result) == {CONF_FEEDING_INTERVAL_DAYS}
    assert _suggested_value(result, CONF_FEEDING_INTERVAL_DAYS) == 5


def test_cleaning_mode_routes_to_mode_specific_forms() -> None:
    """Each schedule selection opens only its relevant settings page."""
    cases = {
        CLEANING_SCHEDULE_ALTERNATING: {
            CONF_ALTERNATING_CLEANING_INTERVAL_DAYS,
            CONF_ALTERNATING_CLEANING_ANCHOR_DATE,
            CONF_ALTERNATING_ANCHOR_TYPE,
        },
        CLEANING_SCHEDULE_MONTHLY: {
            CONF_CLEANING_DAY_OF_MONTH,
            CONF_FULL_CLEAN_EVERY,
            CONF_CLEANING_CYCLE_ANCHOR,
        },
        CLEANING_SCHEDULE_INTERVAL: {
            CONF_FULL_CLEAN_INTERVAL_DAYS,
            CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
            CONF_SPOT_CLEAN_ENABLED,
        },
    }
    for mode, expected_fields in cases.items():
        flow, _entry = _flow()
        result = asyncio.run(
            flow.async_step_cleaning({CONF_CLEANING_SCHEDULE_MODE: mode})
        )
        assert _schema_keys(result) == expected_fields


def test_disabled_spot_clean_hides_interval_and_preserves_it() -> None:
    """Disabling Spot Clean saves without displaying or erasing its interval."""
    flow, _entry = _flow(
        options={CONF_SPOT_CLEAN_INTERVAL_DAYS: 9, "unrelated": "keep"}
    )

    result = asyncio.run(
        flow.async_step_cleaning_independent(
            {
                CONF_FULL_CLEAN_INTERVAL_DAYS: 30,
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: True,
                CONF_SPOT_CLEAN_ENABLED: False,
            }
        )
    )

    assert result["type"] == "menu"
    assert _entry.options[CONF_SPOT_CLEAN_ENABLED] is False
    assert _entry.options[CONF_SPOT_CLEAN_INTERVAL_DAYS] == 9
    assert _entry.options["unrelated"] == "keep"


def test_enabled_spot_clean_opens_interval_step() -> None:
    """Enabling Spot Clean opens its scheduling step before saving."""
    flow, _entry = _flow(options={CONF_SPOT_CLEAN_INTERVAL_DAYS: 8})

    result = asyncio.run(
        flow.async_step_cleaning_independent(
            {
                CONF_FULL_CLEAN_INTERVAL_DAYS: 31,
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: False,
                CONF_SPOT_CLEAN_ENABLED: True,
            }
        )
    )
    assert result["step_id"] == "cleaning_spot"
    assert _schema_keys(result) == {CONF_SPOT_CLEAN_INTERVAL_DAYS}

    saved = asyncio.run(
        flow.async_step_cleaning_spot(
            {CONF_SPOT_CLEAN_INTERVAL_DAYS: 6}
        )
    )
    assert saved["type"] == "menu"
    assert _entry.options[CONF_CLEANING_SCHEDULE_MODE] == "interval"
    assert _entry.options[CONF_SPOT_CLEAN_INTERVAL_DAYS] == 6


def test_feature_pages_expose_only_their_current_fields() -> None:
    """Food Removal, instructions, Vacation, and Profile stay isolated."""
    flow, _entry = _flow()

    assert _schema_keys(asyncio.run(flow.async_step_food_removal())) == {
        CONF_FOOD_REMOVAL_ANCHOR_TIME,
        CONF_FOOD_REMOVAL_DELAY,
        CONF_FOOD_REMOVAL_DELAY_UNIT,
    }
    assert _schema_keys(asyncio.run(flow.async_step_instructions())) == {
        CONF_FEEDING_INSTRUCTIONS,
        CONF_SPOT_CLEAN_INSTRUCTIONS,
        CONF_FULL_CLEAN_INSTRUCTIONS,
    }
    assert _schema_keys(asyncio.run(flow.async_step_vacation())) == {
        CONF_VACATION_CALENDAR
    }
    assert _schema_keys(asyncio.run(flow.async_step_profile())) == {
        CONF_PET_NAME,
        CONF_SPECIES,
        CONF_BIRTH_DATE,
        CONF_SEX,
        CONF_NOTES,
    }


def test_section_save_merges_existing_options_and_data_defaults() -> None:
    """A section update preserves unrelated options from an existing pet."""
    flow, _entry = _flow(
        options={
            CONF_FEEDING_INTERVAL_DAYS: 4,
            CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 45,
            CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
            CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
            "legacy_option": "preserved",
        },
        data={CONF_SPECIES: "Gargoyle Gecko"},
    )

    form = asyncio.run(flow.async_step_feeding())
    assert _suggested_value(form, CONF_FEEDING_INTERVAL_DAYS) == 4
    saved = asyncio.run(
        flow.async_step_feeding({CONF_FEEDING_INTERVAL_DAYS: 3})
    )

    assert saved["type"] == "menu"
    assert _entry.options[CONF_FEEDING_INTERVAL_DAYS] == 3
    assert _entry.options[CONF_ALTERNATING_CLEANING_INTERVAL_DAYS] == 45
    assert _entry.options[CONF_ALTERNATING_CLEANING_ANCHOR_DATE] == "2026-09-01"
    assert _entry.options[CONF_ALTERNATING_ANCHOR_TYPE] == "spot_clean"
    assert _entry.options["legacy_option"] == "preserved"

    reopened = asyncio.run(flow.async_step_feeding())
    assert _suggested_value(reopened, CONF_FEEDING_INTERVAL_DAYS) == 3


def test_existing_entry_data_populates_forms_without_option_migration() -> None:
    """Pre-options config entries continue resolving their original values."""
    flow, _entry = _flow(data={CONF_FEEDING_INTERVAL_DAYS: 7})

    form = asyncio.run(flow.async_step_feeding())

    assert _suggested_value(form, CONF_FEEDING_INTERVAL_DAYS) == 7


def test_alternating_save_changes_only_the_effective_definition_fields() -> None:
    """Alternating edits preserve unrelated state and save signature inputs."""
    original_options = {
        CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_ALTERNATING,
        CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 45,
        CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
        CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
        CONF_FEEDING_INTERVAL_DAYS: 3,
    }
    flow, _entry = _flow(options=original_options)

    unchanged = asyncio.run(
        flow.async_step_cleaning_alternating(
            {
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 45,
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
                CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
            }
        )
    )
    assert unchanged["type"] == "menu"
    assert _entry.options == original_options
    assert flow.hass.config_entries.reloads == []

    changed = asyncio.run(
        flow.async_step_cleaning_alternating(
            {
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 30,
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-10-01",
                CONF_ALTERNATING_ANCHOR_TYPE: "full_clean",
            }
        )
    )
    assert changed["type"] == "menu"
    assert _entry.options[CONF_ALTERNATING_CLEANING_INTERVAL_DAYS] == 30
    assert _entry.options[CONF_ALTERNATING_CLEANING_ANCHOR_DATE] == "2026-10-01"
    assert _entry.options[CONF_ALTERNATING_ANCHOR_TYPE] == "full_clean"
    assert _entry.options[CONF_FEEDING_INTERVAL_DAYS] == 3
    assert flow.hass.config_entries.reloads == ["pet-one"]


def test_profile_save_updates_title_without_resetting_schedule() -> None:
    """Profile edits retain schedule options and update the existing title."""
    flow, entry = _flow(options={CONF_FEEDING_INTERVAL_DAYS: 4})

    result = asyncio.run(
        flow.async_step_profile(
            {
                CONF_PET_NAME: "Pixel Two",
                CONF_SPECIES: "Gargoyle Gecko",
                CONF_BIRTH_DATE: "2024-01-02",
                CONF_SEX: "Female",
                CONF_NOTES: "Calm",
            }
        )
    )

    assert entry.title == "Pixel Two"
    assert result["type"] == "menu"
    assert entry.options[CONF_FEEDING_INTERVAL_DAYS] == 4
    assert entry.options[CONF_PET_NAME] == "Pixel Two"


def test_multiple_sections_save_in_one_flow_and_finish_explicitly() -> None:
    """Section saves persist independently until Finish closes the flow."""
    flow, entry = _flow(options={"unrelated": "keep"})

    feeding = asyncio.run(
        flow.async_step_feeding({CONF_FEEDING_INTERVAL_DAYS: 3})
    )
    vacation = asyncio.run(
        flow.async_step_vacation({CONF_VACATION_CALENDAR: "calendar.travel"})
    )

    assert feeding["type"] == "menu"
    assert vacation["type"] == "menu"
    assert entry.options == {
        "unrelated": "keep",
        CONF_FEEDING_INTERVAL_DAYS: 3,
        CONF_VACATION_CALENDAR: "calendar.travel",
    }
    assert flow.hass.config_entries.reloads == ["pet-one", "pet-one"]

    finished = asyncio.run(flow.async_step_finish())
    assert finished["type"] == "create_entry"
    assert finished["data"] == entry.options


def test_each_top_level_section_returns_to_menu_after_save() -> None:
    """All non-nested feature sections remain in the same options flow."""
    cases = [
        (
            "feeding",
            {CONF_FEEDING_INTERVAL_DAYS: 4},
        ),
        (
            "food_removal",
            {
                CONF_FOOD_REMOVAL_ANCHOR_TIME: "17:00:00",
                CONF_FOOD_REMOVAL_DELAY: 2,
                CONF_FOOD_REMOVAL_DELAY_UNIT: "hours",
            },
        ),
        (
            "instructions",
            {
                CONF_FEEDING_INSTRUCTIONS: "Feed insects",
                CONF_SPOT_CLEAN_INSTRUCTIONS: "Remove waste",
                CONF_FULL_CLEAN_INSTRUCTIONS: "Replace substrate",
            },
        ),
        (
            "vacation",
            {CONF_VACATION_CALENDAR: "calendar.travel"},
        ),
        (
            "profile",
            {
                CONF_PET_NAME: "Pixel",
                CONF_SPECIES: "Gargoyle Gecko",
                CONF_BIRTH_DATE: "2024-01-02",
                CONF_SEX: "Female",
                CONF_NOTES: "Calm",
            },
        ),
    ]

    for step, user_input in cases:
        flow, entry = _flow()
        result = asyncio.run(getattr(flow, f"async_step_{step}")(user_input))
        assert result["type"] == "menu"
        assert entry.options
        assert flow.hass.config_entries.reloads == ["pet-one"]


def test_all_cleaning_paths_return_to_menu_after_final_save() -> None:
    """Independent, Monthly, and Alternating saves all return to the menu."""
    cases = [
        (
            "async_step_cleaning_independent",
            {
                CONF_FULL_CLEAN_INTERVAL_DAYS: 30,
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: True,
                CONF_SPOT_CLEAN_ENABLED: False,
            },
        ),
        (
            "async_step_cleaning_monthly",
            {
                CONF_CLEANING_DAY_OF_MONTH: 10,
                CONF_FULL_CLEAN_EVERY: 2,
                CONF_CLEANING_CYCLE_ANCHOR: "2026-09-01",
            },
        ),
        (
            "async_step_cleaning_alternating",
            {
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 14,
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-09-01",
                CONF_ALTERNATING_ANCHOR_TYPE: "spot_clean",
            },
        ),
    ]

    for method, user_input in cases:
        flow, entry = _flow()
        result = asyncio.run(getattr(flow, method)(user_input))
        assert result["type"] == "menu"
        assert entry.options[CONF_CLEANING_SCHEDULE_MODE] in {
            CLEANING_SCHEDULE_INTERVAL,
            CLEANING_SCHEDULE_MONTHLY,
            CLEANING_SCHEDULE_ALTERNATING,
        }
        assert flow.hass.config_entries.reloads == ["pet-one"]


def test_standard_reload_helper_and_incremental_save_are_retained() -> None:
    """The refactor keeps native reload and avoids replacing other sections."""
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "custom_components/lizardcare/config_flow.py"
    ).read_text()

    assert "class LizardCareOptionsFlow(OptionsFlowWithReload):" in source
    assert "async_update_entry(" in source
    assert "async_schedule_reload(" in source
    assert "entry.add_update_listener" not in source
