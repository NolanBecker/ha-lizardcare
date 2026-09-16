"""Shared config-entry value resolution for Lizard Care."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry


def get_config_value(
    entry: ConfigEntry, key: str, default: Any = None
) -> Any:
    """Return the latest option, falling back to initial entry data."""
    if key in entry.options:
        return entry.options[key]
    return getattr(entry, "data", {}).get(key, default)
