"""Sensor platform for Lizard Care."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import LizardCareConfigEntry
from .coordinator import LizardCareData
from .entity import LizardCareEntity
from .profile import get_birth_date, get_pet_profile
from .schedule import (
    CareSchedule,
    CareStatus,
    calculate_care_status,
    calculate_next_due,
    get_care_schedule,
)

TIMESTAMP_DESCRIPTIONS = (
    SensorEntityDescription(
        key="last_fed",
        translation_key="last_fed",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_spot_clean",
        translation_key="last_spot_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_full_clean",
        translation_key="last_full_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_food_removed",
        translation_key="last_food_removed",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

AGE_DESCRIPTION = SensorEntityDescription(
    key="age",
    translation_key="age",
)

PROFILE_DESCRIPTIONS = (
    SensorEntityDescription(
        key="species",
        translation_key="species",
        icon="mdi:lizard",
    ),
    SensorEntityDescription(
        key="birthday",
        translation_key="birthday",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="sex",
        translation_key="sex",
        icon="mdi:gender-male-female",
    ),
    SensorEntityDescription(
        key="notes",
        translation_key="notes",
        icon="mdi:note-text-outline",
    ),
)

MAX_SENSOR_STATE_LENGTH = 255

NEXT_DUE_DESCRIPTIONS = (
    SensorEntityDescription(
        key="next_feeding",
        translation_key="next_feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="next_spot_clean",
        translation_key="next_spot_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="next_full_clean",
        translation_key="next_full_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

STATUS_DESCRIPTIONS = (
    SensorEntityDescription(
        key="feeding_status",
        translation_key="feeding_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
    SensorEntityDescription(
        key="spot_clean_status",
        translation_key="spot_clean_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
    SensorEntityDescription(
        key="full_clean_status",
        translation_key="full_clean_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care sensors."""
    data = entry.runtime_data
    async_add_entities(
        [
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[0],
                lambda state: state.last_fed,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[1],
                lambda state: state.last_spot_clean,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[2],
                lambda state: state.last_full_clean,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[3],
                lambda state: state.last_food_removed,
            ),
            LizardCareAgeSensor(entry),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[0],
                lambda config_entry: get_pet_profile(config_entry).species
                or None,
            ),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[1],
                get_birth_date,
            ),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[2],
                lambda config_entry: get_pet_profile(config_entry).sex,
            ),
            LizardCareNotesSensor(entry),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[0],
                lambda state: state.last_fed,
                lambda config: config.feeding_interval_days,
            ),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[1],
                lambda state: state.last_spot_clean,
                lambda config: config.spot_clean_interval_days,
            ),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[2],
                lambda state: state.last_full_clean,
                lambda config: config.full_clean_interval_days,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[0],
                lambda state: state.last_fed,
                lambda config: config.feeding_interval_days,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[1],
                lambda state: state.last_spot_clean,
                lambda config: config.spot_clean_interval_days,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[2],
                lambda state: state.last_full_clean,
                lambda config: config.full_clean_interval_days,
            ),
        ]
    )


class LizardCareTimestampSensor(LizardCareEntity, SensorEntity):
    """Show the timestamp of a pet care action."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        data: LizardCareData,
        entry_id: str,
        description: SensorEntityDescription,
        value_fn: Callable[[LizardCareData], datetime | None],
    ) -> None:
        """Initialize a care timestamp sensor."""
        super().__init__(data, entry_id, description)
        self._value_fn = value_fn

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent care-action timestamp."""
        return self._value_fn(self._data)


