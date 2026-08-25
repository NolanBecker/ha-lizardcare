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
from .profile import get_birth_date

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
)

AGE_DESCRIPTION = SensorEntityDescription(
    key="age",
    translation_key="age",
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
            LizardCareAgeSensor(entry),
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
