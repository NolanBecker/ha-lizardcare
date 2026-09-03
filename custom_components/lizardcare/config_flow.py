"""Config flow for Lizard Care."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BIRTH_DATE,
    CONF_FEEDING_INSTRUCTIONS,
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FULL_CLEAN_INSTRUCTIONS,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN,
    CONF_NORMALIZED_PET_NAME,
    CONF_NOTES,
    CONF_PET_NAME,
    CONF_REMOVE_FOOD_AFTER_HOURS,
    CONF_SEX,
    CONF_SPECIES,
    CONF_SPOT_CLEAN_INSTRUCTIONS,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    DEFAULT_SPECIES,
    DOMAIN,
)
from .food_removal import get_food_removal_settings
from .instructions import clean_instruction, get_care_instructions
from .profile import get_pet_profile, normalize_pet_name, pet_name_is_duplicate
from .schedule import get_care_schedule


def _profile_schema(*, species_default: str | None = None) -> vol.Schema:
    """Return the pet profile form schema."""
    species_key = (
        vol.Required(CONF_SPECIES, default=species_default)
        if species_default is not None
        else vol.Required(CONF_SPECIES)
    )
    return vol.Schema(
        {
            vol.Required(CONF_PET_NAME): selector.TextSelector(),
            species_key: selector.TextSelector(),
            vol.Optional(CONF_BIRTH_DATE): selector.DateSelector(),
            vol.Optional(CONF_SEX): selector.TextSelector(),
            vol.Optional(CONF_NOTES): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


def _positive_integer_selector() -> selector.NumberSelector:
    """Return a positive whole-number selector."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _options_schema() -> vol.Schema:
    """Return the combined profile and schedule options schema."""
    return _profile_schema().extend(
        {
            vol.Required(
                CONF_FEEDING_INTERVAL_DAYS
            ): _positive_integer_selector(),
            vol.Required(
                CONF_SPOT_CLEAN_INTERVAL_DAYS
            ): _positive_integer_selector(),
            vol.Required(
                CONF_FULL_CLEAN_INTERVAL_DAYS
            ): _positive_integer_selector(),
            vol.Required(
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN
            ): selector.BooleanSelector(),
            vol.Optional(CONF_FEEDING_INSTRUCTIONS): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_SPOT_CLEAN_INSTRUCTIONS): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Optional(CONF_FULL_CLEAN_INSTRUCTIONS): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
            vol.Required(
                CONF_REMOVE_FOOD_AFTER_HOURS
            ): _positive_integer_selector(),
        }
    )


def _as_positive_int(value: Any) -> int | None:
    """Return a positive integer without truncating fractional values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value < 1 or not float(value).is_integer():
        return None
    return int(value)


class LizardCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lizard Care."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LizardCareOptionsFlow:
        """Create the options flow."""
        return LizardCareOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pet_name = user_input[CONF_PET_NAME].strip()
            normalized_name = normalize_pet_name(pet_name)

            if not normalized_name:
                errors[CONF_PET_NAME] = "invalid_pet_name"
            elif pet_name_is_duplicate(self.hass, normalized_name):
                errors[CONF_PET_NAME] = "duplicate_pet_name"
            else:
                data = {
                    **user_input,
                    CONF_PET_NAME: pet_name,
                    CONF_NORMALIZED_PET_NAME: normalized_name,
                }
                return self.async_create_entry(title=pet_name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_profile_schema(species_default=DEFAULT_SPECIES),
            errors=errors,
        )


class LizardCareOptionsFlow(OptionsFlowWithReload):
    """Handle editable pet profile options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the pet profile."""
        errors: dict[str, str] = {}
        intervals: dict[str, int] = {}

        if user_input is not None:
            pet_name = user_input[CONF_PET_NAME].strip()
            normalized_name = normalize_pet_name(pet_name)

            if not normalized_name:
                errors[CONF_PET_NAME] = "invalid_pet_name"
            elif pet_name_is_duplicate(
                self.hass,
                normalized_name,
                exclude_entry_id=self.config_entry.entry_id,
            ):
                errors[CONF_PET_NAME] = "duplicate_pet_name"
            else:
                for key in (
                    CONF_FEEDING_INTERVAL_DAYS,
                    CONF_SPOT_CLEAN_INTERVAL_DAYS,
                    CONF_FULL_CLEAN_INTERVAL_DAYS,
                    CONF_REMOVE_FOOD_AFTER_HOURS,
                ):
                    value = _as_positive_int(user_input[key])
                    if value is None:
                        errors[key] = "invalid_interval"
                    else:
                        intervals[key] = value

            if not errors:
                options = {
                    CONF_PET_NAME: pet_name,
                    CONF_SPECIES: user_input[CONF_SPECIES].strip(),
                    CONF_BIRTH_DATE: user_input.get(CONF_BIRTH_DATE),
                    CONF_SEX: user_input.get(CONF_SEX),
                    CONF_NOTES: user_input.get(CONF_NOTES),
                    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: user_input[
                        CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN
                    ],
                    CONF_FEEDING_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_FEEDING_INSTRUCTIONS)
                    ),
                    CONF_SPOT_CLEAN_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_SPOT_CLEAN_INSTRUCTIONS)
                    ),
                    CONF_FULL_CLEAN_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_FULL_CLEAN_INSTRUCTIONS)
                    ),
                    **intervals,
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=pet_name
                )
                return self.async_create_entry(data=options)

        profile = get_pet_profile(self.config_entry)
        schedule = get_care_schedule(self.config_entry)
        instructions = get_care_instructions(self.config_entry)
        food_removal = get_food_removal_settings(self.config_entry)
        suggested_values = user_input or {
            CONF_PET_NAME: profile.pet_name,
            CONF_SPECIES: profile.species,
            CONF_BIRTH_DATE: profile.birth_date,
            CONF_SEX: profile.sex,
            CONF_NOTES: profile.notes,
            CONF_FEEDING_INTERVAL_DAYS: schedule.feeding_interval_days,
            CONF_SPOT_CLEAN_INTERVAL_DAYS: schedule.spot_clean_interval_days,
            CONF_FULL_CLEAN_INTERVAL_DAYS: schedule.full_clean_interval_days,
            CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: (
                schedule.full_clean_satisfies_spot_clean
            ),
            CONF_FEEDING_INSTRUCTIONS: instructions.feeding,
            CONF_SPOT_CLEAN_INSTRUCTIONS: instructions.spot_clean,
            CONF_FULL_CLEAN_INSTRUCTIONS: instructions.full_clean,
            CONF_REMOVE_FOOD_AFTER_HOURS: food_removal.remove_after_hours,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(),
                suggested_values,
            ),
            errors=errors,
        )
