"""Sensor platform for Lizard Care."""

from __future__ import annotations

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

LAST_FED_DESCRIPTION = SensorEntityDescription(
    key="last_fed",
    translation_key="last_fed",
    device_class=SensorDeviceClass.TIMESTAMP,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care sensors."""
    async_add_entities(
        [LizardCareLastFedSensor(entry.runtime_data, entry.entry_id)]
    )


class LizardCareLastFedSensor(LizardCareEntity, SensorEntity):
    """Show the pet's most recent feeding time."""

    entity_description = LAST_FED_DESCRIPTION

    def __init__(self, data: LizardCareData, entry_id: str) -> None:
        """Initialize the last-fed sensor."""
        super().__init__(data, entry_id, LAST_FED_DESCRIPTION)

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent feeding timestamp."""
        return self._data.last_fed
