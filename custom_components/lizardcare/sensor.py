"""Sensor platform for Lizard Care."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from . import LizardCareConfigEntry
from .const import CLEANING_SCHEDULE_MONTHLY
from .coordinator import LizardCareData
from .derived import (
    CareActivity,
    DueDayCounts,
    LastCareActivity,
    calculate_due_day_counts,
    find_last_care_activity,
    format_past_relative_time,
    format_scheduled_relative_time,
)
from .entity import LizardCareEntity
from .food_removal import (
    FoodRemovalResult,
    FoodRemovalStatus,
    calculate_food_removal_status,
    get_food_removal_settings,
)
from .instructions import CareInstructions, get_care_instructions
from .profile import get_birth_date, get_pet_profile
from .schedule import (
    CareStatus,
    MonthlyCleaningPlan,
    OverallCareResult,
    OverallCareStatus,
    calculate_care_status,
    calculate_effective_last_spot_clean,
    calculate_monthly_cleaning_plan,
    calculate_next_due,
    calculate_overall_care_status,
    get_care_schedule,
)

TIMESTAMP_DESCRIPTIONS = (
    SensorEntityDescription(
        key="last_fed",
        translation_key="last_fed",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_spot_clean",
        translation_key="last_spot_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_full_clean",
        translation_key="last_full_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_food_removed",
        translation_key="last_food_removed",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

AGE_DESCRIPTION = SensorEntityDescription(
    key="age",
    translation_key="age",
)

PROFILE_DESCRIPTIONS = (
    SensorEntityDescription(
        key="species",
        translation_key="species",
        icon="mdi:lizard",
    ),
    SensorEntityDescription(
        key="birthday",
        translation_key="birthday",
        device_class=SensorDeviceClass.DATE,
    ),
    SensorEntityDescription(
        key="sex",
        translation_key="sex",
        icon="mdi:gender-male-female",
    ),
    SensorEntityDescription(
        key="notes",
        translation_key="notes",
        icon="mdi:note-text-outline",
    ),
)

MAX_SENSOR_STATE_LENGTH = 255

NEXT_DUE_DESCRIPTIONS = (
    SensorEntityDescription(
        key="next_feeding",
        translation_key="next_feeding",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="next_spot_clean",
        translation_key="next_spot_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="next_full_clean",
        translation_key="next_full_clean",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
)

STATUS_DESCRIPTIONS = (
    SensorEntityDescription(
        key="feeding_status",
        translation_key="feeding_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
    SensorEntityDescription(
        key="spot_clean_status",
        translation_key="spot_clean_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
    SensorEntityDescription(
        key="full_clean_status",
        translation_key="full_clean_status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in CareStatus],
    ),
)

CARE_STATUS_DESCRIPTION = SensorEntityDescription(
    key="care_status",
    translation_key="care_status",
    device_class=SensorDeviceClass.ENUM,
    options=[status.value for status in OverallCareStatus],
)

LAST_CARE_ACTIVITY_DESCRIPTION = SensorEntityDescription(
    key="last_care_activity",
    translation_key="last_care_activity",
    device_class=SensorDeviceClass.ENUM,
    options=[activity.value for activity in CareActivity],
)

FOOD_REMOVAL_STATUS_DESCRIPTION = SensorEntityDescription(
    key="food_removal_status",
    translation_key="food_removal_status",
    device_class=SensorDeviceClass.ENUM,
    options=[status.value for status in FoodRemovalStatus],
)


class LizardCareSensorTimeUpdater:
    """Share minute and local-midnight updates across sensor entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the time updater."""
        self._hass = hass
        self._minute_listeners: set[Callable[[], None]] = set()
        self._daily_listeners: set[Callable[[], None]] = set()
        self._minute_unsub: CALLBACK_TYPE | None = None
        self._daily_unsub: CALLBACK_TYPE | None = None

    @callback
    def async_add_minute_listener(
        self, listener: Callable[[], None]
    ) -> CALLBACK_TYPE:
        """Add a listener to the shared minute update."""
        self._minute_listeners.add(listener)
        if self._minute_unsub is None:
            self._minute_unsub = async_track_time_interval(
                self._hass,
                self._async_minute_changed,
                timedelta(minutes=1),
            )
        return lambda: self._remove_minute_listener(listener)

    @callback
    def async_add_daily_listener(
        self, listener: Callable[[], None]
    ) -> CALLBACK_TYPE:
        """Add a listener to the shared local-midnight update."""
        self._daily_listeners.add(listener)
        if self._daily_unsub is None:
            self._daily_unsub = async_track_time_change(
                self._hass,
                self._async_day_changed,
                hour=0,
                minute=0,
                second=0,
            )
        return lambda: self._remove_daily_listener(listener)

    @callback
    def _remove_minute_listener(self, listener: Callable[[], None]) -> None:
        """Remove a minute listener and stop the unused timer."""
        self._minute_listeners.discard(listener)
        if not self._minute_listeners and self._minute_unsub is not None:
            self._minute_unsub()
            self._minute_unsub = None

    @callback
    def _remove_daily_listener(self, listener: Callable[[], None]) -> None:
        """Remove a daily listener and stop the unused timer."""
        self._daily_listeners.discard(listener)
        if not self._daily_listeners and self._daily_unsub is not None:
            self._daily_unsub()
            self._daily_unsub = None

    @callback
    def _async_minute_changed(self, _now: datetime) -> None:
        """Notify entities with minute-level relative text."""
        for listener in tuple(self._minute_listeners):
            listener()

    @callback
    def _async_day_changed(self, _now: datetime) -> None:
        """Notify entities using local-calendar calculations."""
        for listener in tuple(self._daily_listeners):
            listener()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LizardCareConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lizard Care sensors."""
    data = entry.runtime_data
    time_updater = LizardCareSensorTimeUpdater(hass)
    async_add_entities(
        [
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[0],
                lambda state: state.last_fed,
                time_updater,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[1],
                lambda state: state.last_spot_clean,
                time_updater,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[2],
                lambda state: state.last_full_clean,
                time_updater,
            ),
            LizardCareTimestampSensor(
                data,
                entry.entry_id,
                TIMESTAMP_DESCRIPTIONS[3],
                lambda state: state.last_food_removed,
                time_updater,
            ),
            LizardCareAgeSensor(entry, time_updater),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[0],
                lambda config_entry: get_pet_profile(config_entry).species
                or None,
            ),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[1],
                get_birth_date,
            ),
            LizardCareProfileSensor(
                entry,
                PROFILE_DESCRIPTIONS[2],
                lambda config_entry: get_pet_profile(config_entry).sex,
            ),
            LizardCareNotesSensor(entry),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[0],
                _next_feeding_due,
                "feeding",
                time_updater,
            ),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[1],
                _next_spot_clean_due,
                "spot_clean",
                time_updater,
            ),
            LizardCareNextDueSensor(
                entry,
                NEXT_DUE_DESCRIPTIONS[2],
                _next_full_clean_due,
                "full_clean",
                time_updater,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[0],
                _next_feeding_due,
                "feeding",
                lambda instructions: instructions.feeding,
                time_updater,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[1],
                _next_spot_clean_due,
                "spot_clean",
                lambda instructions: instructions.spot_clean,
                time_updater,
            ),
            LizardCareStatusSensor(
                entry,
                STATUS_DESCRIPTIONS[2],
                _next_full_clean_due,
                "full_clean",
                lambda instructions: instructions.full_clean,
                time_updater,
            ),
            LizardCareOverallCareStatusSensor(entry, time_updater),
            LizardCareFoodRemovalStatusSensor(entry, time_updater),
            LizardCareLastCareActivitySensor(entry, time_updater),
        ]
    )


