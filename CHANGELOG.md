# Changelog

All notable changes to this integration. Dates are release dates.

## v1.2.4
- Fix `Handler DanfossEcoConfigFlow doesn't support step no_devices` crash when
  opening the setup flow while nothing was being advertised (missing
  `async_step_no_devices` handler for the "no thermostat detected" menu).

## v1.2.3 — important
- Fix a `NameError` that broke **every** polling cycle since v1.0.3: `read_state`
  referenced the schedule characteristic UUIDs without importing them, so no
  device ever populated its data (entities stuck *unavailable* regardless of
  signal). Added `pyflakes` to the pre-release checks to catch this class of bug.

## v1.2.2
- Keep the guided (button-press) pairing wizard as the primary path. When nothing
  is advertising, the flow now offers "Search again" / "Add manually (advanced)"
  instead of dropping straight into manual entry.

## v1.2.1
- Setup no longer blocks on the first poll: entities are created immediately
  (shown *unavailable* until a poll succeeds) so the device page and the
  **Refresh now** button are always available even for an out-of-range device.
- The Refresh now button stays pressable while polls are failing.

## v1.2.0
- Add a **Refresh now** diagnostic button to force an immediate read.

## v1.1.0
- **Reconfigure** flow: update a device's secret key / PIN from the UI.
- **Diagnostics** download (secret key and address redacted).
- Read the weekly schedule within the same BLE connection as the rest of the
  state — one radio wake per poll instead of two.
- `PARALLEL_UPDATES = 1` to serialize commands.

## v1.0.3
- **Manual add** by MAC + secret key (for devices not currently advertising, or
  to reuse a key from etrv2mqtt / libetrv).
- **Weekly schedule** support — comfort/setback temperature numbers, a
  human-readable *Weekly schedule* sensor, and the `set_schedule` service. The
  44-byte schedule format was reverse-engineered and verified on real hardware
  (prior projects left it unimplemented).

## v1.0.0
- First stable release: Bluetooth discovery + guided pairing wizard, climate
  entity (manual/schedule/vacation), all device settings (min/max, frost
  protection, adaptive/slow regulation, display flip, mounting, montage, child
  lock), automatic clock sync, vacation service, diagnostics (battery, room
  temperature, RSSI + source proxy, last poll, decoded error flags). Translations:
  English, Polish, German, Danish. Own brand icon/logo. Validated end-to-end on
  Danfoss Eco 2 (014G1001) hardware over an ESPHome Bluetooth proxy.
