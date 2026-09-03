"""Constants for the Lizard Care integration."""

DOMAIN = "lizardcare"
MANUFACTURER = "Lizard Care"

CONF_PET_NAME = "pet_name"
CONF_NORMALIZED_PET_NAME = "normalized_pet_name"
CONF_SPECIES = "species"
CONF_BIRTH_DATE = "birth_date"
CONF_SEX = "sex"
CONF_NOTES = "notes"
CONF_FEEDING_INSTRUCTIONS = "feeding_instructions"
CONF_SPOT_CLEAN_INSTRUCTIONS = "spot_clean_instructions"
CONF_FULL_CLEAN_INSTRUCTIONS = "full_clean_instructions"

DEFAULT_FEEDING_INSTRUCTIONS = ""
DEFAULT_SPOT_CLEAN_INSTRUCTIONS = ""
DEFAULT_FULL_CLEAN_INSTRUCTIONS = ""

DEFAULT_SPECIES = "Gargoyle Gecko"

CONF_FEEDING_INTERVAL_DAYS = "feeding_interval_days"
CONF_SPOT_CLEAN_INTERVAL_DAYS = "spot_clean_interval_days"
CONF_FULL_CLEAN_INTERVAL_DAYS = "full_clean_interval_days"
CONF_FULL_CLEAN_SATISFIES_SPOT_CLEAN = (
    "full_clean_satisfies_spot_clean"
)
CONF_CLEANING_SCHEDULE_MODE = "cleaning_schedule_mode"
CONF_CLEANING_DAY_OF_MONTH = "cleaning_day_of_month"
CONF_FULL_CLEAN_EVERY = "full_clean_every"
CONF_CLEANING_CYCLE_ANCHOR = "cleaning_cycle_anchor"

DEFAULT_FEEDING_INTERVAL_DAYS = 2
DEFAULT_SPOT_CLEAN_INTERVAL_DAYS = 7
DEFAULT_FULL_CLEAN_INTERVAL_DAYS = 30
DEFAULT_FULL_CLEAN_SATISFIES_SPOT_CLEAN = True
DEFAULT_CLEANING_SCHEDULE_MODE = "interval"
DEFAULT_CLEANING_DAY_OF_MONTH = 1
DEFAULT_FULL_CLEAN_EVERY = 3

CLEANING_SCHEDULE_INTERVAL = "interval"
CLEANING_SCHEDULE_MONTHLY = "monthly"

# Keep the existing option key so previously configured removal delays carry
# forward. It is now care timing, independent of notifications.
CONF_REMOVE_FOOD_AFTER_HOURS = "food_removal_delay_hours"
DEFAULT_REMOVE_FOOD_AFTER_HOURS = 12
FOOD_REMOVAL_OVERDUE_AFTER_MINUTES = 60

STORAGE_VERSION = 1

STATE_LAST_FED = "last_fed"
STATE_LAST_FOOD_REMOVED = "last_food_removed"
STATE_FOOD_IN_ENCLOSURE = "food_in_enclosure"
STATE_LAST_SPOT_CLEAN = "last_spot_clean"
STATE_LAST_FULL_CLEAN = "last_full_clean"
