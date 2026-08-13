"""Danfoss Eco (eTRV) Bluetooth thermostat integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
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

_VACATION_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Required("start"): cv.datetime,
        vol.Required("end"): cv.datetime,
    }
)


type DanfossEcoConfigEntry = ConfigEntry[EtrvCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DanfossEcoConfigEntry) -> bool:
    coordinator = EtrvCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DanfossEcoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_TIME,
        _sync_time,
        schema=vol.Schema({vol.Required("device_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_VACATION, _set_vacation, schema=_VACATION_SCHEMA
    )
