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

    def async_entries(self, _domain: str) -> list[SimpleNamespace]:
        """Return the configured pet entry."""
        return [self.entry]

    def async_update_entry(self, entry: SimpleNamespace, **changes: str) -> None:
        """Record entry-title updates."""
        if title := changes.get("title"):
            entry.title = title
            self.title_updates.append(title)


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

    assert result["type"] == "create_entry"
    assert result["data"][CONF_SPOT_CLEAN_ENABLED] is False
    assert result["data"][CONF_SPOT_CLEAN_INTERVAL_DAYS] == 9
    assert result["data"]["unrelated"] == "keep"


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
    assert saved["data"][CONF_CLEANING_SCHEDULE_MODE] == "interval"
    assert saved["data"][CONF_SPOT_CLEAN_INTERVAL_DAYS] == 6


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

    assert saved["data"][CONF_FEEDING_INTERVAL_DAYS] == 3
    assert saved["data"][CONF_ALTERNATING_CLEANING_INTERVAL_DAYS] == 45
    assert saved["data"][CONF_ALTERNATING_CLEANING_ANCHOR_DATE] == "2026-09-01"
    assert saved["data"][CONF_ALTERNATING_ANCHOR_TYPE] == "spot_clean"
    assert saved["data"]["legacy_option"] == "preserved"


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
    assert unchanged["data"] == original_options

    changed = asyncio.run(
        flow.async_step_cleaning_alternating(
            {
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: 30,
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE: "2026-10-01",
                CONF_ALTERNATING_ANCHOR_TYPE: "full_clean",
            }
        )
    )
    assert changed["data"][CONF_ALTERNATING_CLEANING_INTERVAL_DAYS] == 30
    assert changed["data"][CONF_ALTERNATING_CLEANING_ANCHOR_DATE] == "2026-10-01"
    assert changed["data"][CONF_ALTERNATING_ANCHOR_TYPE] == "full_clean"
    assert changed["data"][CONF_FEEDING_INTERVAL_DAYS] == 3


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
    assert result["data"][CONF_FEEDING_INTERVAL_DAYS] == 4
    assert result["data"][CONF_PET_NAME] == "Pixel Two"


def test_standard_reload_helper_and_incremental_save_are_retained() -> None:
    """The refactor keeps native reload and avoids replacing other sections."""
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "custom_components/lizardcare/config_flow.py"
    ).read_text()

    assert "class LizardCareOptionsFlow(OptionsFlowWithReload):" in source
    assert "data={**self.config_entry.options, **updates}" in source
    assert "entry.add_update_listener" not in source
