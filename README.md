# Lizard Care for Home Assistant

Lizard Care is a UI-configured Home Assistant custom integration for tracking
the care of reptile pets. Each pet is a separate config entry and Home
Assistant device. It exposes profile information, feeding and enclosure-clean
history, care actions, configurable due intervals, derived status sensors, and
optional care instructions.

Lizard Care does not send notifications. Its sensors are the source of truth;
normal Home Assistant automations decide when, where, and how to notify. Two
included automation blueprints provide a ready-to-use notification model.

## Manual integration installation

1. Copy `custom_components/lizardcare` into your Home Assistant configuration's
   `custom_components` directory. The resulting path is
   `/config/custom_components/lizardcare`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **Lizard Care** and complete the form.

Repeat the final two steps to add another pet. YAML configuration is not
supported.

Existing entries from versions with built-in notifications continue to load.
Old notification targets, reminder times, enable switches, and repeat settings
are ignored. Opening and saving Lizard Care options removes those obsolete
values while retaining profile, schedule, instruction, and food-removal timing
settings.

## Food removal status

The per-pet **Remove food after (hours)** option defines the intended removal
time relative to the actual **Last Fed** timestamp. It does not schedule or send
a notification.

`sensor.<pet>_food_removal_status` reports:

- `not_needed` — no food is currently in the enclosure.
- `pending` — food is present and its removal time has not arrived.
- `due` — the removal time has arrived.
- `overdue` — food has remained for at least one hour after the removal time.

The sensor includes `food_in_enclosure`, `fed_at`, `due_at`,
`minutes_until_due`, and `minutes_overdue` attributes. Pressing **Remove Food**
or correcting care timestamps updates the derived state through the existing
care-state architecture.

## Automation blueprints

The repository includes:

- **Lizard Care — Care Reminders** — sends a daily feeding, spot-clean, and
  full-clean reminder based on the three Lizard Care status sensors, then
  repeats only tasks that remain overdue.
- **Lizard Care — Food Removal Reminder** — sends when Food Removal Status
  becomes `due` and repeats while it remains `due` or `overdue`.

### Install the blueprints

HACS integration downloads install files from `custom_components/lizardcare`;
they do not install repository-root blueprint files into Home Assistant's
`blueprints` directory. Install each blueprint separately using either method:

1. In Home Assistant, go to **Settings → Automations & scenes → Blueprints**.
2. Select **Import Blueprint**.
3. Import each GitHub file URL:
   - `https://github.com/NolanBecker/ha-lizardcare/blob/main/blueprints/automation/lizardcare/care_reminders.yaml`
   - `https://github.com/NolanBecker/ha-lizardcare/blob/main/blueprints/automation/lizardcare/food_removal_reminder.yaml`

Alternatively, copy both repository files into
`/config/blueprints/automation/lizardcare/` and reload automations.

### Create a care-reminder automation

1. Open **Settings → Automations & scenes → Blueprints**.
2. Find **Lizard Care — Care Reminders** and select **Create automation**.
3. Choose one pet's Feeding Status, Spot Clean Status, and Full Clean Status
   sensors.
4. Choose the notify target, reminder time, enabled care categories, and repeat
   interval.
5. Save the automation.

The normal reminder runs at the selected time. Repeats occur only for sensors
still in `overdue`; recording or correcting the task naturally ends the loop.

### Create a food-removal automation

1. Find **Lizard Care — Food Removal Reminder** and select **Create
   automation**.
2. Choose the pet's Food Removal Status sensor and a notify target.
3. Set the repeat interval and optionally customize the title, message, or pet
   name.
4. Save the automation.

When the integration reports `not_needed` or `pending`, the blueprint does not
send and any active repeat loop stops.

## Development and testing

Clone the repository and symlink or copy `custom_components/lizardcare` into a
Home Assistant development or test configuration. Restart Home Assistant after
integration changes and reload automations after blueprint changes.

Run the available checks from the repository root:

```bash
python3 -m compileall custom_components/lizardcare tests
python3 -m pytest
```

In Home Assistant, verify config-entry setup and reload, profile editing,
persistent care timestamps, all action buttons, manual corrections, due-status
transitions, Full Clean satisfying Spot Clean, care instructions, Food Removal
Status transitions, and automations created from both blueprints.
