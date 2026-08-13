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

### Button (configuration)

| Entity | Meaning |
|---|---|
| `button.<name>_sync_time` | Manually writes the current local time to the device (see below). |

---

## 8. Options & configuration

Open the device's integration entry → **Configure**:

| Option | Default | What it does |
|---|---|---|
| **Poll interval (minutes)** | 15 | How often HA reads the device. Lower = fresher data but more battery use and BLE traffic. 10–30 min is sensible. |
| **Device PIN (0 = none)** | 0 | If you set a PIN in the Danfoss app, enter it here. It is written before every read/write. |
| **Automatically sync the device clock** | on | When on, HA writes the correct time whenever the device reports E10 or its clock drifts more than 2 minutes. |

Changing options reloads the entry (a brief reconnect).

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

**Does it support the on-device weekly schedule?** Mode switching (manual/schedule/vacation)
is supported now. Editing the on-device weekly program from HA is planned; meanwhile HA's
own scheduling/automations are more flexible and work today.

**How often does it poll?** Every 15 minutes by default; configurable.

**Battery life?** Polling wakes the radio, so extreme poll rates cost battery. The default
is a good balance; alkaline AAs typically last a heating season or more.

**Is my secret key safe?** It's stored in your Home Assistant config entry, like any other
device credential, and never leaves your instance.

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