class LizardCareTimestampSensor(LizardCareEntity, SensorEntity):
    """Show the timestamp of a pet care action."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        data: LizardCareData,
        entry_id: str,
        description: SensorEntityDescription,
        value_fn: Callable[[LizardCareData], datetime | None],
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize a care timestamp sensor."""
        super().__init__(data, entry_id, description)
        self._value_fn = value_fn
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Subscribe to shared relative-time updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_minute_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the most recent care-action timestamp."""
        return self._value_fn(self._data)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return a friendly age for the care timestamp."""
        value = self._value_fn(self._data)
        if value is None:
            return None
        return {"relative_time": format_past_relative_time(value)}


class LizardCareAgeSensor(LizardCareEntity, SensorEntity):
    """Show the pet's age from its birthday or hatch date."""

    entity_description = AGE_DESCRIPTION

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize the age sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, AGE_DESCRIPTION)
        self._entry = entry
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Update the age when the local date changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_daily_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the pet's age in years and months."""
        birth_date = get_birth_date(self._entry)
        if birth_date is None:
            return None
        return _format_age(birth_date, dt_util.now().date())


class LizardCareProfileSensor(LizardCareEntity, SensorEntity):
    """Expose a read-only value from the pet profile."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        value_fn: Callable[[LizardCareConfigEntry], str | date | None],
    ) -> None:
        """Initialize a profile sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._value_fn = value_fn

    @property
    def native_value(self) -> str | date | None:
        """Return the current resolved profile value."""
        return self._value_fn(self._entry)


