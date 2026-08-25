"""Sensor platform for Lizard Care."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LizardCareConfigEntry
from .coordinator import LizardCareData
from .entity import LizardCareEntity

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