class LizardCareAgeSensor(LizardCareEntity, SensorEntity):
    """Show the pet's age from its birthday or hatch date."""

    entity_description = AGE_DESCRIPTION

    def __init__(self, entry: LizardCareConfigEntry) -> None:
        """Initialize the age sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, AGE_DESCRIPTION)
        self._entry = entry

    async def async_added_to_hass(self) -> None:
        """Update the age when the local date changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._async_date_changed,
                hour=0,
                minute=0,
                second=0,
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the pet's age in years and months."""
        birth_date = get_birth_date(self._entry)
        if birth_date is None:
            return None
        return _format_age(birth_date, dt_util.now().date())

    @callback
    def _async_date_changed(self, _now: datetime) -> None:
        """Refresh the age at local midnight."""
        self.async_write_ha_state()


class LizardCareProfileSensor(LizardCareEntity, SensorEntity):
    """Expose a read-only value from the pet profile."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        value_fn: Callable[[LizardCareConfigEntry], str | date | None],
    ) -> None:
        """Initialize a profile sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._value_fn = value_fn

    @property
    def native_value(self) -> str | date | None:
        """Return the current resolved profile value."""
        return self._value_fn(self._entry)


class LizardCareNotesSensor(LizardCareEntity, SensorEntity):
    """Expose profile notes without exceeding Home Assistant state limits."""

    entity_description = PROFILE_DESCRIPTIONS[3]

    def __init__(self, entry: LizardCareConfigEntry) -> None:
        """Initialize the notes sensor."""
        super().__init__(
            entry.runtime_data,
            entry.entry_id,
            PROFILE_DESCRIPTIONS[3],
        )
        self._entry = entry

    @property
    def native_value(self) -> str | None:
        """Return notes directly when they fit in an entity state."""
        notes = get_pet_profile(self._entry).notes
        if notes is None:
            return None
        if len(notes) <= MAX_SENSOR_STATE_LENGTH:
            return notes
        return f"{notes[: MAX_SENSOR_STATE_LENGTH - 3]}..."

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose long notes safely as an attribute."""
        notes = get_pet_profile(self._entry).notes
        if notes is None:
            return None
        return {"notes": notes}


class LizardCareNextDueSensor(LizardCareEntity, SensorEntity):
    """Show the next scheduled time for a care action."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        last_completed_fn: Callable[[LizardCareData], datetime | None],
        interval_fn: Callable[[CareSchedule], int],
    ) -> None:
        """Initialize a next-due sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._last_completed_fn = last_completed_fn
        self._interval_fn = interval_fn

    @property
    def native_value(self) -> datetime | None:
        """Return the calculated next due timestamp."""
        return calculate_next_due(
            self._last_completed_fn(self._data),
            self._interval_fn(get_care_schedule(self._entry)),
        )


class LizardCareStatusSensor(LizardCareEntity, SensorEntity):
    """Show whether a care action is due based on the local date."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        last_completed_fn: Callable[[LizardCareData], datetime | None],
        interval_fn: Callable[[CareSchedule], int],
    ) -> None:
        """Initialize a care status sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._last_completed_fn = last_completed_fn
        self._interval_fn = interval_fn

    async def async_added_to_hass(self) -> None:
        """Update status when the local date changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._async_date_changed,
                hour=0,
                minute=0,
                second=0,
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the calculated schedule status."""
        next_due = calculate_next_due(
            self._last_completed_fn(self._data),
            self._interval_fn(get_care_schedule(self._entry)),
        )
        status = calculate_care_status(next_due)
        return status.value if status is not None else None

    @callback
    def _async_date_changed(self, _now: datetime) -> None:
        """Refresh status at local midnight."""
        self.async_write_ha_state()


def _format_age(birth_date: date, today: date) -> str | None:
    """Format an age using completed calendar years and months."""
    if birth_date > today:
        return None

    total_months = (today.year - birth_date.year) * 12
    total_months += today.month - birth_date.month
    if today.day < birth_date.day:
        total_months -= 1

    years, months = divmod(max(total_months, 0), 12)
    parts: list[str] = []
    if years:
        parts.append(f"{years} {'year' if years == 1 else 'years'}")
    if months or not years:
        parts.append(f"{months} {'month' if months == 1 else 'months'}")
    return ", ".join(parts)
