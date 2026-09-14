"""Serve the lightweight Lizard Care journal card."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

CARD_URL = "/lizardcare/lizard-care-history-card.js"
CARD_PATH = Path(__file__).parent / "www" / "lizard-care-history-card.js"


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Expose the bundled card JavaScript through Home Assistant HTTP."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_PATH), False)]
    )
