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
    CONF_NORMALIZED_PET_NAME,
    CONF_PET_NAME,
    CONF_SEX,
    CONF_SPECIES,
    DEFAULT_SPECIES,
    DOMAIN,
)
from .profile import get_pet_profile, normalize_pet_name, pet_name_is_duplicate


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
        }
    )


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
                options = {
                    CONF_PET_NAME: pet_name,
                    CONF_SPECIES: user_input[CONF_SPECIES].strip(),
                    CONF_BIRTH_DATE: user_input.get(CONF_BIRTH_DATE),
                    CONF_SEX: user_input.get(CONF_SEX),
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=pet_name
                )
                return self.async_create_entry(data=options)

        profile = get_pet_profile(self.config_entry)
        suggested_values = user_input or {
            CONF_PET_NAME: profile.pet_name,
            CONF_SPECIES: profile.species,
            CONF_BIRTH_DATE: profile.birth_date,
            CONF_SEX: profile.sex,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _profile_schema(),
                suggested_values,
            ),
            errors=errors,
        )
