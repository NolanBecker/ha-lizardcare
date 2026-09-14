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

## Cleaning schedules

Cleaning can use either scheduling mode:

- **Interval** preserves the original behavior: the next Spot Clean and Full
  Clean dates are calculated from their configured day intervals and latest
  completion timestamps.
- **Monthly** anchors cleaning to a selected day of every calendar month. If
  that day does not exist in a month, Lizard Care uses the month's last valid
  day—for example, day 31 becomes February 28 (or 29 in a leap year) and April
  30.

**Spot Clean enabled** defaults on for backward compatibility. When disabled,
Spot Clean Status reports `disabled`, Next Spot Clean has no timestamp and
therefore displays as unknown, and the Spot Clean button is unavailable. Last
Spot Clean history, its correction control, instructions, and saved schedule
settings remain intact so re-enabling Spot Clean resumes the previous setup.
Overall Care Status and reminder automations ignore disabled Spot Clean, while
Full Clean continues on its own interval or monthly cadence.

Monthly mode also provides **Full clean every** and **Full-clean cycle anchor**.
The anchor's month is occurrence 1, and every Nth occurrence is a Full Clean.
For an October anchor and a cadence of 3, October and November are Spot Cleans,
December is a Full Clean, and the pattern repeats without drifting.

Completing a scheduled cleaning late keeps the next cleaning on its configured
calendar day. A completion up to seven days early counts for the upcoming
occurrence. Because occurrence numbers are derived from the saved anchor and
calendar month, restarts, reloads, and duplicate completion presses do not
advance a mutable counter. On a Full Clean occurrence, Spot Clean is skipped;
completing the Full Clean satisfies that monthly cleaning occurrence.

## Care History journal

Each pet has a durable, chronological Care History journal. Pressing **Feed**,
**Remove Food**, **Spot Clean**, or **Full Clean** automatically records one
entry alongside the existing care-state update. Timestamp corrections do not
create journal entries and the journal does not replace the timestamps used for
scheduling.

Journal data is stored locally in Home Assistant's `.storage` directory in a
separate versioned file per config entry. It survives restarts and is independent
of Recorder database retention and purges. Notes and optional structured metadata
remain on the Home Assistant host; they are not sent externally by Lizard Care.

The integration provides these actions under the `lizardcare` domain:

- `lizardcare.add_journal_entry` adds a manual Note, Feeding, Food Removed,
  Spot Clean, Full Clean, Shed, Weight, Enclosure, Health, or Other event. Select
  the pet device and optionally provide a note, timezone-aware timestamp, or
  metadata such as `{weight: 42, unit: g}`.
- `lizardcare.delete_journal_entry` deletes one entry by its stable ID. There is
  intentionally no bulk-clear action.
- `lizardcare.get_journal_entries` returns the selected pet's entries newest
  first for scripts, developer tools, and future dashboard integrations. It can
  filter by event type and inclusive start/end datetimes; all filters combine,
  and the 1–1000 limit is applied afterward.

For a manual Weight entry, provide **Weight value** greater than zero and choose
`g` or `oz` as **Weight unit**. These are normalized into metadata such as
`{value: 42.5, unit: g}`. Home Assistant service selectors cannot conditionally
hide fields based on another field, so Weight value/unit remain visible for all
event types and are only required and processed when Event type is Weight.

Example action data:

```yaml
action: lizardcare.add_journal_entry
data:
  device_id: YOUR_LIZARD_CARE_DEVICE_ID
  event_type: shed
  note: Shed looks almost complete
```

The **Last Journal Activity** timestamp sensor exposes only the latest journal
entry's event type, source, note, and entry ID as small attributes. The complete
journal is never placed in entity state or attributes.

## Automation blueprints

The repository includes:

- **Lizard Care — Care Reminders** — sends `due_today` notices at the selected
  daily time, sends immediately when feeding, spot cleaning, or full cleaning
  becomes `overdue`, and repeats each overdue task independently.
