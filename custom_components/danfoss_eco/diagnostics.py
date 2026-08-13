"""Diagnostics for the Danfoss Eco integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import DanfossEcoConfigEntry
from .const import CONF_SECRET_KEY

TO_REDACT = {CONF_SECRET_KEY, "address", "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DanfossEcoConfigEntry
) -> dict[str, Any]:
    # The entry may not be loaded (e.g. setup_retry), so runtime_data can be absent.
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        return {
            "entry": {
                "title": entry.title,
                "state": str(entry.state),
                "data": async_redact_data(dict(entry.data), TO_REDACT),
                "options": dict(entry.options),
            },
            "loaded": False,
        }
    data = coordinator.data
    state: dict[str, Any] = {}
    if data is not None:
        state = {
            "battery": data.battery,
            "room_temperature": data.temperature.room,
            "set_point": data.temperature.set_point,
            "mode": data.settings.mode.name,
            "temperature_min": data.settings.temperature_min,
            "temperature_max": data.settings.temperature_max,
            "frost_protection": data.settings.frost_protection,
            "vacation_temperature": data.settings.vacation_temperature,
            "config_bits": f"{data.settings.config_bits:#010b}",
            "errors": data.errors.flags,
            "rssi": data.rssi,
            "source": data.source,
            "clock_drift_s": data.device_time.drift_seconds,
            "schedule": data.schedule.as_attributes() if data.schedule else None,
        }
    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "last_update_success": coordinator.last_update_success,
        "state": state,
    }
