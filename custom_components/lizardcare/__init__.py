"""The Lizard Care integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_PET_NAME, CONF_SPECIES, DOMAIN, MANUFACTURER
from .coordinator import LizardCareData

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON)

LizardCareConfigEntry = ConfigEntry[LizardCareData]


async def async_setup_entry(
    hass: HomeAssistant, entry: LizardCareConfigEntry
) -> bool:
    """Set up Lizard Care from a config entry."""
    data = LizardCareData(hass, entry.entry_id)
    await data.async_load()
    entry.runtime_data = data

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=MANUFACTURER,
        model=entry.data[CONF_SPECIES],
        name=entry.data[CONF_PET_NAME],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: LizardCareConfigEntry
) -> bool:
    """Unload a Lizard Care config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