- **Lizard Care — Food Removal Reminder** — sends when Food Removal Status
  becomes `due` and repeats while it remains `due` or `overdue`.
- **Lizard Care — Vacation Care Reminder** — sends one advisory feeding
  reminder on the day before an event begins on the selected vacation calendar.

Each pet has an optional **Vacation calendar** setting. Select the same calendar
again in each applicable Care Reminders, Food Removal Reminder, and Vacation
Care Reminder automation. Home Assistant blueprints cannot read a custom
integration's config-entry options automatically. While an event is actively in progress,
the Care Reminders and Food Removal Reminder blueprints suppress notifications
without changing care states, due dates, or timestamps. Timed events use their
actual start and exclusive end instants; all-day and multi-day events use Home
Assistant's calendar start/end boundaries. Before the event begins and after it
ends, the existing anchored reminder rules continue normally. A missing or
temporarily unavailable calendar fails open, preserving normal reminders.

### Install the blueprints

HACS integration downloads install files from `custom_components/lizardcare`;
they do not install repository-root blueprint files into Home Assistant's
`blueprints` directory. Install each blueprint separately using either method:

1. In Home Assistant, go to **Settings → Automations & scenes → Blueprints**.
2. Select **Import Blueprint**.
3. Import each GitHub file URL:
   - `https://github.com/NolanBecker/ha-lizardcare/blob/main/blueprints/automation/lizardcare/care_reminders.yaml`
   - `https://github.com/NolanBecker/ha-lizardcare/blob/main/blueprints/automation/lizardcare/food_removal_reminder.yaml`
   - `https://github.com/NolanBecker/ha-lizardcare/blob/main/blueprints/automation/lizardcare/vacation_care_reminder.yaml`

Alternatively, copy all three repository files into
`/config/blueprints/automation/lizardcare/` and reload automations.

### Create a care-reminder automation

1. Open **Settings → Automations & scenes → Blueprints**.
2. Find **Lizard Care — Care Reminders** and select **Create automation**.
3. Choose one pet's Feeding Status, Spot Clean Status, and Full Clean Status
   sensors.
4. Enter one or more Companion notification services, choose the optional
   Vacation calendar, reminder time, enabled care categories, and
   overdue repeat intervals. Each category has a numeric value and an
   independent **Minutes** or **Hours** unit. Feeding defaults to **1 hour**;
   Spot Clean and Full Clean share a cleaning interval that defaults to
   **24 hours**. Set **Overdue reminder end time** to control when recurring
   notices stop each day; the default is 11:00 PM.
5. Save the automation.

Each blueprint supports an optional custom notification title and multiline
message. Leave either field blank to use its contextual built-in default. Set
**Dashboard URL** (default `/mobile-dashboard/pixel`) to the relative Home
Assistant dashboard/view that should open when the notification body is tapped.
Select the matching Lizard Care action buttons when creating the automation.
These selectors default to blank so existing automations continue working after
the blueprint update; no action button is shown until its entity is selected.

Notifications include one contextual Companion app action on both Android and
iOS: **Mark as Fed**, **Mark Food Removed**, or **Mark as Cleaned**. The
automation handles `mobile_app_notification_action` events and calls the
selected Feed, Remove Food, Spot Clean, or Full Clean button. This updates care
history and scheduling exactly as pressing that button in Home Assistant would.
Action IDs include the automation entity ID and task, isolating different pets
and blueprint instances. When multiple recipients receive a notification,
either recipient can complete the same underlying care action.

For actionable delivery, enter each recipient as a fully qualified Companion
App notify service, such as `notify.mobile_app_nolans_phone` or
`notify.mobile_app_iphone`. Add both services to send the same notification to
Android and iOS. The blueprints call each service directly because the generic
entity-based `notify.send_message` action rejects Companion-specific nested
`url` and `actions` data.

