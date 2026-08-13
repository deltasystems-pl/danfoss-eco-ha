"""Data update coordinator for a Danfoss Eco device."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .ble import EtrvClient, EtrvError
from .const import (
    CONF_AUTO_TIME_SYNC,
    CONF_PIN,
    CONF_POLL_INTERVAL,
    CONF_SECRET_KEY,
    DEFAULT_AUTO_TIME_SYNC,
    DEFAULT_PIN,
    DEFAULT_POLL_INTERVAL_MIN,
    DOMAIN,
    UUID_CURRENT_TIME,
    UUID_SETTINGS,
    UUID_TEMPERATURE,
    DeviceMode,
)
from .protocol import DeviceTime, Errors, Schedule, Settings, Temperature

_LOGGER = logging.getLogger(__name__)

# Sync the device clock when it drifts beyond this (or E10 is flagged).
MAX_CLOCK_DRIFT_S = 120


@dataclass
class EtrvState:
    """Parsed device state."""

    battery: int
    temperature: Temperature
    settings: Settings
    errors: Errors
    device_time: DeviceTime
    last_poll: object  # datetime
    rssi: int | None
    source: str | None
    schedule: Schedule | None = None


class EtrvCoordinator(DataUpdateCoordinator[EtrvState]):
    """Polls one eTRV and funnels writes through one place."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        poll_min = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_MIN)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.title}",
            config_entry=entry,
            update_interval=timedelta(minutes=poll_min),
        )
        self.address: str = entry.data["address"]
        self.client = EtrvClient(
            hass,
            self.address,
            bytes.fromhex(entry.data[CONF_SECRET_KEY]),
            entry.options.get(CONF_PIN, entry.data.get(CONF_PIN, DEFAULT_PIN)),
        )
        self._auto_time_sync = entry.options.get(
            CONF_AUTO_TIME_SYNC, DEFAULT_AUTO_TIME_SYNC
        )

    async def _async_update_data(self) -> EtrvState:
        try:
            raw = await self.client.read_state()
        except EtrvError as err:
            raise UpdateFailed(str(err)) from err

        state = EtrvState(
            battery=raw["battery"],
            temperature=Temperature.parse(raw["temperature"]),
            settings=Settings.parse(raw["settings"]),
            errors=Errors.parse(raw["errors"]),
            device_time=DeviceTime.parse(raw["time"]),
            last_poll=dt_util.utcnow(),
            rssi=None,
            source=None,
        )
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=False)
        if info:
            state.rssi = info.rssi
            state.source = info.source

        try:
            parts = await self.client.read_schedule()
            state.schedule = Schedule.parse(*parts)
        except EtrvError as err:
            _LOGGER.debug("%s: schedule read failed: %s", self.address, err)

        if self._auto_time_sync and (
            state.errors.flags.get("e10_invalid_time")
            or state.device_time.drift_seconds > MAX_CLOCK_DRIFT_S
        ):
            _LOGGER.info(
                "%s: syncing device clock (drift %s s, e10=%s)",
                self.address,
                state.device_time.drift_seconds,
                state.errors.flags.get("e10_invalid_time"),
            )
            try:
                await self.sync_time()
            except EtrvError as err:
                _LOGGER.warning("%s: time sync failed: %s", self.address, err)

        return state

    # ------------------------------------------------------------- writes --
    async def async_set_temperature(self, value: float) -> None:
        if self.data is None:
            raise UpdateFailed("No state yet")
        payload = self.data.temperature.with_set_point(value)
        await self.client.write_char(UUID_TEMPERATURE, payload)
        self.data.temperature.set_point = value
        self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_mode(self, mode: DeviceMode) -> None:
        if self.data is None:
            raise UpdateFailed("No state yet")
        await self.client.write_char(UUID_SETTINGS, self.data.settings.pack(mode=mode))
        self.data.settings.mode = mode
        self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_vacation(
        self, temperature: float | None, start: int, end: int
    ) -> None:
        if self.data is None:
            raise UpdateFailed("No state yet")
        changes: dict[str, object] = {"vacation_from": start, "vacation_to": end}
        if temperature is not None:
            changes["vacation_temperature"] = temperature
        await self.client.write_char(
            UUID_SETTINGS, self.data.settings.pack(**changes)
        )
        await self.async_request_refresh()

    async def async_update_settings(self, **changes: object) -> None:
        """Write the settings block with dataclass-field overrides."""
        if self.data is None:
            raise UpdateFailed("No state yet")
        await self.client.write_char(
            UUID_SETTINGS, self.data.settings.pack(**changes)
        )
        await self.async_request_refresh()

    async def async_set_config_bit(self, mask: int, state: bool) -> None:
        """Set/clear a bit in the settings config byte (e.g. child lock)."""
        if self.data is None:
            raise UpdateFailed("No state yet")
        bits = self.data.settings.config_bits
        bits = bits | mask if state else bits & ~mask
        await self.client.write_char(
            UUID_SETTINGS, self.data.settings.pack(config_bits=bits)
        )
        self.data.settings.config_bits = bits
        self.async_update_listeners()
        await self.async_request_refresh()

    async def async_set_schedule_temps(
        self, home: float | None = None, away: float | None = None
    ) -> None:
        """Update the comfort (home) and/or setback (away) schedule temperatures."""
        if self.data is None or self.data.schedule is None:
            raise UpdateFailed("No schedule loaded yet")
        sched = self.data.schedule
        if home is not None:
            sched.home_temperature = home
        if away is not None:
            sched.away_temperature = away
        await self.client.write_schedule(*sched.pack())
        await self.async_request_refresh()

    async def async_set_schedule(self, schedule: Schedule) -> None:
        """Write a full weekly schedule."""
        await self.client.write_schedule(*schedule.pack())
        await self.async_request_refresh()

    async def sync_time(self) -> None:
        await self.client.write_char(UUID_CURRENT_TIME, DeviceTime.now().pack())
