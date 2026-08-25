"""Constants for the Lizard Care integration."""

DOMAIN = "lizardcare"
MANUFACTURER = "Lizard Care"

CONF_PET_NAME = "pet_name"
CONF_NORMALIZED_PET_NAME = "normalized_pet_name"
CONF_SPECIES = "species"
CONF_BIRTH_DATE = "birth_date"
CONF_SEX = "sex"

DEFAULT_SPECIES = "Gargoyle Gecko"

CONF_FEEDING_INTERVAL_DAYS = "feeding_interval_days"
CONF_SPOT_CLEAN_INTERVAL_DAYS = "spot_clean_interval_days"
CONF_FULL_CLEAN_INTERVAL_DAYS = "full_clean_interval_days"

DEFAULT_FEEDING_INTERVAL_DAYS = 2
DEFAULT_SPOT_CLEAN_INTERVAL_DAYS = 7
DEFAULT_FULL_CLEAN_INTERVAL_DAYS = 30

STORAGE_VERSION = 1

STATE_LAST_FED = "last_fed"
STATE_LAST_FOOD_REMOVED = "last_food_removed"
STATE_FOOD_IN_ENCLOSURE = "food_in_enclosure"
STATE_LAST_SPOT_CLEAN = "last_spot_clean"
STATE_LAST_FULL_CLEAN = "last_full_clean"