After re-importing this blueprint version, edit every existing automation and
populate **Companion notification services**. The old notify entity target is
retained as an unused legacy input so existing automation YAML continues to
load, but it no longer delivers notifications. Copy the service names from
**Developer tools → Actions**; they normally begin with `notify.mobile_app_`.

At the selected Reminder Time, `due_today` notices are sent once. An `overdue`
transition sends immediately, and a minute-level check honors the configured
repeat interval independently for every task. Reminder Time is also the local
wall-clock anchor for overdue repeats. For example, with a 4:00 PM
Reminder Time, a one-hour Feeding interval repeats at 4:00 PM, 5:00 PM, and
6:00 PM, while a 24-hour Cleaning interval repeats at 4:00 PM each local day.
Recurring reminders run only from Reminder Time through the inclusive End
Time, then pause until the next daily window. An End Time earlier than Reminder
Time creates an overnight window, such as 8:00 PM through 1:00 AM. The initial
transition into `overdue` still notifies immediately even outside the window.
Recording or correcting a task stops its overdue messages without affecting
other overdue tasks. Startup recovery sends only inside the window; automation
reloads resume the same anchored cadence without starting a new countdown.

After re-importing this blueprint over an older version, edit and save each
existing care-reminder automation once. Home Assistant displays the new Feeding
and Cleaning value/unit inputs with their defaults; the removed global and
legacy interval inputs are no longer used. The automation does not need to be
recreated.

### Create a food-removal automation

1. Find **Lizard Care — Food Removal Reminder** and select **Create
   automation**.
2. Choose the pet's Food Removal Status sensor and enter its Companion
   notification service or services.
3. Set **Reminder time / schedule anchor** to the same local time as the pet's
   **Food removal anchor time** integration option.
4. Choose the daily overdue-reminder End Time and a repeat value/unit, such as
   **1 Hour** or **30 Minutes**, then optionally customize the title, message,
   or pet name.
5. Save the automation.

Food Removal Status remains the scheduling source of truth. Its `due_at` is the
feeding day's Food removal anchor time plus the configured Food removal delay,
not the exact feeding timestamp. For example, a 4:00 PM anchor plus 24 Hours is
due at 4:00 PM the next day even when Feed was recorded at 4:37 PM. Configure
the anchor and delay value/unit under the pet's Lizard Care options.

The blueprint sends immediately when the status first becomes `due` or
`overdue`, even outside the daily recurring window. Later reminders follow the
`due_at`-anchored cadence only inside the inclusive Reminder Time–End Time
window. Overnight windows are supported. Startup recovery respects the window,
and `not_needed` or `pending` naturally stops all reminders without a
long-running repeat loop.

After updating the Food Removal Reminder blueprint, edit and save the existing
automation once to configure the new Reminder Time, End Time, and repeat
value/unit inputs. The removed hours-only `repeat_interval` input is ignored;
the automation does not need to be recreated.

### Create a vacation-care automation

1. Find **Lizard Care — Vacation Care Reminder** and select **Create
   automation**.
2. Choose the pet's Vacation calendar and enter its Companion notification
   service or services.
3. Set the day-before Reminder Time (default 4:00 PM), enter the pet name, and
   optionally customize the title or message.
4. Save the automation.

At the configured local time, the blueprint asks the generic Home Assistant
calendar API for events intersecting tomorrow, then sends once if one or more
events actually start tomorrow. Feeding does not need to be due. Multiple
events on that start date still produce one message. If Home Assistant starts
after the configured Reminder Time, the automation recovers a missed reminder.
It uses the automation entity's restored `last_triggered` timestamp to avoid
repeating a reminder already handled at or after today's Reminder Time. A
startup before the configured time does not send early or block the normal time
trigger. Use the normal Feed button afterward; food-removal state and reminders
continue through their existing workflow.

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
Status transitions, interval and monthly cleaning schedules, and automations
created from both blueprints.
