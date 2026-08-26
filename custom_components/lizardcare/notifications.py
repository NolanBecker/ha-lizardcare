"""Notification scheduling for Lizard Care."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from functools import partial
import logging
from typing import TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLEANING_REMINDER_TIME,
    CONF_FEEDING_OVERDUE_REPEAT_HOURS,
    CONF_FEEDING_REMINDERS,
    CONF_FEEDING_REMINDER_TIME,
    CONF_FOOD_REMOVAL_DELAY_HOURS,
    CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
    CONF_FOOD_REMOVAL_REMINDER,
    CONF_FOOD_REMOVAL_REMINDER_BASIS,
    CONF_FULL_CLEAN_REMINDERS,
    CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
    CONF_NOTIFICATION_RECIPIENTS,
    CONF_REMINDER_TIME,
    CONF_SPOT_CLEAN_REMINDERS,
    CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
    DEFAULT_CLEANING_REMINDER_TIME,
    DEFAULT_FEEDING_OVERDUE_REPEAT_HOURS,
    DEFAULT_FEEDING_REMINDERS,
    DEFAULT_FEEDING_REMINDER_TIME,
    DEFAULT_FOOD_REMOVAL_DELAY_HOURS,
    DEFAULT_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
    DEFAULT_FOOD_REMOVAL_REMINDER,
    DEFAULT_FOOD_REMOVAL_REMINDER_BASIS,
    DEFAULT_FULL_CLEAN_REMINDERS,
    DEFAULT_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
    DEFAULT_SPOT_CLEAN_REMINDERS,
    DEFAULT_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
    DOMAIN,
    FOOD_REMOVAL_BASIS_ACTUAL,
    FOOD_REMOVAL_BASIS_SCHEDULED,
)
from .coordinator import LizardCareData
from .food_removal import calculate_food_removal_timing
from .profile import get_pet_profile
from .schedule import (
    CareStatus,
    calculate_care_status,
    calculate_effective_last_spot_clean,
    calculate_next_due,
    get_care_schedule,
)

_LOGGER = logging.getLogger(__name__)

NOTIFICATION_STORAGE_VERSION = 1


class NotificationStateStorage(TypedDict, total=False):
    """Persistent notification deduplication state."""

    daily_reminders: dict[str, str]
    food_removal_feeding: str | None
    food_removal_initial_sent_at: str | None
    food_removal_last_sent_at: str | None
    last_overdue_sent: dict[str, str]


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    """Resolved notification settings for one pet."""

    recipients: tuple[str, ...]
    feeding_reminders: bool
    spot_clean_reminders: bool
    full_clean_reminders: bool
    food_removal_reminder: bool
    feeding_reminder_time: time
    cleaning_reminder_time: time
    food_removal_delay_hours: int
    food_removal_reminder_basis: str
    food_removal_overdue_repeat_hours: int
    feeding_overdue_repeat_hours: int
    spot_clean_overdue_repeat_hours: int
    full_clean_overdue_repeat_hours: int


def _boolean_option(entry: ConfigEntry, key: str, default: bool) -> bool:
    """Return a boolean option or its default."""
    value = entry.options.get(key, default)
    return value if isinstance(value, bool) else default


def _time_option(entry: ConfigEntry, key: str, default: str) -> time:
    """Return a configured time, falling back through the legacy option."""
    value = entry.options.get(key, entry.options.get(CONF_REMINDER_TIME, default))
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(value)
    except (TypeError, ValueError):
        return time.fromisoformat(default)


def _nonnegative_int_option(entry: ConfigEntry, key: str, default: int) -> int:
    """Return a nonnegative integer option or its default."""
    value = entry.options.get(key, default)
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    ):
        return value
    return default


def get_notification_settings(entry: ConfigEntry) -> NotificationSettings:
    """Resolve notification options with backward-compatible defaults."""
    recipients_value = entry.options.get(CONF_NOTIFICATION_RECIPIENTS, [])
    recipients = (
        tuple(value for value in recipients_value if isinstance(value, str))
        if isinstance(recipients_value, list)
        else ()
    )

    delay_value = entry.options.get(
        CONF_FOOD_REMOVAL_DELAY_HOURS, DEFAULT_FOOD_REMOVAL_DELAY_HOURS
    )
    delay_hours = (
        delay_value
        if isinstance(delay_value, int)
        and not isinstance(delay_value, bool)
        and delay_value > 0
        else DEFAULT_FOOD_REMOVAL_DELAY_HOURS
    )
    basis_value = entry.options.get(
        CONF_FOOD_REMOVAL_REMINDER_BASIS,
        DEFAULT_FOOD_REMOVAL_REMINDER_BASIS,
    )
    basis = (
        basis_value
        if basis_value
        in (FOOD_REMOVAL_BASIS_ACTUAL, FOOD_REMOVAL_BASIS_SCHEDULED)
        else DEFAULT_FOOD_REMOVAL_REMINDER_BASIS
    )

    return NotificationSettings(
        recipients=recipients,
        feeding_reminders=_boolean_option(
            entry, CONF_FEEDING_REMINDERS, DEFAULT_FEEDING_REMINDERS
        ),
        spot_clean_reminders=_boolean_option(
            entry, CONF_SPOT_CLEAN_REMINDERS, DEFAULT_SPOT_CLEAN_REMINDERS
        ),
        full_clean_reminders=_boolean_option(
            entry, CONF_FULL_CLEAN_REMINDERS, DEFAULT_FULL_CLEAN_REMINDERS
        ),
        food_removal_reminder=_boolean_option(
            entry, CONF_FOOD_REMOVAL_REMINDER, DEFAULT_FOOD_REMOVAL_REMINDER
        ),
        feeding_reminder_time=_time_option(
            entry, CONF_FEEDING_REMINDER_TIME, DEFAULT_FEEDING_REMINDER_TIME
        ),
        cleaning_reminder_time=_time_option(
            entry, CONF_CLEANING_REMINDER_TIME, DEFAULT_CLEANING_REMINDER_TIME
        ),
        food_removal_delay_hours=delay_hours,
        food_removal_reminder_basis=basis,
        food_removal_overdue_repeat_hours=_nonnegative_int_option(
            entry,
            CONF_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
            DEFAULT_FOOD_REMOVAL_OVERDUE_REPEAT_HOURS,
        ),
        feeding_overdue_repeat_hours=_nonnegative_int_option(
            entry,
            CONF_FEEDING_OVERDUE_REPEAT_HOURS,
            DEFAULT_FEEDING_OVERDUE_REPEAT_HOURS,
        ),
        spot_clean_overdue_repeat_hours=_nonnegative_int_option(
            entry,
            CONF_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
            DEFAULT_SPOT_CLEAN_OVERDUE_REPEAT_HOURS,
        ),
        full_clean_overdue_repeat_hours=_nonnegative_int_option(
            entry,
            CONF_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
            DEFAULT_FULL_CLEAN_OVERDUE_REPEAT_HOURS,
        ),
    )


def calculate_next_overdue_repeat(
    last_sent: datetime, interval_hours: int, now: datetime
) -> datetime | None:
    """Return the next future cadence point for an overdue reminder."""
    if interval_hours <= 0:
        return None
    last_sent = dt_util.as_utc(last_sent)
    now = dt_util.as_utc(now)
    interval = timedelta(hours=interval_hours)
    next_repeat = last_sent + interval
    if next_repeat <= now:
        elapsed_intervals = (now - last_sent) // interval
        next_repeat = last_sent + interval * (elapsed_intervals + 1)
    return next_repeat


def calculate_food_removal_reminder(
    last_fed: datetime,
    settings: NotificationSettings,
    now: datetime,
) -> datetime | None:
    """Calculate a timezone-aware food-removal reminder timestamp."""
    return calculate_food_removal_timing(
        last_fed,
        delay_hours=settings.food_removal_delay_hours,
        basis=settings.food_removal_reminder_basis,
        feeding_reminder_time=settings.feeding_reminder_time,
        now=now,
    ).notification_at


def calculate_stale_food_removal_anchor(
    last_fed: datetime,
    settings: NotificationSettings,
    now: datetime,
) -> datetime:
    """Return the effective due time for a stale removal reminder."""
    return calculate_food_removal_timing(
        last_fed,
        delay_hours=settings.food_removal_delay_hours,
        basis=settings.food_removal_reminder_basis,
        feeding_reminder_time=settings.feeding_reminder_time,
        now=now,
    ).reminder_at


class LizardCareNotificationManager:
    """Schedule, send, and deduplicate notifications for one pet."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        care_data: LizardCareData,
    ) -> None:
        """Initialize the notification manager."""
        self._hass = hass
        self._entry = entry
        self._care_data = care_data
        self._daily_reminders: dict[str, str] = {}
        self._food_removal_feeding: str | None = None
        self._food_removal_initial_sent_at: datetime | None = None
        self._food_removal_last_sent_at: datetime | None = None
        self._last_overdue_sent: dict[str, datetime] = {}
        self._feeding_daily_unsub: CALLBACK_TYPE | None = None
        self._cleaning_daily_unsub: CALLBACK_TYPE | None = None
        self._food_unsub: CALLBACK_TYPE | None = None
        self._care_unsub: CALLBACK_TYPE | None = None
        self._food_task: asyncio.Task[None] | None = None
        self._repeat_unsubs: dict[str, CALLBACK_TYPE] = {}
        self._store = Store[NotificationStateStorage](
            hass,
            NOTIFICATION_STORAGE_VERSION,
            f"{DOMAIN}.notifications.{entry.entry_id}",
        )

    async def async_setup(self) -> None:
        """Load deduplication state and schedule notification checks."""
        if stored := await self._store.async_load():
            daily = stored.get("daily_reminders")
            if isinstance(daily, dict):
                self._daily_reminders = {
                    key: value
                    for key, value in daily.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            food_feeding = stored.get("food_removal_feeding")
            if isinstance(food_feeding, str):
                self._food_removal_feeding = food_feeding
            self._food_removal_initial_sent_at = self._stored_datetime(
                stored.get("food_removal_initial_sent_at")
            )
            self._food_removal_last_sent_at = self._stored_datetime(
                stored.get("food_removal_last_sent_at")
            )
            overdue_sent = stored.get("last_overdue_sent")
            if isinstance(overdue_sent, dict):
                for key, value in overdue_sent.items():
                    if not isinstance(key, str) or not isinstance(value, str):
                        continue
                    try:
                        parsed = datetime.fromisoformat(value)
                    except ValueError:
                        continue
                    if parsed.tzinfo is not None:
                        self._last_overdue_sent[key] = dt_util.as_utc(parsed)

        self._care_unsub = self._care_data.async_add_listener(
            self._async_care_state_changed
        )
        self._schedule_daily_reminders()
        self._schedule_food_removal()
        self._schedule_all_overdue_repeats()

        settings = get_notification_settings(self._entry)
        local_now = dt_util.now()
        if local_now.time() >= settings.feeding_reminder_time:
            self._hass.async_create_task(
                self._async_feeding_reminder(local_now),
                f"{DOMAIN} feeding reminder catch-up",
            )
        if local_now.time() >= settings.cleaning_reminder_time:
            self._hass.async_create_task(
                self._async_cleaning_reminders(local_now),
                f"{DOMAIN} cleaning reminder catch-up",
            )

    @callback
    def async_shutdown(self) -> None:
        """Cancel notification listeners and scheduled callbacks."""
        for unsubscribe in (
            self._feeding_daily_unsub,
            self._cleaning_daily_unsub,
            self._food_unsub,
            self._care_unsub,
        ):
            if unsubscribe is not None:
                unsubscribe()
        self._feeding_daily_unsub = None
        self._cleaning_daily_unsub = None
        self._food_unsub = self._care_unsub = None
        for unsubscribe in self._repeat_unsubs.values():
            unsubscribe()
        self._repeat_unsubs.clear()
        if self._food_task is not None:
            self._food_task.cancel()
            self._food_task = None

    @callback
    def _async_care_state_changed(self) -> None:
        """Reschedule notifications when care state changes."""
        self._schedule_food_removal()
        self._schedule_all_overdue_repeats()

    def _reminder_values(
        self, key: str
    ) -> tuple[bool, datetime | None, int, int]:
        """Return enabled, last event, care days, and repeat hours."""
        settings = get_notification_settings(self._entry)
        schedule = get_care_schedule(self._entry)
        if key == "feeding":
            return (
                settings.feeding_reminders,
                self._care_data.last_fed,
                schedule.feeding_interval_days,
                settings.feeding_overdue_repeat_hours,
            )
        if key == "spot_clean":
            return (
                settings.spot_clean_reminders,
                calculate_effective_last_spot_clean(
                    self._care_data.last_spot_clean,
                    self._care_data.last_full_clean,
                    full_clean_satisfies_spot_clean=(
                        schedule.full_clean_satisfies_spot_clean
                    ),
                ),
                schedule.spot_clean_interval_days,
                settings.spot_clean_overdue_repeat_hours,
            )
        return (
            settings.full_clean_reminders,
            self._care_data.last_full_clean,
            schedule.full_clean_interval_days,
            settings.full_clean_overdue_repeat_hours,
        )

    def _is_overdue(self, last_done: datetime | None, interval: int) -> bool:
        """Return whether a care task is overdue in local time."""
        return calculate_care_status(
            calculate_next_due(last_done, interval), dt_util.now().date()
        ) is CareStatus.OVERDUE

    @staticmethod
    def _stored_datetime(value: object) -> datetime | None:
        """Parse a persisted timezone-aware notification timestamp."""
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return dt_util.as_utc(parsed)

    @callback
    def _schedule_all_overdue_repeats(self) -> None:
        """Reconcile repeat callbacks with current care state and settings."""
        changed = False
        for key in ("feeding", "spot_clean", "full_clean"):
            changed |= self._schedule_overdue_repeat(key)
        if changed:
            self._hass.async_create_task(
                self._async_save(), f"{DOMAIN} reminder metadata save"
            )

    @callback
    def _schedule_overdue_repeat(self, key: str) -> bool:
        """Schedule one repeat cycle, returning whether metadata changed."""
        if unsubscribe := self._repeat_unsubs.pop(key, None):
            unsubscribe()

        settings = get_notification_settings(self._entry)
        enabled, last_done, interval_days, repeat_hours = self._reminder_values(
            key
        )
        last_sent = self._last_overdue_sent.get(key)
        if (
            not settings.recipients
            or not enabled
            or repeat_hours == 0
            or not self._is_overdue(last_done, interval_days)
        ):
            if last_sent is not None and not self._is_overdue(
                last_done, interval_days
            ):
                del self._last_overdue_sent[key]
                return True
            return False
        if last_sent is None:
            return False

        due = calculate_next_overdue_repeat(
            last_sent, repeat_hours, dt_util.utcnow()
        )
        if due is not None:
            self._repeat_unsubs[key] = async_track_point_in_utc_time(
                self._hass,
                partial(self._async_overdue_repeat, key),
                due,
            )
        return False

    @callback
    def _schedule_daily_reminders(self) -> None:
        """Schedule the daily local-time reminder evaluation."""
        if self._feeding_daily_unsub is not None:
            self._feeding_daily_unsub()
        if self._cleaning_daily_unsub is not None:
            self._cleaning_daily_unsub()
        settings = get_notification_settings(self._entry)
        feeding_time = settings.feeding_reminder_time
        cleaning_time = settings.cleaning_reminder_time
        self._feeding_daily_unsub = async_track_time_change(
            self._hass,
            self._async_feeding_reminder,
            hour=feeding_time.hour,
            minute=feeding_time.minute,
            second=feeding_time.second,
        )
        self._cleaning_daily_unsub = async_track_time_change(
            self._hass,
            self._async_cleaning_reminders,
            hour=cleaning_time.hour,
            minute=cleaning_time.minute,
            second=cleaning_time.second,
        )

    @callback
    def _schedule_food_removal(self) -> None:
        """Schedule the initial or repeating reminder for the current feed."""
        if self._food_unsub is not None:
            self._food_unsub()
            self._food_unsub = None
        if self._food_task is not None:
            self._food_task.cancel()
            self._food_task = None

        settings = get_notification_settings(self._entry)
        last_fed = self._care_data.last_fed
        if (
            not settings.recipients
            or not settings.food_removal_reminder
            or not self._care_data.food_in_enclosure
            or last_fed is None
        ):
            return

        now = dt_util.utcnow()
        feeding_event = last_fed.isoformat()
        if self._food_removal_feeding == feeding_event:
            repeat_hours = settings.food_removal_overdue_repeat_hours
            if repeat_hours == 0:
                return
            last_sent = (
                self._food_removal_last_sent_at
                or self._food_removal_initial_sent_at
            )
            # Older installations tracked the feeding event but not send times.
            # Start their first repeat one full interval after this setup pass.
            due = (
                now + timedelta(hours=repeat_hours)
                if last_sent is None
                else calculate_next_overdue_repeat(
                    last_sent, repeat_hours, now
                )
            )
            if due is not None:
                self._food_unsub = async_track_point_in_utc_time(
                    self._hass,
                    partial(
                        self._async_food_removal_repeat,
                        feeding_event,
                    ),
                    due,
                )
            return

        due = calculate_food_removal_reminder(last_fed, settings, now)
        if due is None:
            repeat_hours = settings.food_removal_overdue_repeat_hours
            if repeat_hours == 0:
                return
            due = calculate_next_overdue_repeat(
                calculate_stale_food_removal_anchor(
                    last_fed, settings, now
                ),
                repeat_hours,
                now,
            )
            if due is None:
                return
        if due <= now:
            self._food_task = self._hass.async_create_task(
                self._async_food_removal_reminder(feeding_event, due),
                f"{DOMAIN} food removal reminder",
            )
        else:
            self._food_unsub = async_track_point_in_utc_time(
                self._hass,
                partial(self._async_food_removal_reminder, feeding_event),
                due,
            )

    async def _async_feeding_reminder(self, now: datetime) -> None:
        """Evaluate the daily feeding reminder."""
        await self._async_daily_reminders(now, include_feeding=True)

    async def _async_cleaning_reminders(self, now: datetime) -> None:
        """Evaluate the daily cleaning reminders."""
        await self._async_daily_reminders(now, include_feeding=False)

    async def _async_daily_reminders(
        self, now: datetime, *, include_feeding: bool
    ) -> None:
        """Send the selected due or overdue reminders for the local day."""
        settings = get_notification_settings(self._entry)
        if not settings.recipients:
            return

        profile = get_pet_profile(self._entry)
        schedule = get_care_schedule(self._entry)
        local_date = dt_util.as_local(now).date()
        reminders = (
            (
                "feeding",
                settings.feeding_reminders,
                self._care_data.last_fed,
                schedule.feeding_interval_days,
                f"{profile.pet_name} needs fed today",
                f"{profile.pet_name}'s feeding is overdue",
                "fed",
            ),
            (
                "spot_clean",
                settings.spot_clean_reminders,
                calculate_effective_last_spot_clean(
                    self._care_data.last_spot_clean,
                    self._care_data.last_full_clean,
                    full_clean_satisfies_spot_clean=(
                        schedule.full_clean_satisfies_spot_clean
                    ),
                ),
                schedule.spot_clean_interval_days,
                f"{profile.pet_name} is due for a spot clean",
                f"{profile.pet_name}'s spot clean is overdue",
                "spot cleaned",
            ),
            (
                "full_clean",
                settings.full_clean_reminders,
                self._care_data.last_full_clean,
                schedule.full_clean_interval_days,
                f"{profile.pet_name} is due for a full clean",
                f"{profile.pet_name}'s full clean is overdue",
                "fully cleaned",
            ),
        )
        reminders = reminders[:1] if include_feeding else reminders[1:]

        changed = False
        date_key = local_date.isoformat()
        for (
            key,
            enabled,
            last_done,
            interval,
            due_title,
            overdue_title,
            verb,
        ) in reminders:
            if not enabled or self._daily_reminders.get(key) == date_key:
                continue
            status = calculate_care_status(
                calculate_next_due(last_done, interval), local_date
            )
            if status not in (CareStatus.DUE_TODAY, CareStatus.OVERDUE):
                continue

            last_overdue_sent = self._last_overdue_sent.get(key)
            if (
                status is CareStatus.OVERDUE
                and last_overdue_sent is not None
                and abs(
                    (dt_util.utcnow() - last_overdue_sent).total_seconds()
                ) < 1
            ):
                self._daily_reminders[key] = date_key
                changed = True
                continue

            title = due_title if status is CareStatus.DUE_TODAY else overdue_title
            message = (
                f"{profile.pet_name} was last {verb} on "
                f"{self._friendly_datetime(last_done)}."
            )
            if await self._async_send(settings.recipients, title, message):
                self._daily_reminders[key] = date_key
                if status is CareStatus.OVERDUE:
                    self._last_overdue_sent[key] = dt_util.utcnow()
                    self._schedule_overdue_repeat(key)
                changed = True

        if changed:
            await self._async_save()

    async def _async_overdue_repeat(self, key: str, _now: datetime) -> None:
        """Send one overdue repeat if the cycle remains eligible."""
        self._repeat_unsubs.pop(key, None)
        settings = get_notification_settings(self._entry)
        enabled, last_done, interval_days, repeat_hours = self._reminder_values(
            key
        )
        if (
            not settings.recipients
            or not enabled
            or repeat_hours == 0
            or not self._is_overdue(last_done, interval_days)
        ):
            self._schedule_all_overdue_repeats()
            return

        last_sent = self._last_overdue_sent.get(key)
        actual_now = dt_util.utcnow()
        if last_sent is None:
            return
        allowed_at = last_sent + timedelta(hours=repeat_hours)
        if allowed_at > actual_now:
            self._schedule_overdue_repeat(key)
            return

        profile = get_pet_profile(self._entry)
        details = {
            "feeding": (
                f"{profile.pet_name}'s feeding is overdue",
                "fed",
            ),
            "spot_clean": (
                f"{profile.pet_name}'s spot clean is overdue",
                "spot cleaned",
            ),
            "full_clean": (
                f"{profile.pet_name}'s full clean is overdue",
                "fully cleaned",
            ),
        }
        title, verb = details[key]
        message = (
            f"{profile.pet_name} was last {verb} on "
            f"{self._friendly_datetime(last_done)}."
        )
        if await self._async_send(settings.recipients, title, message):
            self._last_overdue_sent[key] = dt_util.utcnow()
            await self._async_save()
        self._schedule_overdue_repeat(key)

    async def _async_food_removal_reminder(
        self, feeding_event: str, _now: datetime
    ) -> None:
        """Send one reminder for the current feeding if food remains present."""
        self._food_unsub = None
        self._food_task = None
        settings = get_notification_settings(self._entry)
        last_fed = self._care_data.last_fed
        if (
            not settings.recipients
            or not settings.food_removal_reminder
            or not self._care_data.food_in_enclosure
            or last_fed is None
            or last_fed.isoformat() != feeding_event
            or self._food_removal_feeding == last_fed.isoformat()
        ):
            return

        profile = get_pet_profile(self._entry)
        title = f"{profile.pet_name}'s food is still in the enclosure"
        message = (
            f"{profile.pet_name} was fed on {self._friendly_datetime(last_fed)}. "
            "Remember to remove the food when appropriate."
        )
        if await self._async_send(settings.recipients, title, message):
            sent_at = dt_util.utcnow()
            self._food_removal_feeding = last_fed.isoformat()
            self._food_removal_initial_sent_at = sent_at
            self._food_removal_last_sent_at = sent_at
            await self._async_save()
            self._schedule_food_removal()

    async def _async_food_removal_repeat(
        self, feeding_event: str, _now: datetime
    ) -> None:
        """Repeat a removal reminder while the same feeding remains present."""
        self._food_unsub = None
        settings = get_notification_settings(self._entry)
        last_fed = self._care_data.last_fed
        if (
            not settings.recipients
            or not settings.food_removal_reminder
            or settings.food_removal_overdue_repeat_hours == 0
            or not self._care_data.food_in_enclosure
            or last_fed is None
            or last_fed.isoformat() != feeding_event
            or self._food_removal_feeding != last_fed.isoformat()
        ):
            return

        last_sent = (
            self._food_removal_last_sent_at
            or self._food_removal_initial_sent_at
        )
        actual_now = dt_util.utcnow()
        if last_sent is not None and (
            last_sent
            + timedelta(hours=settings.food_removal_overdue_repeat_hours)
            > actual_now
        ):
            self._schedule_food_removal()
            return

        profile = get_pet_profile(self._entry)
        title = f"{profile.pet_name}'s food is still in the enclosure"
        message = (
            f"{profile.pet_name} was fed on {self._friendly_datetime(last_fed)}. "
            "Remember to remove the food when appropriate."
        )
        if await self._async_send(settings.recipients, title, message):
            self._food_removal_last_sent_at = dt_util.utcnow()
            await self._async_save()
        self._schedule_food_removal()

    async def _async_send(
        self, recipients: tuple[str, ...], title: str, message: str
    ) -> bool:
        """Send to each notify entity, isolating unavailable recipients."""
        sent = False
        for recipient in recipients:
            try:
                await self._hass.services.async_call(
                    "notify",
                    "send_message",
                    {"title": title, "message": message},
                    target={"entity_id": recipient},
                    blocking=True,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Failed to notify %s for %s", recipient, self._entry.title
                )
            else:
                sent = True
        return sent

    @staticmethod
    def _friendly_datetime(value: datetime | None) -> str:
        """Format a care timestamp in Home Assistant's local timezone."""
        if value is None:
            return "an unknown time"
        return dt_util.as_local(value).strftime("%Y-%m-%d at %H:%M")

    async def _async_save(self) -> None:
        """Persist notification deduplication state."""
        await self._store.async_save(
            {
                "daily_reminders": self._daily_reminders,
                "food_removal_feeding": self._food_removal_feeding,
                "food_removal_initial_sent_at": (
                    self._food_removal_initial_sent_at.isoformat()
                    if self._food_removal_initial_sent_at is not None
                    else None
                ),
                "food_removal_last_sent_at": (
                    self._food_removal_last_sent_at.isoformat()
                    if self._food_removal_last_sent_at is not None
                    else None
                ),
                "last_overdue_sent": {
                    key: value.isoformat()
                    for key, value in self._last_overdue_sent.items()
                },
            }
        )
