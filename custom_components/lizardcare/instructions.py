"""Care-instruction option helpers for Lizard Care."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_FEEDING_INSTRUCTIONS,
    CONF_FULL_CLEAN_INSTRUCTIONS,
    CONF_SPOT_CLEAN_INSTRUCTIONS,
    DEFAULT_FEEDING_INSTRUCTIONS,
    DEFAULT_FULL_CLEAN_INSTRUCTIONS,
    DEFAULT_SPOT_CLEAN_INSTRUCTIONS,
)


@dataclass(frozen=True, slots=True)
class CareInstructions:
    """Resolved reference instructions for existing care tasks."""

    feeding: str
    spot_clean: str
    full_clean: str


def clean_instruction(value: object) -> str:
    """Trim outer whitespace while preserving intentional internal layout."""
    return value.strip() if isinstance(value, str) else ""


def _entry_instruction(entry: ConfigEntry, key: str, default: str) -> str:
    """Return an option override or a backward-compatible data value."""
    value = (
        entry.options[key]
        if key in entry.options
        else entry.data.get(key, default)
    )
    return clean_instruction(value)


def get_care_instructions(entry: ConfigEntry) -> CareInstructions:
    """Resolve all task instructions with blank defaults."""
    return CareInstructions(
        feeding=_entry_instruction(
            entry, CONF_FEEDING_INSTRUCTIONS, DEFAULT_FEEDING_INSTRUCTIONS
        ),
        spot_clean=_entry_instruction(
            entry,
            CONF_SPOT_CLEAN_INSTRUCTIONS,
            DEFAULT_SPOT_CLEAN_INSTRUCTIONS,
        ),
        full_clean=_entry_instruction(
            entry,
            CONF_FULL_CLEAN_INSTRUCTIONS,
            DEFAULT_FULL_CLEAN_INSTRUCTIONS,
        ),
    )