class LizardCareNotesSensor(LizardCareEntity, SensorEntity):
    """Expose profile notes without exceeding Home Assistant state limits."""

    entity_description = PROFILE_DESCRIPTIONS[3]

    def __init__(self, entry: LizardCareConfigEntry) -> None:
        """Initialize the notes sensor."""
        super().__init__(
            entry.runtime_data,
            entry.entry_id,
            PROFILE_DESCRIPTIONS[3],
        )
        self._entry = entry

    @property
    def native_value(self) -> str | None:
        """Return notes directly when they fit in an entity state."""
        notes = get_pet_profile(self._entry).notes
        if notes is None:
            return None
        if len(notes) <= MAX_SENSOR_STATE_LENGTH:
            return notes
        return f"{notes[: MAX_SENSOR_STATE_LENGTH - 3]}..."

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose long notes safely as an attribute."""
        notes = get_pet_profile(self._entry).notes
        if notes is None:
            return None
        return {"notes": notes}


class LizardCareNextDueSensor(LizardCareEntity, SensorEntity):
    """Show the next scheduled time for a care action."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        next_due_fn: Callable[
            [LizardCareConfigEntry, LizardCareData], datetime | None
        ],
        task_key: str,
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize a next-due sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._next_due_fn = next_due_fn
        self._task_key = task_key
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Subscribe to shared local-calendar updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_daily_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the calculated next due timestamp."""
        return self._next_due_fn(self._entry, self._data)

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, str | int | datetime] | None:
        """Return a calendar-aware relative due description."""
        value = self.native_value
        if value is None:
            return None
        attributes: dict[str, str | int | datetime] = {
            "relative_time": format_scheduled_relative_time(value)
        }
        attributes.update(
            _cleaning_schedule_attributes(
                self._entry,
                self._data,
                self._task_key,
            )
        )
        return attributes


class LizardCareStatusSensor(LizardCareEntity, SensorEntity):
    """Show whether a care action is due based on the local date."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        description: SensorEntityDescription,
        next_due_fn: Callable[
            [LizardCareConfigEntry, LizardCareData], datetime | None
        ],
        task_key: str,
        instruction_fn: Callable[[CareInstructions], str],
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize a care status sensor."""
        super().__init__(entry.runtime_data, entry.entry_id, description)
        self._entry = entry
        self._next_due_fn = next_due_fn
        self._task_key = task_key
        self._instruction_fn = instruction_fn
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Update status when the local date changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_daily_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the calculated schedule status."""
        next_due = self._next_due_fn(self._entry, self._data)
        schedule = get_care_schedule(self._entry)
        if (
            self._task_key == "spot_clean"
            and schedule.cleaning_schedule_mode == CLEANING_SCHEDULE_MONTHLY
            and schedule.full_clean_every == 1
        ):
            return CareStatus.NOT_DUE.value
        status = calculate_care_status(next_due)
        return status.value if status is not None else None

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, int | str | bool | datetime]:
        """Return due distance and optional task reference instructions."""
        instructions = self._instruction_fn(
            get_care_instructions(self._entry)
        )
        attributes: dict[str, int | str | bool] = {
            "has_instructions": bool(instructions)
        }
        if instructions:
            attributes["instructions"] = instructions
        counts = self._due_day_counts()
        if counts is not None:
            attributes["days_until_due"] = counts.days_until_due
            attributes["days_overdue"] = counts.days_overdue
        attributes.update(
            _cleaning_schedule_attributes(
                self._entry,
                self._data,
                self._task_key,
            )
        )
        return attributes

    def _due_day_counts(self) -> DueDayCounts | None:
        """Calculate local-calendar distance for this care schedule."""
        next_due = self._next_due_fn(self._entry, self._data)
        return calculate_due_day_counts(next_due)


