"""Button platform for Lizard Care."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LizardCareConfigEntry
from .coordinator import LizardCareData
from .entity import LizardCareEntity

BUTTON_DESCRIPTIONS = (
    ButtonEntityDescription(key="feed", translation_key="feed"),
    ButtonEntityDescription(key="remove_food", translation_key="remove_food"),
    ButtonEntityDescription(key="spot_clean", translation_key="spot_clean"),
    ButtonEntityDescription(key="full_clean", translation_key="full_clean"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care buttons."""
    data = entry.runtime_data
    async_add_entities(
        [
            LizardCareButton(
                data,
                entry.entry_id,
                BUTTON_DESCRIPTIONS[0],
                data.async_feed,
            ),
            LizardCareButton(
                data,
                entry.entry_id,
                BUTTON_DESCRIPTIONS[1],
                data.async_remove_food,
            ),
            LizardCareButton(
                data,
                entry.entry_id,
                BUTTON_DESCRIPTIONS[2],
                data.async_spot_clean,
            ),
            LizardCareButton(
                data,
                entry.entry_id,
                BUTTON_DESCRIPTIONS[3],
                data.async_full_clean,
            ),
        ]
    )


class LizardCareButton(LizardCareEntity, ButtonEntity):
    """A button that records a pet care action."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        data: LizardCareData,
        entry_id: str,
        description: ButtonEntityDescription,
        action: Callable[[], Awaitable[None]],
    ) -> None:
        """Initialize a care-action button."""
        super().__init__(data, entry_id, description)
        self._action = action

    async def async_press(self) -> None:
        """Handle a button press."""
        await self._action()
