"""Date/time platform for Lizard Care."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from homeassistant.components.datetime import (
    DateTimeEntity,
    DateTimeEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LizardCareConfigEntry
from .coordinator import LizardCareData
from .entity import LizardCareEntity

DATETIME_DESCRIPTIONS = (
    DateTimeEntityDescription(
        key="set_last_fed",
        translation_key="set_last_fed",
        entity_category=EntityCategory.CONFIG,
    ),
    DateTimeEntityDescription(
        key="set_last_food_removed",
        translation_key="set_last_food_removed",
        entity_category=EntityCategory.CONFIG,
    ),
    DateTimeEntityDescription(
        key="set_last_spot_clean",
        translation_key="set_last_spot_clean",
        entity_category=EntityCategory.CONFIG,
    ),
    DateTimeEntityDescription(
        key="set_last_full_clean",
        translation_key="set_last_full_clean",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care date/time entities."""
    data = entry.runtime_data
    async_add_entities(
        [
            LizardCareDateTime(
                data,
                entry.entry_id,
                DATETIME_DESCRIPTIONS[0],
                lambda state: state.last_fed,
                data.async_set_last_fed,
            ),
            LizardCareDateTime(
                data,
                entry.entry_id,
                DATETIME_DESCRIPTIONS[1],
                lambda state: state.last_food_removed,
                data.async_set_last_food_removed,
            ),
            LizardCareDateTime(
                data,
                entry.entry_id,
                DATETIME_DESCRIPTIONS[2],
                lambda state: state.last_spot_clean,
                data.async_set_last_spot_clean,
            ),
            LizardCareDateTime(
                data,
                entry.entry_id,
                DATETIME_DESCRIPTIONS[3],
                lambda state: state.last_full_clean,
                data.async_set_last_full_clean,
            ),
        ]
    )


class LizardCareDateTime(LizardCareEntity, DateTimeEntity):
    """Allow correction of one stored care timestamp."""

    entity_description: DateTimeEntityDescription

    def __init__(
        self,
        data: LizardCareData,
        entry_id: str,
        description: DateTimeEntityDescription,
        value_fn: Callable[[LizardCareData], datetime | None],
        set_value_fn: Callable[[datetime], Awaitable[None]],
    ) -> None:
        """Initialize a care timestamp editor."""
        super().__init__(data, entry_id, description)
        self._value_fn = value_fn
        self._set_value_fn = set_value_fn

    @property
    def native_value(self) -> datetime | None:
        """Return the corresponding stored care timestamp."""
        return self._value_fn(self._data)

    async def async_set_value(self, value: datetime) -> None:
        """Correct the corresponding stored care timestamp."""
        await self._set_value_fn(value)