class LizardCareFoodRemovalStatusSensor(LizardCareEntity, SensorEntity):
    """Show whether food currently needs to be removed."""

    entity_description = FOOD_REMOVAL_STATUS_DESCRIPTION

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize the food-removal status sensor."""
        super().__init__(
            entry.runtime_data,
            entry.entry_id,
            FOOD_REMOVAL_STATUS_DESCRIPTION,
        )
        self._entry = entry
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Update elapsed timing once per minute."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_minute_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str:
        """Return the current derived food-removal status."""
        return self._result().status.value

    @property
    def icon(self) -> str:
        """Return an icon matching the current food-removal status."""
        return {
            FoodRemovalStatus.NOT_NEEDED: "mdi:bowl-outline",
            FoodRemovalStatus.PENDING: "mdi:timer-sand",
            FoodRemovalStatus.DUE: "mdi:bowl-mix-outline",
            FoodRemovalStatus.OVERDUE: "mdi:alert-circle-outline",
        }[self._result().status]

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, bool | datetime | int | None]:
        """Return the feeding event and derived removal timing."""
        result = self._result()
        return {
            "food_in_enclosure": self._data.food_in_enclosure,
            "fed_at": self._data.last_fed,
            "due_at": result.due_at,
            "minutes_until_due": result.minutes_until_due,
            "minutes_overdue": result.minutes_overdue,
        }

    def _result(self) -> FoodRemovalResult:
        """Calculate current state from care data and pet options."""
        settings = get_food_removal_settings(self._entry)
        return calculate_food_removal_status(
            food_in_enclosure=self._data.food_in_enclosure,
            last_fed=self._data.last_fed,
            remove_after_hours=settings.remove_after_hours,
        )


class LizardCareOverallCareStatusSensor(LizardCareEntity, SensorEntity):
    """Summarize all currently configured care requirements."""

    entity_description = CARE_STATUS_DESCRIPTION

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize the overall care status sensor."""
        super().__init__(
            entry.runtime_data,
            entry.entry_id,
            CARE_STATUS_DESCRIPTION,
        )
        self._entry = entry
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Track local midnight and minute-level food-removal changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_daily_listener(
                self.async_write_ha_state
            )
        )
        self.async_on_remove(
            self._time_updater.async_add_minute_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str:
        """Return the aggregate care state."""
        return self._calculate_result().status.value

    @property
    def icon(self) -> str:
        """Return an icon matching the aggregate state."""
        return {
            OverallCareStatus.ALL_GOOD: "mdi:check-circle-outline",
            OverallCareStatus.ATTENTION_NEEDED: "mdi:alert-circle-outline",
            OverallCareStatus.OVERDUE: "mdi:alert-octagon-outline",
            OverallCareStatus.UNKNOWN: "mdi:help-circle-outline",
        }[self._calculate_result().status]

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, list[str] | str | int | datetime]:
        """Explain which care items contribute to the aggregate state."""
        result = self._calculate_result()
        attributes: dict[str, list[str] | str | int | datetime] = {
            "attention_items": list(result.attention_items),
            "overdue_items": list(result.overdue_items),
            "summary": _care_status_summary(result),
        }
        attributes.update(
            _cleaning_schedule_attributes(
                self._entry,
                self._data,
                "spot_clean",
            )
        )
        return attributes

    def _calculate_result(self) -> OverallCareResult:
        """Calculate current status directly from runtime and options data."""
        schedule = get_care_schedule(self._entry)
        today = dt_util.now().date()
        item_statuses: dict[str, CareStatus | None] = {}
        item_statuses["feeding"] = calculate_care_status(
            calculate_next_due(
                self._data.last_fed,
                schedule.feeding_interval_days,
            ),
            today,
        )
        if self._data.food_in_enclosure:
            item_statuses["food_removal"] = self._food_removal_status()
        item_statuses["spot_clean"] = _cleaning_status(
            self._entry,
            self._data,
            "spot_clean",
            today,
        )
        item_statuses["full_clean"] = _cleaning_status(
            self._entry,
            self._data,
            "full_clean",
            today,
        )
        return calculate_overall_care_status(item_statuses)

    def _food_removal_status(self) -> CareStatus | None:
        """Return the current contribution from food in the enclosure."""
        settings = get_food_removal_settings(self._entry)
        status = calculate_food_removal_status(
            food_in_enclosure=self._data.food_in_enclosure,
            last_fed=self._data.last_fed,
            remove_after_hours=settings.remove_after_hours,
        ).status
        return {
            FoodRemovalStatus.NOT_NEEDED: CareStatus.NOT_DUE,
            FoodRemovalStatus.PENDING: CareStatus.NOT_DUE,
            FoodRemovalStatus.DUE: CareStatus.DUE_TODAY,
            FoodRemovalStatus.OVERDUE: CareStatus.OVERDUE,
        }[status]


