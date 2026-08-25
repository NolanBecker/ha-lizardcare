"""Config flow for Lizard Care."""

from __future__ import annotations

import unicodedata
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
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


def _normalize_pet_name(name: str) -> str:
    """Normalize a pet name for duplicate detection."""
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


class LizardCareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lizard Care."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pet_name = user_input[CONF_PET_NAME].strip()
            normalized_name = _normalize_pet_name(pet_name)

            if not normalized_name:
                errors[CONF_PET_NAME] = "invalid_pet_name"
            else:
                data = {
                    **user_input,
                    CONF_PET_NAME: pet_name,
                    CONF_NORMALIZED_PET_NAME: normalized_name,
                }
                self._async_abort_entries_match(
                    {CONF_NORMALIZED_PET_NAME: normalized_name}
                )
                return self.async_create_entry(title=pet_name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PET_NAME): selector.TextSelector(),
                    vol.Required(
                        CONF_SPECIES, default=DEFAULT_SPECIES
                    ): selector.TextSelector(),
                    vol.Optional(CONF_BIRTH_DATE): selector.DateSelector(),
                    vol.Optional(CONF_SEX): selector.TextSelector(),
                }
            ),
            errors=errors,
        )
