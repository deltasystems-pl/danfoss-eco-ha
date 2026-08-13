<p align="center">
  <img src="custom_components/danfoss_eco/brand/logo.png" alt="Danfoss Eco for Home Assistant" width="420">
</p>

<h1 align="center">Danfoss Eco for Home Assistant</h1>

<p align="center">
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
  <a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2025.6%2B-41BDF5.svg" alt="Home Assistant"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/iot__class-local__polling-blue.svg" alt="iot_class: local_polling">
  <img src="https://img.shields.io/github/v/release/deltasystems-pl/danfoss-eco-ha" alt="Release">
</p>

Control **Danfoss Eco / Eco 2 (eTRV)** Bluetooth radiator thermostats (e.g. 014G1001)
natively from Home Assistant — with a **guided pairing wizard** that needs no MAC
addresses, no hex keys and no command-line tools.

## Features

- 🔍 **Automatic discovery** — thermostats in Bluetooth range pop up in
  *Settings → Devices & Services*, like any modern integration
- 🪄 **Guided pairing** — the wizard tells you when to press the timer button;
  the secret key is read from the device automatically and stored in the config entry
- 🌡️ **Climate entity** — setpoint, manual/schedule mode, vacation preset,
  device min/max limits respected
- 🎛️ **All the app's expert settings** — min/max temperature, frost protection,
  vacation temperature, adaptive regulation, slow regulation, display flip, mounting
  orientation, montage mode and **button (child) lock**, as native number/switch entities
- 🕐 **Automatic time sync** — the device clock is corrected whenever it drifts or
  flags `E10 INVALID TIME` (e.g. after a battery swap); manual *Sync time* button
  and `danfoss_eco.sync_time` service included
- 🏖️ **Vacation mode** — `danfoss_eco.set_vacation` service programs the period
  and temperature; shows up as the *Away* preset
- 📊 **Diagnostics** — battery, room temperature, Bluetooth signal (RSSI + which
  adapter/proxy hears the device), last-poll timestamp, and a *Problem* sensor that
  decodes the device error flags (E9 valve, E10 time, E14/E15 battery)
- 🔑 **Manual key entry** — optional path for migrating from etrv2mqtt / libetrv
- 📡 **Works over ESPHome Bluetooth proxies** — no adapter on the HA host needed

## 📖 Full documentation

**[Read the complete documentation → DOCUMENTATION.md](DOCUMENTATION.md)** — a thorough
guide covering every entity, option and service, how the device and protocol work, how
to build a dashboard, Bluetooth-proxy placement, troubleshooting and an FAQ.

### A note on speed

The Danfoss Eco has a reputation for being painfully slow over BLE (60–90 s
operations). Our measurements show that is a **BlueZ artifact**: through an
ESP32-based Bluetooth proxy the same device connects and completes a full state
read in a few seconds. A close proxy (RSSI better than about −90 dBm) gives the
best experience.

## Installation

### HACS (recommended)

1. HACS → *Custom repositories* → add `deltasystems-pl/danfoss-eco-ha` (Integration)
2. Install **Danfoss Eco**, restart Home Assistant

### Manual

Copy `custom_components/danfoss_eco` into your `config/custom_components/` and restart.

## Pairing a thermostat

1. *Settings → Devices & Services* — discovered thermostats appear automatically
   (or *Add integration → Danfoss Eco*)
2. Walk to the radiator
3. When the wizard asks, **short-press the timer (clock) button** on the thermostat
   and click *Submit* right away — press again every ~10 s if it retries;
   the pairing window the device opens is short
4. Done — the device name you set in the Danfoss app becomes the entity name

Already have a key (from `etrv2mqtt` / `libetrv`)? Use the *manual key* step.

> Pairing with Home Assistant does **not** break the Danfoss mobile-app pairing —
> both use the same key.

## Credits

Protocol knowledge builds on the MIT-licensed pioneering work of
[AdamStrojek/libetrv](https://github.com/AdamStrojek/libetrv),
[keton/etrv2mqtt](https://github.com/keton/etrv2mqtt) and
[dmitry-cherkas/esphome-danfoss-eco](https://github.com/dmitry-cherkas/esphome-danfoss-eco).
XXTEA is the public-domain Corrected Block TEA cipher by Needham & Wheeler.

## License

[MIT](LICENSE)
