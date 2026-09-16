"""Shared care state for Lizard Care."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_CARE_COMPLETED,
    EVENT_JOURNAL_UPDATED,
    STATE_ALTERNATING_COMPLETED_OCCURRENCE,
    STATE_ALTERNATING_OCCURRENCE_OUTCOMES,
    STATE_ALTERNATING_SCHEDULE_DEFINITION,
    STATE_FOOD_IN_ENCLOSURE,
    STATE_LAST_FED,
    STATE_LAST_FOOD_REMOVED,
    STATE_LAST_FULL_CLEAN,
    STATE_LAST_SPOT_CLEAN,
    STORAGE_VERSION,
)
from .journal import JournalEntry, JournalEventType, JournalManager, JournalSource

if TYPE_CHECKING:
    from .schedule import CareSchedule


class CareStateStorage(TypedDict, total=False):
    """JSON-serializable persisted care state."""

    last_fed: str | None
    last_food_removed: str | None
    food_in_enclosure: bool
    last_spot_clean: str | None
    last_full_clean: str | None
    alternating_completed_occurrence: int
    alternating_occurrence_outcomes: dict[str, str]
    alternating_schedule_definition: str | None


class LizardCareData:
    """Manage persisted care state for one pet config entry."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize care state."""
        self.last_fed: datetime | None = None
        self.last_food_removed: datetime | None = None
        self.food_in_enclosure = False
        self.last_spot_clean: datetime | None = None
        self.last_full_clean: datetime | None = None
        self.alternating_completed_occurrence: int | None = None
        self.alternating_occurrence_outcomes: dict[int, str] = {}
        self.alternating_schedule_definition: str | None = None
        self._alternating_definition_was_loaded = False
        self._hass = hass
        self.entry_id = entry_id
        self._listeners: set[Callable[[], None]] = set()
        self._update_lock = asyncio.Lock()
        self._store = Store[CareStateStorage](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}"
        )
        self.journal = JournalManager(hass, entry_id)

    async def async_load(self) -> None:
        """Load this pet's persisted care state."""
        stored = await self._store.async_load()
        await self.journal.async_load()
        if stored is None:
            return

        self.last_fed = self._parse_stored_datetime(stored.get(STATE_LAST_FED))
        self.last_food_removed = self._parse_stored_datetime(
            stored.get(STATE_LAST_FOOD_REMOVED)
        )
        self.last_spot_clean = self._parse_stored_datetime(
            stored.get(STATE_LAST_SPOT_CLEAN)
        )
        self.last_full_clean = self._parse_stored_datetime(
            stored.get(STATE_LAST_FULL_CLEAN)
        )
        stored_occurrence = stored.get(STATE_ALTERNATING_COMPLETED_OCCURRENCE)
        if (
            isinstance(stored_occurrence, int)
            and not isinstance(stored_occurrence, bool)
            and stored_occurrence >= 0
        ):
            self.alternating_completed_occurrence = stored_occurrence
        stored_outcomes = stored.get(STATE_ALTERNATING_OCCURRENCE_OUTCOMES)
        if isinstance(stored_outcomes, dict):
            self.alternating_occurrence_outcomes = {
                int(number): outcome
                for number, outcome in stored_outcomes.items()
                if isinstance(number, str)
                and number.isdigit()
                and int(number) > 0
                and outcome in ("spot_clean", "full_clean", "skipped")
            }
        if STATE_ALTERNATING_SCHEDULE_DEFINITION in stored:
            stored_definition = stored.get(
                STATE_ALTERNATING_SCHEDULE_DEFINITION
            )
            if stored_definition is None or isinstance(stored_definition, str):
                self.alternating_schedule_definition = stored_definition
                self._alternating_definition_was_loaded = True

        stored_food_state = stored.get(STATE_FOOD_IN_ENCLOSURE)
        if isinstance(stored_food_state, bool):
            self.food_in_enclosure = stored_food_state

    async def async_feed(self) -> None:
        """Record a feeding and mark food as present."""
        async with self._update_lock:
            self.last_fed = dt_util.utcnow()
            self.food_in_enclosure = True
            await self._async_save()
            await self.journal.async_add_entry(
                JournalEventType.FEEDING,
                timestamp=self.last_fed,
                source=JournalSource.AUTOMATIC,
            )
            self._async_fire_journal_updated()
            self._async_notify_listeners()
            self._async_fire_care_completed("feeding", self.last_fed)

    async def async_remove_food(self) -> None:
        """Record food removal and mark food as removed."""
        async with self._update_lock:
            self.last_food_removed = dt_util.utcnow()
            self.food_in_enclosure = False
            await self._async_save()
            await self.journal.async_add_entry(
                JournalEventType.FOOD_REMOVED,
                timestamp=self.last_food_removed,
                source=JournalSource.AUTOMATIC,
            )
            self._async_fire_journal_updated()
            self._async_notify_listeners()
            self._async_fire_care_completed(
                "food_removal", self.last_food_removed
            )

    async def async_reconcile_alternating_definition(
        self, schedule: CareSchedule
    ) -> bool:
        """Reset progression when the effective schedule definition changes."""
        from .schedule import alternating_schedule_definition

        definition = alternating_schedule_definition(schedule)
        definition_changed = (
            not self._alternating_definition_was_loaded
            or self.alternating_schedule_definition != definition
        )
        if not definition_changed:
            return False
        self.alternating_completed_occurrence = None
        self.alternating_occurrence_outcomes.clear()
        self.alternating_schedule_definition = definition
        self._alternating_definition_was_loaded = True
        await self._async_save()
        return True

    async def async_spot_clean(self, schedule: CareSchedule | None = None) -> None:
        """Record a spot clean."""
        async with self._update_lock:
            self.last_spot_clean = dt_util.utcnow()
            self._advance_alternating_schedule(
                schedule, "spot_clean", self.last_spot_clean
            )
            await self._async_save()
            await self.journal.async_add_entry(
                JournalEventType.SPOT_CLEAN,
                timestamp=self.last_spot_clean,
                source=JournalSource.AUTOMATIC,
            )
            self._async_fire_journal_updated()
            self._async_notify_listeners()
            self._async_fire_care_completed(
                "spot_clean", self.last_spot_clean
            )

    async def async_full_clean(self, schedule: CareSchedule | None = None) -> None:
        """Record a full enclosure clean."""
        async with self._update_lock:
            self.last_full_clean = dt_util.utcnow()
            self._advance_alternating_schedule(
                schedule, "full_clean", self.last_full_clean
            )
            await self._async_save()
            await self.journal.async_add_entry(
                JournalEventType.FULL_CLEAN,
                timestamp=self.last_full_clean,
                source=JournalSource.AUTOMATIC,
            )
            self._async_fire_journal_updated()
            self._async_notify_listeners()
            self._async_fire_care_completed(
                "full_clean", self.last_full_clean
            )

    def _advance_alternating_schedule(
        self,
        schedule: CareSchedule | None,
        action_type: str,
        completed_at: datetime,
    ) -> None:
        """Advance only when the pressed action matches the active slot."""
        if schedule is None:
            return
        from .const import CLEANING_SCHEDULE_ALTERNATING
        from .schedule import (
            calculate_alternating_cleaning_plan,
            first_alternating_occurrence_after,
        )

        if schedule.cleaning_schedule_mode != CLEANING_SCHEDULE_ALTERNATING:
            return
        plan = calculate_alternating_cleaning_plan(
            schedule, self.alternating_completed_occurrence
        )
        if plan.cleaning_occurrence_type.value != action_type:
            return
        self._ensure_alternating_outcomes(schedule)
        self.alternating_occurrence_outcomes[plan.occurrence_number] = action_type
        first_future = first_alternating_occurrence_after(
            dt_util.as_local(completed_at).date(), schedule
        )
        for occurrence in range(plan.occurrence_number + 1, first_future):
            self.alternating_occurrence_outcomes.setdefault(
                occurrence, "skipped"
            )
        self._recalculate_alternating_progression()

    def _ensure_alternating_outcomes(self, schedule: CareSchedule) -> None:
        """Migrate the prior integer state into explicit outcomes once."""
        if self.alternating_occurrence_outcomes:
            return
        completed = self.alternating_completed_occurrence or 0
        if completed < 1:
            return
        from .schedule import (
            alternating_occurrence_date,
            alternating_occurrence_type,
        )

        for occurrence in range(1, completed + 1):
            self.alternating_occurrence_outcomes[occurrence] = "skipped"
        for action_type, timestamp in (
            ("spot_clean", self.last_spot_clean),
            ("full_clean", self.last_full_clean),
        ):
            if timestamp is None:
                continue
            completed_date = dt_util.as_local(timestamp).date()
            eligible = [
                occurrence
                for occurrence in range(1, completed + 1)
                if alternating_occurrence_type(
                    occurrence, schedule.alternating_anchor_type
                ).value
                == action_type
                and alternating_occurrence_date(
                    schedule.alternating_anchor_date,
                    occurrence,
                    schedule.alternating_interval_days,
                )
                <= completed_date
            ]
            for occurrence in eligible:
                self.alternating_occurrence_outcomes[occurrence] = action_type

    def _recalculate_alternating_progression(self) -> None:
        """Set progression to the highest contiguous explicit outcome."""
        occurrence = 1
        while occurrence in self.alternating_occurrence_outcomes:
            occurrence += 1
        self.alternating_completed_occurrence = occurrence - 1 or None

    def _reconcile_alternating_correction(
        self,
        schedule: CareSchedule | None,
        action_type: str,
        corrected_at: datetime,
    ) -> None:
        """Invalidate unsupported same-type outcomes without advancing."""
        if schedule is None:
            return
        from .const import CLEANING_SCHEDULE_ALTERNATING
        from .schedule import alternating_occurrence_date

        if schedule.cleaning_schedule_mode != CLEANING_SCHEDULE_ALTERNATING:
            return
        self._ensure_alternating_outcomes(schedule)
        corrected_date = dt_util.as_local(corrected_at).date()
        invalid = [
            occurrence
            for occurrence, outcome in self.alternating_occurrence_outcomes.items()
            if outcome == action_type
            and alternating_occurrence_date(
                schedule.alternating_anchor_date,
                occurrence,
                schedule.alternating_interval_days,
            )
            > corrected_date
        ]
        for occurrence in invalid:
            self.alternating_occurrence_outcomes.pop(occurrence)
        self._recalculate_alternating_progression()

    async def async_add_journal_entry(
        self,
        event_type: str,
        *,
        timestamp: datetime | None = None,
        note: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> JournalEntry:
        """Add a manual journal entry and refresh entities."""
        entry = await self.journal.async_add_entry(
            event_type,
            timestamp=timestamp,
            note=note,
            source=JournalSource.MANUAL,
            metadata=metadata,
        )
        self._async_fire_journal_updated()
        self._async_notify_listeners()
        return entry

    async def async_delete_journal_entry(self, entry_id: str) -> bool:
        """Delete one journal entry and refresh entities when changed."""
        deleted = await self.journal.async_delete_entry(entry_id)
        if deleted:
            self._async_fire_journal_updated()
            self._async_notify_listeners()
        return deleted

    @callback
    def _async_fire_journal_updated(self) -> None:
        """Publish a lightweight refresh signal without journal content."""
        self._hass.bus.async_fire(
            EVENT_JOURNAL_UPDATED,
            {"entry_id": self.entry_id},
        )

    @callback
    def _async_fire_care_completed(
        self, task: str, completed_at: datetime
    ) -> None:
        """Publish a minimal signal for successful real care actions."""
        self._hass.bus.async_fire(
            EVENT_CARE_COMPLETED,
            {
                "entry_id": self.entry_id,
                "task": task,
                "completed_at": completed_at.isoformat(),
            },
        )

    async def async_set_last_fed(self, value: datetime) -> None:
        """Correct the last-fed timestamp and reconcile enclosure state."""
        await self._async_set_timestamp("last_fed", value)

    async def async_set_last_food_removed(self, value: datetime) -> None:
        """Correct food-removal time and reconcile enclosure state."""
        await self._async_set_timestamp("last_food_removed", value)

    async def async_set_last_spot_clean(
        self, value: datetime, schedule: CareSchedule | None = None
    ) -> None:
        """Correct the last spot-clean timestamp."""
        await self._async_set_timestamp("last_spot_clean", value, schedule)

    async def async_set_last_full_clean(
        self, value: datetime, schedule: CareSchedule | None = None
    ) -> None:
        """Correct the last full-clean timestamp."""
        await self._async_set_timestamp("last_full_clean", value, schedule)

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Register a care-state listener."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _async_notify_listeners(self) -> None:
        """Notify entities that care state changed."""
        for listener in tuple(self._listeners):
            listener()

    @callback
    def reconcile_food_in_enclosure(self) -> bool:
        """Reconcile enclosure state from feeding and removal timestamps."""
        reconciled_state = self.last_fed is not None and (
            self.last_food_removed is None
            or self.last_fed > self.last_food_removed
        )
        if self.food_in_enclosure == reconciled_state:
            return False

        self.food_in_enclosure = reconciled_state
        return True

    @staticmethod
    def _parse_stored_datetime(value: object) -> datetime | None:
        """Parse a stored timezone-aware datetime as UTC."""
        if not isinstance(value, str):
            return None

        parsed = dt_util.parse_datetime(value)
        if parsed is None or parsed.tzinfo is None:
            return None
        return dt_util.as_utc(parsed)

    async def _async_set_timestamp(
        self,
        attribute: str,
        value: datetime,
        schedule: CareSchedule | None = None,
    ) -> None:
        """Correct one care timestamp and persist the changed state."""
        if value.tzinfo is None:
            raise ValueError("Care timestamps must be timezone-aware")

        value = dt_util.as_utc(value)
        async with self._update_lock:
            previous_outcomes = dict(self.alternating_occurrence_outcomes)
            if attribute in ("last_spot_clean", "last_full_clean"):
                self._reconcile_alternating_correction(
                    schedule,
                    "spot_clean"
                    if attribute == "last_spot_clean"
                    else "full_clean",
                    value,
                )
            timestamp_changed = getattr(self, attribute) != value
            if timestamp_changed:
                setattr(self, attribute, value)

            food_state_changed = False
            if attribute in ("last_fed", "last_food_removed"):
                food_state_changed = self.reconcile_food_in_enclosure()

            outcomes_changed = (
                previous_outcomes != self.alternating_occurrence_outcomes
            )
            if not timestamp_changed and not food_state_changed and not outcomes_changed:
                return
            await self._async_save()
            self._async_notify_listeners()

    async def _async_save(self) -> None:
        """Persist current care state."""
        await self._store.async_save(
            {
                STATE_LAST_FED: (
                    self.last_fed.isoformat() if self.last_fed is not None else None
                ),
                STATE_LAST_FOOD_REMOVED: (
                    self.last_food_removed.isoformat()
                    if self.last_food_removed is not None
                    else None
                ),
                STATE_FOOD_IN_ENCLOSURE: self.food_in_enclosure,
                STATE_LAST_SPOT_CLEAN: (
                    self.last_spot_clean.isoformat()
                    if self.last_spot_clean is not None
                    else None
                ),
                STATE_LAST_FULL_CLEAN: (
                    self.last_full_clean.isoformat()
                    if self.last_full_clean is not None
                    else None
                ),
                STATE_ALTERNATING_COMPLETED_OCCURRENCE: (
                    self.alternating_completed_occurrence
                ),
                STATE_ALTERNATING_OCCURRENCE_OUTCOMES: {
                    str(number): outcome
                    for number, outcome in (
                        self.alternating_occurrence_outcomes.items()
                    )
                },
                STATE_ALTERNATING_SCHEDULE_DEFINITION: (
                    self.alternating_schedule_definition
                ),
            }
        )
