# Lizard Care for Home Assistant

Lizard Care is a custom Home Assistant integration for creating a profile and
device for each reptile. This initial version supports UI-based setup of a pet's
name, species, birthday or hatch date, and sex. It does not create entities or
provide care tracking yet.

## Manual installation

1. Copy `custom_components/lizardcare` from this repository into the
   `custom_components` directory inside your Home Assistant configuration
   directory. The resulting path should be
   `/config/custom_components/lizardcare`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **Lizard Care** and complete the form.

Repeat the final two steps to add another pet. Each pet is stored as a separate
config entry and represented by a separate Home Assistant device.

## Development and testing

For local development, clone this repository and symlink or copy
`custom_components/lizardcare` into the `custom_components` directory of a Home
Assistant development or test configuration. Restart Home Assistant after code
changes, then exercise the setup flow from **Settings → Devices & Services**.

At minimum, verify that the integration appears in the integration picker, the
profile fields are saved, duplicate names (including case and whitespace
variations) are rejected, and one correctly named device is created per pet.

This integration is configured only through the Home Assistant UI; YAML
configuration is not supported.
