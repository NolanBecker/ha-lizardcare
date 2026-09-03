"""Regression checks for removal of integration-owned notifications."""

from pathlib import Path

INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "lizardcare"
)


def test_integration_does_not_call_notify_services() -> None:
    """Notification delivery belongs exclusively to Home Assistant automations."""
    source = "\n".join(
        path.read_text() for path in INTEGRATION_DIR.glob("*.py")
    )
    assert 'async_call("notify"' not in source
    assert "LizardCareNotificationManager" not in source
    assert not (INTEGRATION_DIR / "notifications.py").exists()
