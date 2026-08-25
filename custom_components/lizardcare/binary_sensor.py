"""Binary sensor platform for Lizard Care."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LizardCareConfigEntry
from .coordinator import LizardCareData
from .entity import LizardCareEntity

FOOD_IN_ENCLOSURE_DESCRIPTION = BinarySensorEntityDescription(
    key="food_in_enclosure",
    translation_key="food_in_enclosure",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care binary sensors."""
    async_add_entities(
        [LizardCareFoodInEnclosureSensor(entry.runtime_data, entry.entry_id)]
    )


class LizardCareFoodInEnclosureSensor(LizardCareEntity, BinarySensorEntity):
    """Show whether food is currently in the enclosure."""

    entity_description = FOOD_IN_ENCLOSURE_DESCRIPTION

    def __init__(self, data: LizardCareData, entry_id: str) -> None:
        """Initialize the food-in-enclosure binary sensor."""
        super().__init__(data, entry_id, FOOD_IN_ENCLOSURE_DESCRIPTION)

    @property
    def is_on(self) -> bool:
        """Return whether food is currently in the enclosure."""
        return self._data.food_in_enclosure
