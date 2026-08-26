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
    CONF_CLEANING_REMINDER_TIME,
    CONF_FEEDING_INTERVAL_DAYS,
    CONF_FEEDING_OVERDUE_REPEAT_HOURS,
    CONF_FEEDING_REMINDERS,
    CONF_FEEDING_REMINDER_TIME,
    CONF_FOOD_REMOVAL_DELAY_HOURS,
    CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
    CONF_FOOD_REMOVAL_REMINDER,
    CONF_FOOD_REMOVAL_REMINDER_BASIS,
    CONF_FULL_CLEAN_INTERVAL_DAYS,
    CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
    CONF_FULL_CLEAN_REMINDERS,
    CONF_NOTES,
    CONF_NORMALIZED_PET_NAME,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_PET_NAME,
    CONF_SEX,
    CONF_SPECIES,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
    CONF_SPOT_CLEAN_REMINDERS,
    DEFAULT_SPECIES,
    DOMAIN,
    FOOD_REMOVAL_BASIS_ACTUAL,
    FOOD_REMOVAL_BASIS_SCHEDULED,
)
from .notifications import get_notification_settings
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


def _nonnegative_integer_selector() -> selector.NumberSelector:
    """Return a whole-number selector where zero disables a feature."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
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
            vol.Optional(CONF_NOTIFICATION_RECIPIENTS): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="notify", multiple=True)
            ),
            vol.Required(CONF_FEEDING_REMINDERS): selector.BooleanSelector(),
            vol.Required(CONF_SPOT_CLEAN_REMINDERS): selector.BooleanSelector(),
            vol.Required(CONF_FULL_CLEAN_REMINDERS): selector.BooleanSelector(),
            vol.Required(CONF_FOOD_REMOVAL_REMINDER): selector.BooleanSelector(),
            vol.Required(CONF_FEEDING_REMINDER_TIME): selector.TimeSelector(),
            vol.Required(CONF_CLEANING_REMINDER_TIME): selector.TimeSelector(),
            vol.Required(
                CONF_FOOD_REMOVAL_DELAY_HOURS
            ): _positive_integer_selector(),
            vol.Required(
                CONF_FOOD_REMOVAL_REMINDER_BASIS
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=FOOD_REMOVAL_BASIS_ACTUAL,
                            label="Actual feeding time",
                        ),
                        selector.SelectOptionDict(
                            value=FOOD_REMOVAL_BASIS_SCHEDULED,
                            label="Scheduled feeding reminder time",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_FEEDING_OVERDUE_REPEAT_HOURS
            ): _nonnegative_integer_selector(),
            vol.Required(
                CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS
            ): _nonnegative_integer_selector(),
            vol.Required(
                CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS
            ): _nonnegative_integer_selector(),
            vol.Required(
                CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS
            ): _nonnegative_integer_selector(),
        }
    )


def _as_positive_int(value: Any) -> int | None:
    """Return a positive integer without truncating fractional values."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value < 1 or not float(value).is_integer():
        return None
    return int(value)


def _as_nonnegative_int(value: Any) -> int | None:
    """Return a nonnegative integer without truncating fractions."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if value < 0 or not float(value).is_integer():
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
                    CONF_FOOD_REMOVAL_DELAY_HOURS,
                ):
                    value = _as_positive_int(user_input[key])
                    if value is None:
                        errors[key] = "invalid_interval"
                    else:
                        intervals[key] = value

                for key in (
                    CONF_FEEDING_OVERDUE_REPEAT_HOURS,
                    CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
                    CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
                    CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
                ):
                    value = _as_nonnegative_int(user_input[key])
                    if value is None:
                        errors[key] = "invalid_repeat_interval"
                    else:
                        intervals[key] = value

            if not errors:
                options = {
                    CONF_PET_NAME: pet_name,
                    CONF_SPECIES: user_input[CONF_SPECIES].strip(),
                    CONF_BIRTH_DATE: user_input.get(CONF_BIRTH_DATE),
                    CONF_SEX: user_input.get(CONF_SEX),
                    CONF_NOTES: user_input.get(CONF_NOTES),
                    CONF_NOTIFICATION_RECIPIENTS: user_input.get(
                        CONF_NOTIFICATION_RECIPIENTS, []
                    ),
                    CONF_FEEDING_REMINDERS: user_input[CONF_FEEDING_REMINDERS],
                    CONF_SPOT_CLEAN_REMINDERS: user_input[
                        CONF_SPOT_CLEAN_REMINDERS
                    ],
                    CONF_FULL_CLEAN_REMINDERS: user_input[
                        CONF_FULL_CLEAN_REMINDERS
                    ],
                    CONF_FOOD_REMOVAL_REMINDER: user_input[
                        CONF_FOOD_REMOVAL_REMINDER
                    ],
                    CONF_FEEDING_REMINDER_TIME: user_input[
                        CONF_FEEDING_REMINDER_TIME
                    ],
                    CONF_CLEANING_REMINDER_TIME: user_input[
                        CONF_CLEANING_REMINDER_TIME
                    ],
                    CONF_FOOD_REMOVAL_REMINDER_BASIS: user_input[
                        CONF_FOOD_REMOVAL_REMINDER_BASIS
                    ],
                    **intervals,
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=pet_name
                )
                return self.async_create_entry(data=options)

        profile = get_pet_profile(self.config_entry)
        schedule = get_care_schedule(self.config_entry)
        notification_settings = get_notification_settings(self.config_entry)
        suggested_values = user_input or {
            CONF_PET_NAME: profile.pet_name,
            CONF_SPECIES: profile.species,
            CONF_BIRTH_DATE: profile.birth_date,
            CONF_SEX: profile.sex,
            CONF_NOTES: profile.notes,
            CONF_FEEDING_INTERVAL_DAYS: schedule.feeding_interval_days,
            CONF_SPOT_CLEAN_INTERVAL_DAYS: schedule.spot_clean_interval_days,
            CONF_FULL_CLEAN_INTERVAL_DAYS: schedule.full_clean_interval_days,
            CONF_NOTIFICATION_RECIPIENTS: list(
                notification_settings.recipients
            ),
            CONF_FEEDING_REMINDERS: notification_settings.feeding_reminders,
            CONF_SPOT_CLEAN_REMINDERS: notification_settings.spot_clean_reminders,
            CONF_FULL_CLEAN_REMINDERS: notification_settings.full_clean_reminders,
            CONF_FOOD_REMOVAL_REMINDER: (
                notification_settings.food_removal_reminder
            ),
            CONF_FEEDING_REMINDER_TIME: (
                notification_settings.feeding_reminder_time.isoformat()
            ),
            CONF_CLEANING_REMINDER_TIME: (
                notification_settings.cleaning_reminder_time.isoformat()
            ),
            CONF_FOOD_REMOVAL_DELAY_HOURS: (
                notification_settings.food_removal_delay_hours
            ),
            CONF_FOOD_REMOVAL_REMINDER_BASIS: (
                notification_settings.food_removal_reminder_basis
            ),
            CONF_FEEDING_OVERDUE_REPEAT_HOURS: (
                notification_settings.feeding_overdue_repeat_hours
            ),
            CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS: (
                notification_settings.spot_clean_overdue_repeat_hours
            ),
            CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS: (
                notification_settings.full_clean_overdue_repeat_hours
            ),
            CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS: (
                notification_settings.food_removal_overdue_repeat_hours
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(),
                suggested_values,
            ),
            errors=errors,
        )
