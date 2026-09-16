"""Contract tests for the journal WebSocket API and history card."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.lizardcare.journal import JournalEventType, JournalManager

ROOT = Path(__file__).parents[1]
CARD_PATH = (
    ROOT
    / "custom_components/lizardcare/www/lizard-care-history-card.js"
)


class FakeStore:
    """Minimal journal storage for API response tests."""

    stored = None

    async def async_load(self):
        """Return stored state."""
        return self.stored

    async def async_save(self, data):
        """Save state."""
        self.stored = data


def test_websocket_response_returns_recent_requested_limit() -> None:
    """The frontend API returns newest entries using the requested bound."""
    manager = JournalManager(None, "pet-one", store=FakeStore())  # type: ignore[arg-type]
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)

    async def populate() -> None:
        for day in range(4):
            await manager.async_add_entry(
                JournalEventType.NOTE,
                timestamp=base + timedelta(days=day),
            )

    asyncio.run(populate())
    response = {
        "entry_id": "pet-one",
        "entries": [entry.as_storage() for entry in manager.entries(limit=2)],
    }

    assert response["entry_id"] == "pet-one"
    assert len(response["entries"]) == 2
    assert response["entries"][0]["timestamp"].startswith("2026-09-04")


def test_websocket_contract_enforces_entity_permission_and_safe_errors() -> None:
    """Unauthorized, malformed, and missing requests have explicit guards."""
    source = (
        ROOT / "custom_components/lizardcare/websocket_api.py"
    ).read_text()

    assert 'vol.Required("entity_id"): str' in source
    assert "vol.Range(min=1, max=1000)" in source
    assert "permissions.check_entity(entity_id, POLICY_READ)" in source
    assert "websocket_api.ERR_NOT_ALLOWED" in source
    assert "websocket_api.ERR_NOT_FOUND" in source


def test_websocket_create_reuses_authorized_entity_and_runtime_contract() -> None:
    """Manual writes resolve the pet entity and reuse journal validation."""
    source = (
        ROOT / "custom_components/lizardcare/websocket_api.py"
    ).read_text()

    assert 'WS_TYPE_CREATE_JOURNAL = f"{DOMAIN}/journal/create"' in source
    assert source.count("permissions.check_entity(entity_id, POLICY_READ)") == 2
    assert "_journal_runtime_for_entity(hass, entity_id)" in source
    assert "normalize_manual_metadata(" in source
    assert "runtime.async_add_journal_entry(" in source
    assert 'vol.Length(max=2000)' in source
    assert '"invalid_format"' in source
    assert "websocket_create_journal" in source


def test_card_retrieves_and_subscribes_without_polling() -> None:
    """The card loads over WebSocket and refreshes from journal events."""
    source = CARD_PATH.read_text()

    assert 'type: "lizardcare/journal/get"' in source
    assert 'const EVENT_TYPE = "lizardcare_journal_updated"' in source
    assert "subscribeEvents" in source
    assert "event.data?.entry_id === this._entryId" in source
    assert "setInterval" not in source
    assert "setTimeout" not in source


def test_card_has_recent_history_presentation_states() -> None:
    """Friendly labels, state feedback, grouping, and Weight data are present."""
    source = CARD_PATH.read_text()

    for label in (
        "Feeding",
        "Food Removed",
        "Spot Clean",
        "Full Clean",
        "Note",
        "Shed",
        "Weight",
        "Enclosure",
        "Health",
        "Other",
    ):
        assert label in source
    assert "Loading care history" in source
    assert "No care history yet" in source
    assert "Unable to load care history" in source
    assert "entry.metadata?.value" in source
    assert 'return "Today"' in source
    assert 'return "Yesterday"' in source
    assert "config?.time_zone" in source


def test_card_supports_recent_and_full_history_configuration() -> None:
    """Limit and View All configuration support main and popup use."""
    source = CARD_PATH.read_text()

    assert "limit: 5" in source
    assert "show_view_all: true" in source
    assert 'view_all_hash: "#pixel-history"' in source
    assert 'window.location.hash = this._config.view_all_hash' in source
    assert 'customElements.define("lizard-care-history-card"' in source


def test_card_add_entry_form_and_submission_contract() -> None:
    """The shared card offers a guarded mobile journal-entry workflow."""
    source = CARD_PATH.read_text()

    assert "show_add: true" in source
    assert 'type: "lizardcare/journal/create"' in source
    assert 'entity_id: this._config.entity' in source
    assert "if (this._submitting) return" in source
    assert "new Date(timestamp).toISOString()" in source
    assert "Weight Value" in source
    assert '<option value="g"' in source
    assert '<option value="oz"' in source
    assert "Journal entries do not change care schedules" in source
    assert "await this._loadEntries()" in source
    assert "Unable to save this journal entry" in source
