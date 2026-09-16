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
    CONF_NORMALIZED_PET_NAME,
    CONF_NOTES,
    CONF_PET_NAME,
    CONF_SEX,
    CONF_SPECIES,
    CONF_SPOT_CLEAN_ENABLED,
    CONF_SPOT_CLEAN_INSTRUCTIONS,
    CONF_SPOT_CLEAN_INTERVAL_DAYS,
    CONF_VACATION_CALENDAR,
    DEFAULT_SPECIES,
    DOMAIN,
    TIME_UNIT_HOURS,
    TIME_UNIT_MINUTES,
)
from .food_removal import get_food_removal_settings
from .instructions import clean_instruction, get_care_instructions
from .profile import get_pet_profile, normalize_pet_name, pet_name_is_duplicate
from .schedule import get_care_schedule
from .vacation import get_vacation_calendar


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


def _day_of_month_selector() -> selector.NumberSelector:
    """Return a calendar day selector."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=1,
            max=31,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _feeding_schema() -> vol.Schema:
    """Return feeding schedule fields only."""
    return vol.Schema(
        {vol.Required(CONF_FEEDING_INTERVAL_DAYS): _positive_integer_selector()}
    )


def _cleaning_mode_schema() -> vol.Schema:
    """Return the cleaning schedule mode selector."""
    return vol.Schema(
        {
            vol.Required(CONF_CLEANING_SCHEDULE_MODE): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=CLEANING_SCHEDULE_INTERVAL,
                                label="Independent",
                            ),
                            selector.SelectOptionDict(
                                value=CLEANING_SCHEDULE_MONTHLY,
                                label="Monthly",
                            ),
                            selector.SelectOptionDict(
                                value=CLEANING_SCHEDULE_ALTERNATING,
                                label="Alternating",
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        }
    )


def _independent_cleaning_schema() -> vol.Schema:
    """Return common Independent cleaning fields."""
    return vol.Schema(
        {
            vol.Required(CONF_FULL_CLEAN_INTERVAL_DAYS): _positive_integer_selector(),
            vol.Required(
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN
            ): selector.BooleanSelector(),
            vol.Required(CONF_SPOT_CLEAN_ENABLED): selector.BooleanSelector(),
        }
    )


def _spot_cleaning_schema() -> vol.Schema:
    """Return enabled Spot Clean scheduling fields."""
    return vol.Schema(
        {vol.Required(CONF_SPOT_CLEAN_INTERVAL_DAYS): _positive_integer_selector()}
    )


def _monthly_cleaning_schema() -> vol.Schema:
    """Return Monthly cleaning schedule fields only."""
    return vol.Schema(
        {
            vol.Required(CONF_CLEANING_DAY_OF_MONTH): _day_of_month_selector(),
            vol.Required(CONF_FULL_CLEAN_EVERY): _positive_integer_selector(),
            vol.Required(CONF_CLEANING_CYCLE_ANCHOR): selector.DateSelector(),
        }
    )


def _alternating_cleaning_schema() -> vol.Schema:
    """Return Alternating cleaning schedule fields only."""
    return vol.Schema(
        {
            vol.Required(
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS
            ): _positive_integer_selector(),
            vol.Required(
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE
            ): selector.DateSelector(),
            vol.Required(CONF_ALTERNATING_ANCHOR_TYPE): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value="spot_clean", label="Spot Clean"
                            ),
                            selector.SelectOptionDict(
                                value="full_clean", label="Full Clean"
                            ),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            ),
        }
    )


def _food_removal_schema() -> vol.Schema:
    """Return food-removal care timing fields only."""
    return vol.Schema(
        {
            vol.Required(CONF_FOOD_REMOVAL_ANCHOR_TIME): selector.TimeSelector(),
            vol.Required(CONF_FOOD_REMOVAL_DELAY): _positive_integer_selector(),
            vol.Required(CONF_FOOD_REMOVAL_DELAY_UNIT): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=TIME_UNIT_MINUTES,
                            label="Minutes",
                        ),
                        selector.SelectOptionDict(
                            value=TIME_UNIT_HOURS,
                            label="Hours",
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _instructions_schema() -> vol.Schema:
    """Return optional care instruction fields."""
    multiline = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
    return vol.Schema(
        {
            vol.Optional(CONF_FEEDING_INSTRUCTIONS): multiline,
            vol.Optional(CONF_SPOT_CLEAN_INSTRUCTIONS): multiline,
            vol.Optional(CONF_FULL_CLEAN_INSTRUCTIONS): multiline,
        }
    )


def _vacation_schema() -> vol.Schema:
    """Return the optional Vacation Mode calendar field."""
    return vol.Schema(
        {
            vol.Optional(CONF_VACATION_CALENDAR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="calendar")
            )
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
    """Handle feature-oriented pet options."""

    _independent_updates: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the feature-oriented options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "feeding",
                "cleaning",
                "food_removal",
                "instructions",
                "vacation",
                "profile",
            ],
        )

    async def async_step_feeding(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit feeding schedule settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            interval = _as_positive_int(user_input[CONF_FEEDING_INTERVAL_DAYS])
            if interval is None:
                errors[CONF_FEEDING_INTERVAL_DAYS] = "invalid_interval"
            else:
                return self._async_save_options({CONF_FEEDING_INTERVAL_DAYS: interval})
        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "feeding",
            _feeding_schema(),
            user_input
            or {
                CONF_FEEDING_INTERVAL_DAYS: schedule.feeding_interval_days,
            },
            errors,
        )

    async def async_step_cleaning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the cleaning schedule mode to edit."""
        if user_input is not None:
            cleaning_mode = user_input[CONF_CLEANING_SCHEDULE_MODE]
            if cleaning_mode == CLEANING_SCHEDULE_INTERVAL:
                return await self.async_step_cleaning_independent()
            if cleaning_mode == CLEANING_SCHEDULE_MONTHLY:
                return await self.async_step_cleaning_monthly()
            return await self.async_step_cleaning_alternating()

        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "cleaning",
            _cleaning_mode_schema(),
            {CONF_CLEANING_SCHEDULE_MODE: (schedule.cleaning_schedule_mode)},
            {},
        )

    async def async_step_cleaning_independent(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit Independent cleaning settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            full_interval = _as_positive_int(user_input[CONF_FULL_CLEAN_INTERVAL_DAYS])
            if full_interval is None:
                errors[CONF_FULL_CLEAN_INTERVAL_DAYS] = "invalid_interval"
            else:
                updates = {
                    CONF_CLEANING_SCHEDULE_MODE: CLEANING_SCHEDULE_INTERVAL,
                    CONF_FULL_CLEAN_INTERVAL_DAYS: full_interval,
                    CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: user_input[
                        CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN
                    ],
                    CONF_SPOT_CLEAN_ENABLED: user_input[CONF_SPOT_CLEAN_ENABLED],
                }
                if user_input[CONF_SPOT_CLEAN_ENABLED]:
                    self._independent_updates = updates
                    return await self.async_step_cleaning_spot()
                return self._async_save_options(updates)

        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "cleaning_independent",
            _independent_cleaning_schema(),
            user_input
            or {
                CONF_FULL_CLEAN_INTERVAL_DAYS: (schedule.full_clean_interval_days),
                CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN: (
                    schedule.full_clean_satisfies_spot_clean
                ),
                CONF_SPOT_CLEAN_ENABLED: schedule.spot_clean_enabled,
            },
            errors,
        )

    async def async_step_cleaning_spot(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit enabled Spot Clean scheduling."""
        errors: dict[str, str] = {}
        if user_input is not None:
            interval = _as_positive_int(user_input[CONF_SPOT_CLEAN_INTERVAL_DAYS])
            if interval is None:
                errors[CONF_SPOT_CLEAN_INTERVAL_DAYS] = "invalid_interval"
            else:
                updates = dict(self._independent_updates or {})
                updates[CONF_SPOT_CLEAN_INTERVAL_DAYS] = interval
                return self._async_save_options(updates)

        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "cleaning_spot",
            _spot_cleaning_schema(),
            user_input
            or {CONF_SPOT_CLEAN_INTERVAL_DAYS: (schedule.spot_clean_interval_days)},
            errors,
        )

    async def async_step_cleaning_monthly(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit Monthly cleaning settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaning_day = _as_positive_int(user_input[CONF_CLEANING_DAY_OF_MONTH])
            full_clean_every = _as_positive_int(user_input[CONF_FULL_CLEAN_EVERY])
            if cleaning_day is None or cleaning_day > 31:
                errors[CONF_CLEANING_DAY_OF_MONTH] = "invalid_day_of_month"
            if full_clean_every is None:
                errors[CONF_FULL_CLEAN_EVERY] = "invalid_interval"
            if not errors:
                return self._async_save_options(
                    {
                        CONF_CLEANING_SCHEDULE_MODE: (CLEANING_SCHEDULE_MONTHLY),
                        CONF_CLEANING_DAY_OF_MONTH: cleaning_day,
                        CONF_FULL_CLEAN_EVERY: full_clean_every,
                        CONF_CLEANING_CYCLE_ANCHOR: user_input[
                            CONF_CLEANING_CYCLE_ANCHOR
                        ],
                    }
                )

        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "cleaning_monthly",
            _monthly_cleaning_schema(),
            user_input
            or {
                CONF_CLEANING_DAY_OF_MONTH: schedule.cleaning_day_of_month,
                CONF_FULL_CLEAN_EVERY: schedule.full_clean_every,
                CONF_CLEANING_CYCLE_ANCHOR: (
                    schedule.cleaning_cycle_anchor.isoformat()
                ),
            },
            errors,
        )

    async def async_step_cleaning_alternating(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit Alternating cleaning settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            interval = _as_positive_int(
                user_input[CONF_ALTERNATING_CLEANING_INTERVAL_DAYS]
            )
            if interval is None:
                errors[CONF_ALTERNATING_CLEANING_INTERVAL_DAYS] = "invalid_interval"
            else:
                return self._async_save_options(
                    {
                        CONF_CLEANING_SCHEDULE_MODE: (CLEANING_SCHEDULE_ALTERNATING),
                        CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: interval,
                        CONF_ALTERNATING_CLEANING_ANCHOR_DATE: user_input[
                            CONF_ALTERNATING_CLEANING_ANCHOR_DATE
                        ],
                        CONF_ALTERNATING_ANCHOR_TYPE: user_input[
                            CONF_ALTERNATING_ANCHOR_TYPE
                        ],
                    }
                )

        schedule = get_care_schedule(self.config_entry)
        return self._async_show_section_form(
            "cleaning_alternating",
            _alternating_cleaning_schema(),
            user_input
            or {
                CONF_ALTERNATING_CLEANING_INTERVAL_DAYS: (
                    schedule.alternating_interval_days
                ),
                CONF_ALTERNATING_CLEANING_ANCHOR_DATE: (
                    schedule.alternating_anchor_date.isoformat()
                ),
                CONF_ALTERNATING_ANCHOR_TYPE: (schedule.alternating_anchor_type.value),
            },
            errors,
        )

    async def async_step_food_removal(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit food-removal care timing."""
        errors: dict[str, str] = {}
        if user_input is not None:
            delay = _as_positive_int(user_input[CONF_FOOD_REMOVAL_DELAY])
            if delay is None:
                errors[CONF_FOOD_REMOVAL_DELAY] = "invalid_interval"
            else:
                return self._async_save_options(
                    {
                        CONF_FOOD_REMOVAL_ANCHOR_TIME: user_input[
                            CONF_FOOD_REMOVAL_ANCHOR_TIME
                        ],
                        CONF_FOOD_REMOVAL_DELAY: delay,
                        CONF_FOOD_REMOVAL_DELAY_UNIT: user_input[
                            CONF_FOOD_REMOVAL_DELAY_UNIT
                        ],
                    }
                )

        settings = get_food_removal_settings(self.config_entry)
        return self._async_show_section_form(
            "food_removal",
            _food_removal_schema(),
            user_input
            or {
                CONF_FOOD_REMOVAL_ANCHOR_TIME: (settings.anchor_time.isoformat()),
                CONF_FOOD_REMOVAL_DELAY: settings.delay_value,
                CONF_FOOD_REMOVAL_DELAY_UNIT: settings.delay_unit,
            },
            errors,
        )

    async def async_step_instructions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit optional care instructions."""
        if user_input is not None:
            return self._async_save_options(
                {
                    CONF_FEEDING_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_FEEDING_INSTRUCTIONS)
                    ),
                    CONF_SPOT_CLEAN_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_SPOT_CLEAN_INSTRUCTIONS)
                    ),
                    CONF_FULL_CLEAN_INSTRUCTIONS: clean_instruction(
                        user_input.get(CONF_FULL_CLEAN_INSTRUCTIONS)
                    ),
                }
            )

        instructions = get_care_instructions(self.config_entry)
        return self._async_show_section_form(
            "instructions",
            _instructions_schema(),
            {
                CONF_FEEDING_INSTRUCTIONS: instructions.feeding,
                CONF_SPOT_CLEAN_INSTRUCTIONS: instructions.spot_clean,
                CONF_FULL_CLEAN_INSTRUCTIONS: instructions.full_clean,
            },
            {},
        )

    async def async_step_vacation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the Vacation Mode calendar."""
        if user_input is not None:
            return self._async_save_options(
                {CONF_VACATION_CALENDAR: user_input.get(CONF_VACATION_CALENDAR)}
            )

        return self._async_show_section_form(
            "vacation",
            _vacation_schema(),
            {CONF_VACATION_CALENDAR: get_vacation_calendar(self.config_entry)},
            {},
        )

    async def async_step_profile(
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
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=pet_name
                )
                return self._async_save_options(
                    {
                        CONF_PET_NAME: pet_name,
                        CONF_SPECIES: user_input[CONF_SPECIES].strip(),
                        CONF_BIRTH_DATE: user_input.get(CONF_BIRTH_DATE),
                        CONF_SEX: user_input.get(CONF_SEX),
                        CONF_NOTES: user_input.get(CONF_NOTES),
                    }
                )

        profile = get_pet_profile(self.config_entry)
        return self._async_show_section_form(
            "profile",
            _profile_schema(),
            user_input
            or {
                CONF_PET_NAME: profile.pet_name,
                CONF_SPECIES: profile.species,
                CONF_BIRTH_DATE: profile.birth_date,
                CONF_SEX: profile.sex,
                CONF_NOTES: profile.notes,
            },
            errors,
        )

    @callback
    def _async_show_section_form(
        self,
        step_id: str,
        schema: vol.Schema,
        suggested_values: dict[str, Any],
        errors: dict[str, str],
    ) -> ConfigFlowResult:
        """Show one options section with current values."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                schema,
                suggested_values,
            ),
            errors=errors,
        )

    @callback
    def _async_save_options(self, updates: dict[str, Any]) -> ConfigFlowResult:
        """Merge one section without resetting unrelated option values."""
        return self.async_create_entry(data={**self.config_entry.options, **updates})
