# Changelog

All notable changes to this integration. Dates are release dates.

## v1.3.0 — offline resilience

Radiator valves are weak-signal, deep-sleeping BLE devices. A proxy that is busy
(an ESPHome build pegging its CPU), a valve that drifts out of range, or a Home
Assistant restart used to blank the whole device and throw away whatever the user
had just asked for. That is now handled:

- **Cached readings.** A failed poll no longer makes the device *unavailable*.
  The last successful reading stays on show for `Keep the last reading for`
  hours (default 24, `0` = forever), and `Last poll` tells you how old it is.
  The cache is written to `.storage/danfoss_eco.<entry_id>` and restored on
  startup, so a restart no longer blanks the dashboard either.
- **Queued commands.** Setting a temperature (or a mode, config switch, comfort/
  setback temperature or weekly program) while the thermostat is out of reach no
  longer fails — the change is coalesced into a persistent queue, shown
  immediately on the entity, and written the moment the device is next reachable.
  Undelivered commands expire after `Keep undelivered commands for` hours
  (default 24, `0` = forever).
- **Faster recovery.** A failed poll is retried after 1, 2, 5, 10 then 15 minutes
  instead of waiting out the whole poll interval, and an advertisement from the
  thermostat triggers an immediate retry — so a valve that comes back within
  range of a proxy is picked up straight away.
- **New entities:** *Connection* (binary sensor — whether the radio link is
  actually up, with last success / last advertisement / last error attributes),
  *Pending commands* (sensor — count, with a readable list of what is queued),
  and *Discard pending commands* (button). The climate entity gained `cached`,
  `pending_writes`, `last_poll` and `pending_target_temperature` attributes.
- **One connection per cycle.** Queued writes are flushed inside the polling
  connection and applied to the settings block the device holds *right now*, then
  read back for confirmation — no separate radio wake-up per command.
- **Connections are serialized across all thermostats.** Three valves dialling
  one proxy at once is the quickest way to produce *"no backend with an available
  connection slot"*.
- Fix: a device that keeps the `E10 invalid time` flag raised even after its clock
  has been written correctly (seen on real hardware) no longer queues a clock sync
  on every single poll — E10 alone now triggers at most one resync per day.

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