class LizardCareLastCareActivitySensor(LizardCareEntity, SensorEntity):
    """Show the newest feeding, removal, or cleaning activity."""

    entity_description = LAST_CARE_ACTIVITY_DESCRIPTION

    def __init__(
        self,
        entry: LizardCareConfigEntry,
        time_updater: LizardCareSensorTimeUpdater,
    ) -> None:
        """Initialize the last care activity sensor."""
        super().__init__(
            entry.runtime_data,
            entry.entry_id,
            LAST_CARE_ACTIVITY_DESCRIPTION,
        )
        self._time_updater = time_updater

    async def async_added_to_hass(self) -> None:
        """Subscribe to the shared minute-level relative-time update."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._time_updater.async_add_minute_listener(
                self.async_write_ha_state
            )
        )

    @property
    def native_value(self) -> str | None:
        """Return the most recent activity type."""
        activity = self._last_activity()
        return activity.activity.value if activity is not None else None

    @property
    def icon(self) -> str:
        """Return an icon matching the most recent activity."""
        activity = self._last_activity()
        if activity is None:
            return "mdi:history"
        return {
            CareActivity.FED: "mdi:food-apple-outline",
            CareActivity.FOOD_REMOVED: "mdi:bowl-outline",
            CareActivity.SPOT_CLEAN: "mdi:spray-bottle",
            CareActivity.FULL_CLEAN: "mdi:shimmer",
        }[activity.activity]

    @property
    def extra_state_attributes(
        self,
    ) -> dict[str, str | datetime] | None:
        """Return friendly details for the most recent activity."""
        activity = self._last_activity()
        if activity is None:
            return None
        labels = {
            CareActivity.FED: "Fed",
            CareActivity.FOOD_REMOVED: "Food Removed",
            CareActivity.SPOT_CLEAN: "Spot Clean",
            CareActivity.FULL_CLEAN: "Full Clean",
        }
        return {
            "activity": labels[activity.activity],
            "timestamp": activity.timestamp,
            "relative_time": format_past_relative_time(activity.timestamp),
        }

    def _last_activity(self) -> LastCareActivity | None:
        """Resolve the newest care timestamp from runtime state."""
        return find_last_care_activity(
            {
                CareActivity.FED: self._data.last_fed,
                CareActivity.FOOD_REMOVED: self._data.last_food_removed,
                CareActivity.SPOT_CLEAN: self._data.last_spot_clean,
                CareActivity.FULL_CLEAN: self._data.last_full_clean,
            }
        )


def _effective_last_spot_clean(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
) -> datetime | None:
    """Resolve the event currently satisfying the spot-clean schedule."""
    schedule = get_care_schedule(entry)
    return calculate_effective_last_spot_clean(
        data.last_spot_clean,
        data.last_full_clean,
        full_clean_satisfies_spot_clean=(
            schedule.full_clean_satisfies_spot_clean
        ),
    )


def _monthly_cleaning_plan(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
) -> MonthlyCleaningPlan:
    """Return the deterministic monthly plan for current persisted state."""
    return calculate_monthly_cleaning_plan(
        get_care_schedule(entry),
        data.last_spot_clean,
        data.last_full_clean,
    )


def _next_feeding_due(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
) -> datetime | None:
    """Return the unchanged interval-based feeding due timestamp."""
    return calculate_next_due(
        data.last_fed,
        get_care_schedule(entry).feeding_interval_days,
    )


def _next_spot_clean_due(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
) -> datetime | None:
    """Return the next spot-clean date for the configured schedule mode."""
    schedule = get_care_schedule(entry)
    if schedule.cleaning_schedule_mode == CLEANING_SCHEDULE_MONTHLY:
        return _monthly_cleaning_plan(entry, data).next_spot_clean
    return calculate_next_due(
        _effective_last_spot_clean(entry, data),
        schedule.spot_clean_interval_days,
    )


def _next_full_clean_due(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
) -> datetime | None:
    """Return the next full-clean date for the configured schedule mode."""
    schedule = get_care_schedule(entry)
    if schedule.cleaning_schedule_mode == CLEANING_SCHEDULE_MONTHLY:
        return _monthly_cleaning_plan(entry, data).next_full_clean
    return calculate_next_due(
        data.last_full_clean,
        schedule.full_clean_interval_days,
    )


def _cleaning_status(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
    task_key: str,
    today: date | None = None,
) -> CareStatus | None:
    """Return a cleaning status, including an intentionally skipped Spot Clean."""
    schedule = get_care_schedule(entry)
    if (
        task_key == "spot_clean"
        and schedule.cleaning_schedule_mode == CLEANING_SCHEDULE_MONTHLY
        and schedule.full_clean_every == 1
    ):
        return CareStatus.NOT_DUE
    next_due = (
        _next_spot_clean_due(entry, data)
        if task_key == "spot_clean"
        else _next_full_clean_due(entry, data)
    )
    return calculate_care_status(next_due, today)


def _cleaning_schedule_attributes(
    entry: LizardCareConfigEntry,
    data: LizardCareData,
    task_key: str,
) -> dict[str, str | int | datetime]:
    """Return monthly context for existing cleaning entities."""
    if task_key not in ("spot_clean", "full_clean"):
        return {}
    schedule = get_care_schedule(entry)
    attributes: dict[str, str | int | datetime] = {
        "schedule_mode": schedule.cleaning_schedule_mode,
    }
    if schedule.cleaning_schedule_mode != CLEANING_SCHEDULE_MONTHLY:
        return attributes
    plan = _monthly_cleaning_plan(entry, data)
    attributes.update(
        {
            "scheduled_day": schedule.cleaning_day_of_month,
            "cleaning_occurrence_type": plan.cleaning_occurrence_type.value,
            "next_cleaning": plan.next_cleaning,
            "next_full_clean": plan.next_full_clean,
            "occurrence_number": plan.occurrence_number,
        }
    )
    return attributes


def _care_status_summary(result: OverallCareResult) -> str:
    """Return a concise human-readable explanation of aggregate care."""
    if result.status is OverallCareStatus.ALL_GOOD:
        return "All care is up to date"
    if result.status is OverallCareStatus.UNKNOWN:
        return "Care status is not yet available"

    items = (
        result.overdue_items
        if result.status is OverallCareStatus.OVERDUE
        else result.attention_items
    )
    labels = {
        "feeding": "Feeding",
        "food_removal": "Food Removal",
        "spot_clean": "Spot Clean",
        "full_clean": "Full Clean",
    }
    item_names = [labels[item] for item in items]
    joined = (
        item_names[0]
        if len(item_names) == 1
        else f"{', '.join(item_names[:-1])} and {item_names[-1]}"
    )
    if result.status is OverallCareStatus.OVERDUE:
        return f"{joined} {'is' if len(items) == 1 else 'are'} overdue"
    if items == ("food_removal",):
        return "Food needs to be removed"
    return f"{joined} {'needs' if len(items) == 1 else 'need'} attention"


def _format_age(birth_date: date, today: date) -> str | None:
    """Format an age using completed calendar years and months."""
    if birth_date > today:
        return None

    total_months = (today.year - birth_date.year) * 12
    total_months += today.month - birth_date.month
    if today.day < birth_date.day:
        total_months -= 1

    years, months = divmod(max(total_months, 0), 12)
    parts: list[str] = []
    if years:
        parts.append(f"{years} {'year' if years == 1 else 'years'}")
    if months or not years:
        parts.append(f"{months} {'month' if months == 1 else 'months'}")
    return ", ".join(parts)
