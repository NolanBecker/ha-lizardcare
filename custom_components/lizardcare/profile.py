"""Pet profile helpers for Lizard Care."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BIRTH_DATE,
    CONF_NOTES,
    CONF_PET_NAME,
    CONF_SEX,
    CONF_SPECIES,
    DOMAIN,
)


@dataclass(frozen=True, slots=True)
class PetProfile:
    """Resolved profile for one pet."""

    pet_name: str
    species: str
    birth_date: str | None
    sex: str | None
    notes: str | None


def _entry_value(entry: ConfigEntry, key: str) -> str | None:
    """Return an option override or the original config-entry value."""
    if key in entry.options:
        value = entry.options[key]
    else:
        value = entry.data.get(key)
    return value if isinstance(value, str) and value else None


def get_pet_profile(entry: ConfigEntry) -> PetProfile:
    """Resolve the current profile, with options overriding setup data."""
    return PetProfile(
        pet_name=_entry_value(entry, CONF_PET_NAME) or entry.title,
        species=_entry_value(entry, CONF_SPECIES) or "",
        birth_date=_entry_value(entry, CONF_BIRTH_DATE),
        sex=_entry_value(entry, CONF_SEX),
        notes=_entry_value(entry, CONF_NOTES),
    )


def get_birth_date(entry: ConfigEntry) -> date | None:
    """Return the configured birthday as a date, if valid."""
    value = get_pet_profile(entry).birth_date
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_pet_name(name: str) -> str:
    """Normalize a pet name for duplicate detection."""
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def pet_name_is_duplicate(
    hass: HomeAssistant,
    normalized_name: str,
    *,
    exclude_entry_id: str | None = None,
) -> bool:
    """Return whether another entry has the effective normalized pet name."""
    return any(
        entry.entry_id != exclude_entry_id
        and normalize_pet_name(get_pet_profile(entry).pet_name) == normalized_name
        for entry in hass.config_entries.async_entries(DOMAIN)
    )
