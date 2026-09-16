"""WebSocket API for Lizard Care journal cards."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .journal import JournalEventType, normalize_manual_metadata

WS_TYPE_GET_JOURNAL = f"{DOMAIN}/journal/get"
WS_TYPE_CREATE_JOURNAL = f"{DOMAIN}/journal/create"


def journal_response(runtime: Any, entry_id: str, limit: int) -> dict[str, Any]:
    """Build a bounded WebSocket response for one pet runtime."""
    entries = runtime.journal.entries(limit=limit)
    return {
        "entry_id": entry_id,
        "entries": [entry.as_storage() for entry in entries],
    }


def _journal_runtime_for_entity(
    hass: HomeAssistant,
    entity_id: str,
) -> tuple[str, Any] | None:
    """Resolve an entity to its loaded Lizard Care runtime."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    if registry_entry is None or registry_entry.config_entry_id is None:
        return None
    entry = hass.config_entries.async_get_entry(registry_entry.config_entry_id)
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
    ):
        return None
    return entry.entry_id, entry.runtime_data


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_GET_JOURNAL,
        vol.Required("entity_id"): str,
        vol.Optional("limit", default=5): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1000)
        ),
    }
)
@websocket_api.async_response
async def websocket_get_journal(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return newest-first entries for an authorized journal entity."""
    entity_id = msg["entity_id"]
    if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_ALLOWED,
            "Not authorized to read this entity",
        )
        return
    resolved = _journal_runtime_for_entity(hass, entity_id)
    if resolved is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            "Lizard Care journal entity was not found or is not loaded",
        )
        return
    entry_id, runtime = resolved
    connection.send_result(
        msg["id"], journal_response(runtime, entry_id, msg["limit"])
    )


def _journal_timestamp(value: object) -> datetime | None:
    """Parse an optional timezone-aware journal timestamp."""
    if value is None:
        return None
    parsed = dt_util.parse_datetime(value) if isinstance(value, str) else value
    if parsed is None or parsed.tzinfo is None:
        raise ValueError("Journal timestamp must include a timezone")
    return parsed


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_TYPE_CREATE_JOURNAL,
        vol.Required("entity_id"): str,
        vol.Required("event_type"): vol.In(
            [event_type.value for event_type in JournalEventType]
        ),
        vol.Optional("note"): vol.All(str, vol.Length(max=2000)),
        vol.Optional("timestamp"): str,
        vol.Optional("weight_value"): vol.Any(int, float),
        vol.Optional("weight_unit"): str,
    }
)
@websocket_api.async_response
async def websocket_create_journal(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Create one manual entry for an authorized journal entity."""
    entity_id = msg["entity_id"]
    if not connection.user.permissions.check_entity(entity_id, POLICY_READ):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_ALLOWED,
            "Not authorized to access this entity",
        )
        return
    resolved = _journal_runtime_for_entity(hass, entity_id)
    if resolved is None:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_FOUND,
            "Lizard Care journal entity was not found or is not loaded",
        )
        return
    entry_id, runtime = resolved
    try:
        metadata = normalize_manual_metadata(
            msg["event_type"],
            None,
            weight_value=msg.get("weight_value"),
            weight_unit=msg.get("weight_unit"),
        )
        entry = await runtime.async_add_journal_entry(
            msg["event_type"],
            timestamp=_journal_timestamp(msg.get("timestamp")),
            note=msg.get("note"),
            metadata=metadata,
        )
    except (TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    connection.send_result(
        msg["id"], {"entry_id": entry_id, "journal_entry": entry.as_storage()}
    )


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register journal WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_get_journal)
    websocket_api.async_register_command(hass, websocket_create_journal)
