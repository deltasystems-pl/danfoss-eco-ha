"""Danfoss Eco (eTRV) Bluetooth thermostat integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util

from .ble import EtrvError
from .const import DOMAIN
from .coordinator import EtrvCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SET_VACATION = "set_vacation"
SERVICE_SYNC_TIME = "sync_time"
SERVICE_SET_SCHEDULE = "set_schedule"

_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Required("start"): cv.datetime,
        vol.Required("end"): cv.datetime,
    }
)

_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("home_temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=4, max=28)
        ),
        vol.Optional("away_temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=4, max=28)
        ),
        vol.Optional("days"): vol.All(
            cv.ensure_list, [vol.All(cv.ensure_list, [cv.string])]
        ),
    }
)


def _hhmm_to_mark(value: str) -> int:
    """'HH:MM' -> half-hour mark (0..48). Minutes snap to 0/30."""
    h, _, m = str(value).partition(":")
    mark = int(h) * 2 + (1 if int(m or 0) >= 30 else 0)
    return max(0, min(48, mark))


type DanfossEcoConfigEntry = ConfigEntry[EtrvCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DanfossEcoConfigEntry) -> bool:
    coordinator = EtrvCoordinator(hass, entry)
    entry.runtime_data = coordinator
    # Bring back the last reading and any undelivered writes before the first
    # poll, so a restart doesn't blank the dashboard or drop commands.
    await coordinator.async_load_cache()
    # These are weak-signal, deep-sleeping BLE devices, so the first read may
    # fail simply because the thermostat is momentarily unreachable. Don't block
    # setup on it: create the entities (they show the cached reading, or
    # "unavailable" if there is none) so the user always has the device page and
    # can hit "Refresh now". The coordinator keeps retrying on its own too.
    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # A thermostat that starts advertising again is the earliest signal that it
    # is reachable - use it to retry immediately instead of waiting out the poll
    # interval, which is what actually delivers queued commands "when it comes
    # back near a proxy".
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator.async_device_seen,
            {"address": coordinator.address, "connectable": True},
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(coordinator.async_cancel_retry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DanfossEcoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: DanfossEcoConfigEntry) -> None:
    """Drop the cached reading / pending writes when the device is removed."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None:
        await coordinator.async_remove_cache()


def _coordinator_for_device(hass: HomeAssistant, device_id: str) -> EtrvCoordinator:
    dev = dr.async_get(hass).async_get(device_id)
    if not dev:
        raise EtrvError(f"Unknown device_id {device_id}")
    for entry_id in dev.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and entry.domain == DOMAIN and hasattr(entry, "runtime_data"):
            return entry.runtime_data
    raise EtrvError(f"Device {device_id} is not a Danfoss Eco")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_TIME):
        return

    async def _sync_time(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data["device_id"])
        await coordinator.sync_time()

    async def _set_vacation(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data["device_id"])
        start = int(dt_util.as_timestamp(call.data["start"]))
        end = int(dt_util.as_timestamp(call.data["end"]))
        await coordinator.async_set_vacation(
            call.data.get("temperature"), start, end
        )

    async def _set_schedule(call: ServiceCall) -> None:
        coordinator = _coordinator_for_device(hass, call.data["device_id"])
        if "home_temperature" in call.data or "away_temperature" in call.data:
            await coordinator.async_set_schedule_temps(
                home=call.data.get("home_temperature"),
                away=call.data.get("away_temperature"),
            )
        days_in = call.data.get("days")
        if days_in is not None:
            # days: list of up to 7 lists of "HH:MM" transition strings (home
            # starts after the first mark; before it the device is in setback).
            # Days not listed stay as the thermostat has them.
            days: list[list[int] | None] = [None] * 7
            for idx, marks in enumerate(days_in[:7]):
                days[idx] = sorted(_hhmm_to_mark(m) for m in marks)
            await coordinator.async_set_schedule_days(days)

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, _set_schedule, schema=_SCHEDULE_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_TIME,
        _sync_time,
        schema=vol.Schema({vol.Required("device_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_VACATION, _set_vacation, schema=_VACATION_SCHEMA
    )
