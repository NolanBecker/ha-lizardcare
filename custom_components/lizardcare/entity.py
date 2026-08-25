"""Base entity for Lizard Care."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN
from .coordinator import LizardCareData


class LizardCareEntity(Entity):
    """Base class for entities belonging to a pet device."""

    _attr_has_entity_name = True
    entity_description: EntityDescription

    def __init__(
        self,
        data: LizardCareData,
        entry_id: str,
        description: EntityDescription,
    ) -> None:
        """Initialize a Lizard Care entity."""
        self.entity_description = description
        self._data = data
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

    async def async_added_to_hass(self) -> None:
        """Subscribe to care-state updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._data.async_add_listener(self.async_write_ha_state)
        )
