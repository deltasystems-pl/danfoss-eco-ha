# Danfoss Eco for Home Assistant — Full Documentation

> Everything about how this integration works, how to use it, how the Danfoss Eco
> talks over Bluetooth, and how to troubleshoot it. If you only want to get going,
> the [Quick start](#2-quick-start) is enough; the rest is here for the curious and
> for when something goes wrong.

## Table of contents

1. [What this integration is](#1-what-this-integration-is)
2. [Quick start](#2-quick-start)
3. [Supported hardware](#3-supported-hardware)
4. [How the Danfoss Eco works over Bluetooth](#4-how-the-danfoss-eco-works-over-bluetooth)
5. [Installation](#5-installation)
6. [Pairing — the wizard in detail](#6-pairing--the-wizard-in-detail)
7. [Entities reference](#7-entities-reference)
8. [Options & configuration](#8-options--configuration)
9. [Services](#9-services)
10. [Automations & examples](#10-automations--examples)
11. [How the integration works internally](#11-how-the-integration-works-internally)
12. [The protocol, byte by byte](#12-the-protocol-byte-by-byte)
13. [Bluetooth proxies & range](#13-bluetooth-proxies--range)
14. [Building a dashboard](#14-building-a-dashboard)
15. [Troubleshooting](#15-troubleshooting)
16. [FAQ](#16-faq)
17. [Credits, license & prior art](#17-credits-license--prior-art)

---

## 1. What this integration is

A native Home Assistant integration for **Danfoss Eco** and **Danfoss Eco 2**
electronic radiator thermostats (eTRV) — the battery-powered valve heads you screw
onto a radiator, model numbers like **014G1001**. These devices speak Bluetooth Low
Energy (BLE) with a proprietary, encrypted protocol; Danfoss's own way to use them
is the *Danfoss Eco* phone app, one device at a time.

This integration brings them into Home Assistant as first-class **climate** devices:
you get a thermostat card, schedule/vacation modes, all of the advanced settings the
app exposes, and diagnostics — controllable from automations, dashboards, voice, and
anything else HA can drive. It works both with a **local Bluetooth adapter** on the
HA host and, crucially, with **ESPHome Bluetooth proxies**, so a single cheap ESP32
near your radiators is enough.

What makes it friendly: **you never type a MAC address or a hex key.** Thermostats
are auto-discovered, and a wizard walks you through the one physical action the
device requires — a press of its button — then reads the encryption key off the
device itself.

---

## 2. Quick start

1. Install via HACS (see [Installation](#5-installation)) and restart Home Assistant.
2. Make sure a Bluetooth adapter or an **ESPHome Bluetooth proxy** is within a few
   metres of the thermostat.
3. Go to **Settings → Devices & Services**. Your thermostat should appear as a
   *Discovered* card named "Danfoss Eco …". Click **Configure**.
4. Choose **Pair automatically**.
5. Walk to the radiator. When the wizard says so, **short-press the button** on the
   thermostat and immediately click **Submit**. If it doesn't catch it, press again
   every ~10 seconds and re-submit — the device only opens a short pairing window.
6. Done. You now have a `climate.<name>` entity plus sensors and settings.

---

## 3. Supported hardware

| | |
|---|---|
| **Devices** | Danfoss Eco, Danfoss Eco 2 (eTRV), e.g. 014G1001. Living Connect and Ally (Zigbee) are **not** this integration — those already have Zigbee support. |
| **Bluetooth address** | Danfoss eTRVs use the OUI `00:04:2F`. |
| **HA Bluetooth** | Any [supported adapter](https://www.home-assistant.io/integrations/bluetooth/#known-working-adapters) **or** an [ESPHome Bluetooth Proxy](https://esphome.io/components/bluetooth_proxy.html). |
| **Batteries** | 2× AA. Danfoss recommends alkaline (not rechargeable — their lower voltage confuses the gauge). |

---

## 4. How the Danfoss Eco works over Bluetooth

Understanding this explains almost every quirk below.

- The eTRV is a **BLE peripheral**. It advertises itself with a name of the form
  `<n>;0:04:2F:XX:YY:ZZ;eTRV`, where the leading digit `<n>` is a small counter/status
  value that changes over time (and bumps when you press the button).
- Its custom GATT service (`10020000-…`) holds characteristics for temperature,
  settings, errors, time, name and the **secret key**. Everything except the standard
  battery level is **encrypted with XXTEA** using a per-device 16-byte key.
- To read that key you must put the device into a short **pairing window** by pressing
  its physical button. While the window is open, the secret-key characteristic becomes
  readable; the app (and this integration) read it once and store it forever. Reading
  it again later is not needed and does not disturb the app's own copy.
- Before any encrypted read/write, the client writes a **PIN** (4 bytes) to an auth
  characteristic. The factory PIN is `0` (shown as `0000`). If you set a PIN in the
  app, you must tell the integration (see [Options](#8-options--configuration)).
- The device is a **deep-sleep power miser.** It is not always connectable; it wakes,
  advertises, and is reachable in bursts. This is why polling is infrequent by design.

### The "Danfoss Eco is slow over BLE" myth

You will read everywhere that these devices are painfully slow — 30 to 90 seconds per
operation. Our own measurements tell a more useful story: that slowness is a **BlueZ
(Linux host) artifact**. Through an **ESP32 Bluetooth proxy** the same device connects
and completes a full state read in **a few seconds**. So: prefer a proxy close to the
radiators, and don't be alarmed by the folklore.

---

## 5. Installation

### HACS (recommended)

1. In HACS, open the three-dot menu → **Custom repositories**.
2. Add `https://github.com/deltasystems-pl/danfoss-eco-ha` with category **Integration**.
3. Search for **Danfoss Eco**, install it.
4. **Restart Home Assistant.**

### Manual

1. Copy the `custom_components/danfoss_eco` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

After restarting, the integration loads automatically and begins Bluetooth discovery.

---

## 6. Pairing — the wizard in detail

The config flow has these steps:

1. **Discovery / selection.** Discovered thermostats show up on the *Devices &
   Services* page. You can also click **Add Integration → Danfoss Eco** to pick from a
   list of nearby eTRVs. No MAC typing.
2. **Pairing method** (menu):
   - **Pair automatically (press the button)** — the normal path.
   - **Enter the secret key manually** — for people migrating from `etrv2mqtt` /
     `libetrv`, or restoring a device whose key they already saved. Paste the 32-hex
     character key.
3. **The button press.** For automatic pairing, the wizard shows an instruction. Walk
   to the radiator, **short-press the thermostat's button**, then click **Submit**
   right away. The integration connects, writes the PIN, and reads the secret key.
   - If the pairing window had already closed you get a friendly error
     ("press the button and submit again"); just press and re-submit. Pressing every
     ~10 seconds while you click is the reliable rhythm.
4. **Naming.** The entry is titled with the device's own stored name (the one you set
   in the Danfoss app, e.g. "Living room"). You can rename it later like any device.

### Why the "keep pressing" advice

The device opens the pairing window for a short time after a press, and the integration
connects on the BLE stack's own schedule. Pressing repeatedly maximises the chance that
a connection attempt lands while the window is open. Once the key is stored, you never
need to press the button again.

---

## 7. Entities reference

Every paired thermostat becomes one **device** with the following entities. Advanced
ones are placed in the **Configuration** and **Diagnostic** sections of the device page;
some are disabled by default (enable them if you want them).

### Climate — `climate.<name>`

The main thermostat.

| Capability | Behaviour |
|---|---|
| **Target temperature** | The setpoint. Writes to the device; respects the device min/max. Step 0.5 °C. |
| **HVAC mode `heat`** | Manual mode — the device holds your setpoint. |
| **HVAC mode `auto`** | Schedule mode — the device follows its on-board weekly program. |
| **Preset `none`** | Manual operation. |
| **Preset `away`** | **Vacation mode** — the device holds its vacation temperature. |
| **Current temperature** | The device's own room-temperature estimate. |
| **HVAC action** | `heating` when room < setpoint, else `idle` (the valve has no direct "% open" readout). |

### Sensors (diagnostic)

| Entity | Meaning |
|---|---|
| `sensor.<name>_battery` | Battery %, from the standard BLE battery characteristic. |
| `sensor.<name>_room_temperature` | Same value as the climate current temperature, as its own sensor for history/automations. |
| `sensor.<name>_bluetooth_signal` | RSSI in dBm. Its `source` attribute tells you **which adapter/proxy** currently hears the device — handy for placing proxies. |
| `sensor.<name>_last_poll` | Timestamp of the last successful full read. If this stops advancing, connections are failing. |
| `sensor.<name>_weekly_schedule` | `programmed` / `not set`. Its attributes list the on-device weekly program per day in plain language (e.g. `mon: 00:00-07:00 away, 07:00-22:00 home, 22:00-24:00 away`). |

### Binary sensor (diagnostic)

| Entity | Meaning |
|---|---|
| `binary_sensor.<name>_problem` | `on` if any device error flag is set. Its attributes break out the individual flags: `e9_valve_does_not_close`, `e10_invalid_time`, `e14_low_battery`, `e15_very_low_battery`. |

The famous **E10 (invalid time)** appears after a battery change, because the clock
resets. This integration fixes it automatically — see [Time sync](#time-sync-button--service).

### Switches (configuration)

These map directly to the "expert settings" in the Danfoss app. All are written into
the device's settings block.

| Entity | App equivalent | Notes |
|---|---|---|
| `switch.<name>_child_lock` | Button lock | Locks the physical buttons on the thermostat. |
| `switch.<name>_adaptive_regulation` | Adaptive/forecast control | Learns your room's heat-up curve to hit the setpoint on time. |
| `switch.<name>_slow_regulation` | Regulation: normal vs slow | Off = normal (faster) regulation, On = slow regulation (quieter, gentler). |
| `switch.<name>_display_flip` | Display orientation | Rotates the display 180°. |
| `switch.<name>_vertical_installation` | Mounting orientation | Disabled by default; enable in the entity settings if you need it. |
| `switch.<name>_valve_installed` | Montage mode | **Disabled by default.** Toggling this re-triggers the device's valve-adaptation routine (the motor drives the valve fully to learn its range). Only touch it during (re)installation. |

### Numbers (configuration)

| Entity | App equivalent | Range |
|---|---|---|
| `number.<name>_minimum_setpoint` | Min temperature | 4–15 °C |
| `number.<name>_maximum_setpoint` | Max temperature | 15–28 °C |
| `number.<name>_frost_protection_temperature` | Ochrona przeciwzamrożeniowa / frost protection | 4–10 °C |
| `number.<name>_vacation_temperature` | Vacation temperature | 4–28 °C |
| `number.<name>_comfort_home_temperature` | Comfort (home) schedule temperature | 4–28 °C |
| `number.<name>_setback_sleep_away_temperature` | Setback (sleep/away) schedule temperature | 4–28 °C |

The last two are the two temperatures the device's **weekly schedule** switches between:
comfort when the program says you're home, setback when it says you're away or asleep.
Together with the manual setpoint and the vacation temperature, these give the same
four-temperature model as the Danfoss app.

### Button (configuration)

| Entity | Meaning |
|---|---|
| `button.<name>_sync_time` | Manually writes the current local time to the device (see below). |
| `button.<name>_refresh_now` | Forces an immediate read of the thermostat instead of waiting for the next poll — handy after a change, or to retry when a device has been out of range. |

---

## 8. Options & configuration

Open the device's integration entry → **Configure**:

| Option | Default | What it does |
|---|---|---|
| **Poll interval (minutes)** | 15 | How often HA reads the device. Lower = fresher data but more battery use and BLE traffic. 10–30 min is sensible. |
| **Device PIN (0 = none)** | 0 | If you set a PIN in the Danfoss app, enter it here. It is written before every read/write. |
| **Automatically sync the device clock** | on | When on, HA writes the correct time whenever the device reports E10 or its clock drifts more than 2 minutes. |

Changing options reloads the entry (a brief reconnect).

### Updating the secret key or PIN (reconfigure)

If a device's key changes (e.g. you re-paired it in the Danfoss app) or you set a PIN
later, you don't need to delete and re-add it. Open the device's integration entry →
the three-dot menu → **Reconfigure**, and update the stored secret key and/or PIN.

### Downloading diagnostics

The entry's three-dot menu → **Download diagnostics** produces a JSON snapshot of the
current state (temperatures, mode, settings, errors, RSSI, schedule) for troubleshooting
or bug reports. **The secret key and Bluetooth address are redacted** so the file is safe
to share.

---

## 9. Services

### `danfoss_eco.sync_time`

Writes the current local time (with UTC offset) to a device. Fixes E10 and keeps the
on-board weekly schedule aligned to real time.

```yaml
action: danfoss_eco.sync_time
data:
  device_id: 1234567890abcdef      # the Danfoss Eco device
```

### `danfoss_eco.set_vacation`

Programs the vacation window and (optionally) the vacation temperature. Combine with
the climate `away` preset to actually enter vacation mode, or the device will switch
automatically when the start time arrives.

```yaml
action: danfoss_eco.set_vacation
data:
  device_id: 1234567890abcdef
  temperature: 16
  start: 2026-12-24 00:00:00
  end: 2027-01-02 00:00:00
```

### `danfoss_eco.set_schedule`

Writes the comfort/setback temperatures and/or the on-device weekly program, so the
thermostat can run **autonomously** (switch `climate` to `auto`/schedule mode to use it).

`days` is a list of **7 lists** (Monday → Sunday). Each inner list holds the
`HH:MM` **transition times** for that day; minutes snap to `:00`/`:30`. The device
starts each day in **setback (away)**, and every transition flips home↔away. So
`['07:00','22:00']` means away 00:00–07:00, home 07:00–22:00, away 22:00–24:00.
An empty list `[]` = setback all day. Up to 6 transitions per day.

```yaml
action: danfoss_eco.set_schedule
data:
  device_id: 1234567890abcdef
  home_temperature: 22
  away_temperature: 18
  days:
    - ["07:00", "22:00"]   # Mon
    - ["07:00", "22:00"]   # Tue
    - ["07:00", "22:00"]   # Wed
    - ["07:00", "22:00"]   # Thu
    - ["07:00", "23:00"]   # Fri
    - ["08:00", "23:00"]   # Sat
    - ["08:00", "22:00"]   # Sun
```

You can also set just the two temperatures via the
`number.<name>_comfort_home_temperature` / `..._setback_sleep_away_temperature`
entities without touching the day program.

---

## 10. Automations & examples

### Night setback for one radiator

```yaml
alias: Bedroom night setback
triggers:
  - trigger: time
    at: "22:30:00"
actions:
  - action: climate.set_temperature
    target:
      entity_id: climate.bedroom
    data:
      temperature: 17
```

### Away when nobody's home, comfort when someone returns

```yaml
alias: Heating follows presence
triggers:
  - trigger: state
    entity_id: group.family
actions:
  - choose:
      - conditions: "{{ trigger.to_state.state == 'not_home' }}"
        sequence:
          - action: climate.set_preset_mode
            target: { entity_id: climate.living_room }
            data: { preset_mode: away }
    default:
      - action: climate.set_preset_mode
        target: { entity_id: climate.living_room }
        data: { preset_mode: none }
```

### Lock the buttons so the kids can't fiddle

```yaml
action: switch.turn_on
target:
  entity_id: switch.living_room_child_lock
```

### Warn on low battery

```yaml
alias: eTRV low battery
triggers:
  - trigger: numeric_state
    entity_id: sensor.bedroom_battery
    below: 15
actions:
  - action: notify.mobile_app
    data:
      message: "Bedroom thermostat battery is low ({{ states('sensor.bedroom_battery') }}%)."
```

---

## 11. How the integration works internally

- **Discovery** is declared in `manifest.json` via Bluetooth `local_name` matchers
  covering `0;0:04:2F*` … `9;0:04:2F*` (the leading digit varies). HA surfaces a
  discovery flow whenever a matching advertisement is seen by any adapter/proxy.
- **The config flow** (`config_flow.py`) handles discovery, the pair/manual menu, the
  button-press step (which calls `EtrvClient.retrieve_secret_key`), and an options flow.
- **A `DataUpdateCoordinator`** (`coordinator.py`) owns one device. On each interval it
  makes **one connection** and reads battery, temperature, settings, errors and time,
  parses them, and (if enabled) syncs the clock. All writes go through the coordinator,
  which re-requests a refresh afterwards, so entities converge on real device state.
- **Entities** are thin `CoordinatorEntity` views over the parsed state. Writes call
  coordinator methods that re-serialize the relevant characteristic and send it.
- **The BLE layer** (`ble.py`) uses HA's `bluetooth` component plus
  `bleak-retry-connector` for robust connects, and uses **short-lived connections**:
  connect → PIN → do the work → disconnect. This suits the device's sleepy nature and
  frees the proxy's limited connection slots between polls.
- **Crypto** (`crypto.py`) is a self-contained pure-Python XXTEA; **payload parsing**
  (`protocol.py`) turns raw bytes into dataclasses and back.

There are **no external Python dependencies** beyond what Home Assistant already ships
(`bleak`, `bleak-retry-connector`) — the XXTEA implementation is bundled, so nothing is
pulled from PyPI at runtime.

---

## 12. The protocol, byte by byte

> For contributors and the curious. Addresses are the custom service `10020000-2749-0001-0000-00805f9b042f`.

### Characteristics

| UUID suffix | Name | Access | Encrypted |
|---|---|---|---|
| `10020001` | PIN | write | no (4-byte big-endian int) |
| `10020003` | Settings | read/write | yes |
| `10020005` | Temperature | read/write | yes |
| `10020006` | Name | read | yes |
| `10020008` | Current time | read/write | yes |
| `10020009` | Errors | read | yes |
| `1002000b` | Secret key | read (only during pairing window) | no |
| `00002a19` (std) | Battery level | read | no |

### Encryption

Each encrypted payload is processed as: **reverse every 4-byte chunk → XXTEA
(decrypt/encrypt, no padding, little-endian words) → reverse every 4-byte chunk again.**
The key is the 16-byte secret read during pairing.

### Temperature payload (8 bytes, decrypted)

- byte 0 = setpoint × 2 (i.e. 0.5 °C steps)
- byte 1 = room temperature × 2
- remaining bytes carry schedule/other state and are preserved on write.

### Settings payload (16 bytes, decrypted, big-endian ints)

| Offset | Field |
|---|---|
| 0 | config bits (see below) |
| 1 | min temperature × 2 |
| 2 | max temperature × 2 |
| 3 | frost-protection temperature × 2 |
| 4 | device mode (0 manual, 1 scheduled, 3 vacation, 5 hold) |
| 5 | vacation temperature × 2 |
| 6–9 | vacation-from (int32, UTC epoch) |
| 10–13 | vacation-to (int32, UTC epoch) |
| 14–15 | padding |

**Config bits (byte 0):**

| Bit | Mask | Meaning |
|---|---|---|
| 0 | 0x01 | adaptable (adaptive) regulation |
| 2 | 0x04 | vertical installation |
| 3 | 0x08 | display flip |
| 4 | 0x10 | slow regulation |
| 6 | 0x40 | valve installed (montage mode) |
| 7 | 0x80 | child lock |

### Errors payload (8 bytes, decrypted)

A uint16 flag field at offset 0: bit 8 = E9 valve doesn't close, bit 9 = E10 invalid
time, bit 13 = E14 low battery, bit 14 = E15 very low battery.

### Time payload (8 bytes, decrypted)

Two big-endian int32: local epoch seconds, then the UTC offset in seconds. The device
stores local time; the integration writes `epoch + offset` and the offset so the device
knows both.

### Schedule payload (44 bytes, decrypted — **newly documented here**)

Prior projects (libetrv, etrv2mqtt, esphome-danfoss-eco) left the schedule
unimplemented. This layout was reverse-engineered against real Eco 2 hardware and is
round-trip tested. The 44-byte struct is split across three encrypted characteristics:

| UUID suffix | Bytes | Contents |
|---|---|---|
| `1002000d` | 20 | `home_temp` (×2), `away_temp` (×2), then days 0–2 |
| `1002000e` | 12 | days 3–4 |
| `1002000f` | 12 | days 5–6 |

Each **day** is 6 bytes: up to six *transition marks* in **half-hour units** (0…48,
where 14 = 07:00, 44 = 22:00; trailing `0x00` = unused). Day 0 is **Monday**. The day
begins in **setback (away)**; each mark toggles home↔away. Concatenate the three
decrypted characteristics to get the full struct; to write, re-split 20/12/12 and
encrypt each part independently.

Example (a real device, comfort 23 °C / setback 21 °C, home 07:00–22:00 every day):

```
2e 2a | 0e2c000000 00 | … (7×)      # 0x2e=46→23.0, 0x2a=42→21.0, 0x0e=14→07:00, 0x2c=44→22:00
```

---

## 13. Bluetooth proxies & range

- **A proxy near the radiators beats a distant adapter.** Aim for RSSI better than about
  **−90 dBm** on `sensor.<name>_bluetooth_signal`; the `source` attribute tells you which
  proxy is in use.
- **ESPHome proxy config:** a standard `bluetooth_proxy` with `active: true` is enough —
  the integration drives the connections itself. Give the ESP enough BLE connection slots
  if it serves several devices (`esp32_ble: { max_connections: N }`).
- **Multiple proxies** are fine and recommended for a whole house; HA automatically uses
  whichever proxy has the best link for each connection.
- The old "proxies can't handle the 30-second GATT timeout" warning does **not** apply
  here in practice — via esp-idf the device is fast (see the myth section).

---

## 14. Building a dashboard

The integration deliberately exposes **primitive entities** (one climate, plus numbers,
switches, sensors) rather than a fixed card, so you can compose whatever dashboard you
like. This section shows one proven layout — a per-floor heating panel with an
essential/advanced split — that you can copy and adapt.

### The idea

Group thermostats by **room or floor** into tabs, show the everyday controls up front,
and hide the expert settings behind a collapsible section so the panel stays clean for
day-to-day use but stays powerful when you need it. The pattern:

- **One card per thermostat** for everyday use: current + target temperature, mode,
  preset, battery.
- **A small diagnostics glance** under each: battery, Bluetooth signal, problem flag.
- **A collapsible "Advanced" block** revealing the configuration entities (min/max,
  frost protection, adaptive/slow regulation, display flip, child lock, vacation temp).

Home Assistant has no native collapsible card, so the advanced block uses the common
`input_boolean` + `conditional` trick.

### Everyday card (built-in `thermostat` card)

```yaml
type: thermostat
entity: climate.living_room
name: Living room
features:
  - type: climate-preset-modes
    style: icons
    preset_modes:
      - none
      - away
```

### Diagnostics glance under it

```yaml
type: glance
columns: 3
entities:
  - entity: sensor.living_room_battery
    name: Battery
  - entity: sensor.living_room_bluetooth_signal
    name: Signal
  - entity: binary_sensor.living_room_problem
    name: Problem
```

### Collapsible "Advanced" block

First create a helper toggle (once): **Settings → Devices & Services → Helpers → Create
Helper → Toggle**, e.g. `input_boolean.living_room_advanced`. Then:

```yaml
type: vertical-stack
cards:
  - type: entities
    entities:
      - entity: input_boolean.living_room_advanced
        name: Advanced settings
    # a compact toggle row acting as the "expander"
  - type: conditional
    conditions:
      - entity: input_boolean.living_room_advanced
        state: "on"
    card:
      type: entities
      title: Advanced — Living room
      entities:
        - entity: number.living_room_minimum_setpoint
        - entity: number.living_room_maximum_setpoint
        - entity: number.living_room_frost_protection_temperature
        - entity: number.living_room_vacation_temperature
        - entity: switch.living_room_adaptive_regulation
        - entity: switch.living_room_slow_regulation
        - entity: switch.living_room_display_flip
        - entity: switch.living_room_child_lock
        - entity: button.living_room_sync_time
```

### Putting a floor together

Wrap several of the above into a **grid** (or the modern `sections` view) so each
thermostat is a tile, and use one **tab per floor**:

```yaml
title: Heating
views:
  - title: Ground floor
    type: sections
    sections:
      - type: grid
        cards:
          - type: heading
            heading: Ground floor thermostats
          # living-room stack (everyday card + glance + advanced) ...
          # kitchen stack ...
  - title: First floor
    type: sections
    sections:
      - type: grid
        cards:
          # bedroom stack ...
```

### Tips

- The **built-in `thermostat` card** already renders the away/comfort presets and the
  min/max the device reports — you rarely need a custom card.
- Prefer the **`sections` view** on recent HA: its grid is responsive on phones, unlike
  the classic `grid` card. If you must use a fixed multi-column desktop layout with
  mobile fallback, the `layout-card` HACS card helps.
- If you like the fancier look, the HACS **`better-thermostat-ui-card`** works with these
  climate entities too (`type: custom:better-thermostat-normal-climate-card`).
- For a house-wide overview, a `glance` or `entities` card listing every
  `climate.*` setpoint and every `sensor.*_battery` makes a good "status at a glance" tab.

---

## 15. Troubleshooting

**The device isn't discovered.**
Check that a Bluetooth adapter/proxy is in range and that the eTRV has batteries.
Confirm HA sees advertisements: *Developer Tools → Actions →
`bluetooth.` … or the Bluetooth integration's diagnostics. The address must start `00:04:2F`.*

**Pairing keeps saying "button was not pressed".**
The pairing window is short. Stand at the device and press its button every ~10 seconds
while you click Submit. If it never works, power-cycle the ESP proxy (a stale BLE cache
can hide the key characteristic) and retry.

**Everything paired but reads fail / `last_poll` stops advancing.**
Usually range or a busy proxy. Move a proxy closer, or raise its `max_connections`.
Check `sensor.<name>_bluetooth_signal`.

**A device stays *unavailable* but still shows a min/max range.**
Those cached values prove it *has* polled successfully before — the current poll is just
failing (range or contention). It will recover on the next successful poll; press
**Refresh now** to retry immediately.

**One device is flaky / drops off while the others are fine.**
That device is your weakest link (farthest from the proxy, or a thick wall in the way).
The eTRV only advertises intermittently, so a weak one is reachable sometimes and not
others. Fixes, in order: (1) **restart the thermostat** (short-press-reset or a battery
out-and-in) to wake its radio; (2) add a **second Bluetooth proxy** closer to it — HA
automatically routes each device to whichever proxy hears it best; (3) move the existing
proxy. Watch `sensor.<name>_bluetooth_signal`; aim for better than −85 dBm.

**Several devices go unavailable when I refresh them all at once.**
Expected. Each Danfoss connection is slow and holds a proxy connection slot for its whole
poll, so firing *N* refreshes simultaneously makes them fight over the proxy and some time
out. Refresh **one at a time**, or just let the scheduled polls run — they are naturally
staggered. If you have many devices on one proxy, raise `esp32_ble: max_connections` in the
proxy firmware and/or add another proxy.

**"not seen by any Bluetooth adapter/proxy" right after restarting Home Assistant.**
Transient. After a restart (or after the proxy reboots) the Bluetooth stack needs a minute
or two to re-register the proxy's *connectable* routes; the first poll in that window fails.
It clears itself on the next poll. (If it persists for many minutes, the proxy connection to
HA is the problem — see the proxy notes.)

**"Refresh now" does something, but calling `homeassistant.update_entity` does nothing.**
Correct — `homeassistant.update_entity` does **not** trigger a fresh device read for this
integration (the entities are coordinator-backed and have no per-entity poll). To force an
immediate read, use the **Refresh now** button, or reload the config entry.

**Don't run the `esphome-danfoss-eco` ESPHome component on the same ESP as your proxy.**
If you previously used the ESPHome `danfoss_eco` component, remove it once you switch to this
integration. Its blocking BLE work can starve the ESP's main loop and take the whole
ESPHome/Bluetooth-proxy connection offline. A device configured as an ESPHome `ble_client`
is also *claimed* by that ESP and cannot be used by this integration at the same time. Use a
plain `bluetooth_proxy` and let this integration do the BLE.

**Writes seem ignored.**
If you set a PIN in the Danfoss app, enter it in **Configure → Device PIN**. A wrong PIN
lets reads through but can make writes silently fail.

**`Problem` sensor is on with `e10_invalid_time`.**
Harmless; the integration will sync the clock on the next poll (keep *Automatically sync
the device clock* on), or press `button.<name>_sync_time`.

**A thermostat already used in the Danfoss app.**
No conflict — app pairing and HA pairing use the same key; both can coexist. You do not
need to factory-reset.

**Slow first poll after restart.**
Normal — the first connect + full read can take ~20 s. Subsequent polls are quick.

### Enabling debug logs

```yaml
logger:
  logs:
    custom_components.danfoss_eco: debug
```

---

## 16. FAQ

**Do I need a Danfoss gateway/hub?** No. Just Bluetooth (adapter or ESPHome proxy).

**Will this break my Danfoss app?** No. The app keeps working; both read the same key.

**Can I use the phone app and HA at the same time?** Yes, though only one BLE client can
be connected at a given instant — they take turns, they don't conflict.

**Does it support the on-device weekly schedule?** Yes — read it (the *Weekly schedule*
sensor's attributes) and write it (the `danfoss_eco.set_schedule` service, plus the
comfort/setback temperature numbers). Switch the climate entity to `auto` to run the
device's program. HA's own scheduling/automations remain available and are more flexible
if you prefer to drive heating from Home Assistant instead.

**How often does it poll?** Every 15 minutes by default; configurable.

**Battery life?** Polling wakes the radio, so extreme poll rates cost battery. The default
is a good balance; alkaline AAs typically last a heating season or more.

**Is my secret key safe?** It's stored in your Home Assistant config entry, like any other
device credential, and never leaves your instance.

**Why do I see the device with all entities "unavailable"?** Setup deliberately succeeds
even if the first read fails (these devices are often briefly unreachable), so you always
get the device page and a working **Refresh now** button. The entities populate on the first
successful poll.

**How many thermostats can one proxy handle?** A handful, but each poll is slow and holds a
connection slot, so they should not all connect at once. For more than ~3 on one proxy,
raise `esp32_ble: max_connections` and/or add a second proxy. HA balances devices across
proxies automatically.

**Do I need to keep the Danfoss app?** Only for things this integration doesn't expose yet
(rare). Day-to-day control, the four temperatures, schedule and settings are all here.

---

## 17. Credits, license & prior art

This integration stands on community reverse-engineering of the eTRV protocol:

- [AdamStrojek/libetrv](https://github.com/AdamStrojek/libetrv) — original Python protocol library (MIT)
- [keton/etrv2mqtt](https://github.com/keton/etrv2mqtt) — MQTT bridge (MIT)
- [dmitry-cherkas/esphome-danfoss-eco](https://github.com/dmitry-cherkas/esphome-danfoss-eco) — ESPHome component (MIT)

XXTEA is the public-domain Corrected Block TEA cipher (Needham & Wheeler). This project is
licensed under the [MIT License](LICENSE). It is a community project and is **not**
affiliated with or endorsed by Danfoss A/S; "Danfoss" and "Danfoss Eco" are trademarks of
their owner and are used here only to describe compatibility.
