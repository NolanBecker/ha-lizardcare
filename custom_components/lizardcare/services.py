"""Home Assistant actions for the Lizard Care journal."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import LizardCareData
from .journal import JournalEventType, normalize_manual_metadata

SERVICE_ADD_JOURNAL_ENTRY = "add_journal_entry"
SERVICE_DELETE_JOURNAL_ENTRY = "delete_journal_entry"
SERVICE_GET_JOURNAL_ENTRIES = "get_journal_entries"

ATTR_DEVICE_ID = "device_id"
ATTR_ENTRY_ID = "entry_id"
ATTR_EVENT_TYPE = "event_type"
ATTR_METADATA = "metadata"
ATTR_NOTE = "note"
ATTR_TIMESTAMP = "timestamp"
ATTR_LIMIT = "limit"
ATTR_START_DATETIME = "start_datetime"
ATTR_END_DATETIME = "end_datetime"
ATTR_WEIGHT_VALUE = "weight_value"
ATTR_WEIGHT_UNIT = "weight_unit"

ADD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): str,
        vol.Required(ATTR_EVENT_TYPE): vol.In(
            [event_type.value for event_type in JournalEventType]
        ),
        vol.Optional(ATTR_NOTE): str,
        vol.Optional(ATTR_TIMESTAMP): vol.Any(str, datetime),
        vol.Optional(ATTR_METADATA): dict,
        vol.Optional(ATTR_WEIGHT_VALUE): vol.Any(str, int, float),
        vol.Optional(ATTR_WEIGHT_UNIT): str,
    }
)
DELETE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): str,
        vol.Required(ATTR_ENTRY_ID): str,
    }
)
GET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): str,
        vol.Optional(ATTR_LIMIT, default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1000)
        ),
        vol.Optional(ATTR_EVENT_TYPE): vol.In(
            [event_type.value for event_type in JournalEventType]
        ),
        vol.Optional(ATTR_START_DATETIME): vol.Any(str, datetime),
        vol.Optional(ATTR_END_DATETIME): vol.Any(str, datetime),
    }
)


def _runtime_for_device(hass: HomeAssistant, device_id: str) -> LizardCareData:
    """Resolve a selected Lizard Care device to its loaded runtime."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise HomeAssistantError("Lizard Care device was not found")
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is not None
            and entry.domain == DOMAIN
            and entry.state is ConfigEntryState.LOADED
        ):
            return entry.runtime_data
    raise HomeAssistantError("The selected Lizard Care pet is not loaded")


def _service_timestamp(value: object) -> datetime | None:
    """Parse an optional service timestamp as an aware datetime."""
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else dt_util.parse_datetime(value)
    if parsed is None or parsed.tzinfo is None:
        raise HomeAssistantError("Journal timestamp must include a timezone")
    return parsed


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration-level journal actions once."""
    if hass.services.has_service(DOMAIN, SERVICE_ADD_JOURNAL_ENTRY):
        return

    async def async_add_entry(call: ServiceCall) -> None:
        data = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        try:
            metadata = normalize_manual_metadata(
                call.data[ATTR_EVENT_TYPE],
                call.data.get(ATTR_METADATA),
                weight_value=call.data.get(ATTR_WEIGHT_VALUE),
                weight_unit=call.data.get(ATTR_WEIGHT_UNIT),
            )
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        await data.async_add_journal_entry(
            call.data[ATTR_EVENT_TYPE],
            timestamp=_service_timestamp(call.data.get(ATTR_TIMESTAMP)),
            note=call.data.get(ATTR_NOTE),
            metadata=metadata,
        )

    async def async_delete_entry(call: ServiceCall) -> None:
        data = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        await data.async_delete_journal_entry(call.data[ATTR_ENTRY_ID])

    async def async_get_entries(call: ServiceCall) -> dict[str, Any]:
        data = _runtime_for_device(hass, call.data[ATTR_DEVICE_ID])
        start = _service_timestamp(call.data.get(ATTR_START_DATETIME))
        end = _service_timestamp(call.data.get(ATTR_END_DATETIME))
        if start is not None and end is not None and start > end:
            raise HomeAssistantError(
                "Journal start datetime must not be after end datetime"
            )
        entries = data.journal.entries(
            event_type=call.data.get(ATTR_EVENT_TYPE),
            start_datetime=start,
            end_datetime=end,
            limit=call.data[ATTR_LIMIT],
        )
        return {"entries": [entry.as_storage() for entry in entries]}

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_JOURNAL_ENTRY,
        async_add_entry,
        schema=ADD_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_JOURNAL_ENTRY,
        async_delete_entry,
        schema=DELETE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_JOURNAL_ENTRIES,
        async_get_entries,
        schema=GET_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
