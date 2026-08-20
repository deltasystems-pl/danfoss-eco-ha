"""Data update coordinator for a Danfoss Eco device.

Two things make this more than a plain polling coordinator:

* **The last reading is kept.** A radiator valve that is momentarily out of
  reach has not changed its setpoint, its battery level or its weekly program,
  so blanking every entity to "unavailable" throws away information that is
  still true. The cached reading stays on show (with `last_poll` telling the
  user how old it is) until it ages past the configured TTL.
* **Writes are queued, not lost.** Anything the user changes while the device
  is unreachable is coalesced into `PendingWrites`, persisted, and flushed on
  the next successful connection - including one triggered by simply seeing the
  thermostat advertise again.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .ble import EtrvClient, EtrvError
from .const import (
    ADV_RETRY_MIN_INTERVAL_S,
    CONF_AUTO_TIME_SYNC,
    CONF_CACHE_TTL,
    CONF_PIN,
    CONF_POLL_INTERVAL,
    CONF_QUEUE_TTL,
    CONF_SECRET_KEY,
    DEFAULT_AUTO_TIME_SYNC,
    DEFAULT_CACHE_TTL_HOURS,
    DEFAULT_PIN,
    DEFAULT_POLL_INTERVAL_MIN,
    DEFAULT_QUEUE_TTL_HOURS,
    DOMAIN,
    RETRY_BACKOFF_S,
    STORAGE_VERSION,
    UUID_CURRENT_TIME,
    UUID_SCHEDULE_1,
    UUID_SCHEDULE_2,
    UUID_SCHEDULE_3,
    UUID_SETTINGS,
    UUID_TEMPERATURE,
    DeviceMode,
)
from .pending import PendingWrites
from .protocol import DeviceTime, Errors, Schedule, Settings, Temperature

_LOGGER = logging.getLogger(__name__)

# Sync the device clock when it drifts beyond this.
MAX_CLOCK_DRIFT_S = 120
# Some units keep the E10 "invalid time" flag raised even after the clock has
# been written correctly (seen on real hardware: drift 1 s, E10 still set), so
# E10 on its own may only trigger a sync this often. Drift always may.
E10_RESYNC_INTERVAL = timedelta(hours=24)

# Coalescing window for user-initiated writes. Long enough that dragging a
# temperature slider produces one BLE connection, short enough to feel instant.
WRITE_DEBOUNCE_S = 2.0

# Delay before the cache/queue file is written, so a burst of changes is one
# disk write.
SAVE_DELAY_S = 10


@dataclass
class EtrvState:
    """Parsed device state."""

    battery: int
    temperature: Temperature
    settings: Settings
    errors: Errors
    device_time: DeviceTime
    last_poll: datetime
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
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=WRITE_DEBOUNCE_S, immediate=False
            ),
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
        self._cache_ttl_h = entry.options.get(CONF_CACHE_TTL, DEFAULT_CACHE_TTL_HOURS)
        self._queue_ttl_h = entry.options.get(CONF_QUEUE_TTL, DEFAULT_QUEUE_TTL_HOURS)

        self.pending = PendingWrites()
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        # Connection health, surfaced by the "Connection" binary sensor.
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.consecutive_failures = 0
        self.last_seen: datetime | None = None
        self.last_time_sync: datetime | None = None
        self._next_retry = 0.0
        self._retry_unsub: CALLBACK_TYPE | None = None
        self._in_flight: PendingWrites | None = None
        self._polling = False

    # ------------------------------------------------------------- cache ----
    @property
    def cache_valid(self) -> bool:
        """Whether the cached reading may still be shown to the user."""
        if self.data is None:
            return False
        if self.last_update_success:
            return True
        if self._cache_ttl_h <= 0:
            return True
        return dt_util.utcnow() - self.data.last_poll < timedelta(
            hours=self._cache_ttl_h
        )

    @property
    def is_stale(self) -> bool:
        """Showing cached data because the last poll failed."""
        return self.data is not None and not self.last_update_success

    async def async_load_cache(self) -> None:
        """Restore the last reading and any undelivered writes from disk.

        Without this, a Home Assistant restart blanks every thermostat until
        the first poll succeeds - which, for a device this far from its proxy,
        may be a long time - and silently drops writes the user is still
        waiting for.
        """
        stored = await self._store.async_load()
        if not stored:
            return
        self.pending = PendingWrites.from_dict(stored.get("pending"))
        self._expire_pending()
        if (synced := stored.get("last_time_sync")) is not None:
            self.last_time_sync = dt_util.parse_datetime(synced)
        if (state := self._state_from_dict(stored.get("state"))) is not None:
            self.data = state
            self.async_apply_pending(state)
            _LOGGER.debug(
                "%s: restored cached reading from %s", self.address, state.last_poll
            )

    def _state_from_dict(self, raw: dict[str, Any] | None) -> EtrvState | None:
        if not raw:
            return None
        try:
            schedule_hex = raw.get("schedule")
            return EtrvState(
                battery=raw["battery"],
                temperature=Temperature.parse(bytes.fromhex(raw["temperature"])),
                settings=Settings.parse(bytes.fromhex(raw["settings"])),
                errors=Errors.parse(bytes.fromhex(raw["errors"])),
                device_time=DeviceTime.parse(bytes.fromhex(raw["time"])),
                last_poll=dt_util.parse_datetime(raw["last_poll"]) or dt_util.utcnow(),
                rssi=raw.get("rssi"),
                source=raw.get("source"),
                schedule=(
                    Schedule.parse(*(bytes.fromhex(p) for p in schedule_hex))
                    if schedule_hex
                    else None
                ),
            )
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.debug("%s: ignoring unreadable cache: %s", self.address, err)
            return None

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        state: dict[str, Any] | None = None
        if self.data is not None:
            state = {
                "battery": self.data.battery,
                "temperature": self.data.temperature.raw.hex(),
                "settings": self.data.settings.raw.hex(),
                "errors": self.data.errors.raw.hex(),
                "time": self.data.device_time.pack().hex(),
                "last_poll": self.data.last_poll.isoformat(),
                "rssi": self.data.rssi,
                "source": self.data.source,
                "schedule": (
                    [p.hex() for p in self.data.schedule.pack()]
                    if self.data.schedule
                    else None
                ),
            }
        return {
            "state": state,
            "pending": self.pending.as_dict(),
            "last_time_sync": (
                self.last_time_sync.isoformat() if self.last_time_sync else None
            ),
        }

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_S)

    async def async_remove_cache(self) -> None:
        await self._store.async_remove()

    # -------------------------------------------------------------- poll ----
    async def _async_update_data(self) -> EtrvState:
        self._expire_pending()
        self._in_flight = None
        self._polling = True
        try:
            raw = await self.client.read_state(
                build_writes=None if self.pending.is_empty else self._build_writes
            )
        except EtrvError as err:
            self.consecutive_failures += 1
            self.last_error = str(err)
            self._arm_retry()
            raise UpdateFailed(str(err)) from err
        finally:
            self._polling = False

        if self._in_flight is not None:
            if self._in_flight.sync_time:
                self.last_time_sync = dt_util.utcnow()
            self.pending.subtract(self._in_flight)
            self._in_flight = None
        self.consecutive_failures = 0
        self.last_error = None
        self.last_success = dt_util.utcnow()
        self._next_retry = 0.0
        self.async_cancel_retry()

        state = EtrvState(
            battery=raw["battery"],
            temperature=Temperature.parse(raw["temperature"]),
            settings=Settings.parse(raw["settings"]),
            errors=Errors.parse(raw["errors"]),
            device_time=DeviceTime.parse(raw["time"]),
            last_poll=self.last_success,
            rssi=None,
            source=None,
        )
        info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=False
        )
        if info:
            state.rssi = info.rssi
            state.source = info.source

        parts = raw.get("schedule")
        if parts:
            try:
                state.schedule = Schedule.parse(*parts)
            except Exception as err:  # noqa: BLE001 - malformed payload, keep polling
                _LOGGER.debug("%s: schedule parse failed: %s", self.address, err)

        if self._auto_time_sync and self._needs_clock_sync(state):
            _LOGGER.info(
                "%s: queueing device clock sync (drift %s s, e10=%s)",
                self.address,
                state.device_time.drift_seconds,
                state.errors.flags.get("e10_invalid_time"),
            )
            self.pending.queue_sync_time()

        # Anything queued while this connection was open (or that the device
        # refused) still describes what the user wants to see.
        self.async_apply_pending(state)
        self._schedule_save()
        return state

    def _needs_clock_sync(self, state: EtrvState) -> bool:
        if state.device_time.drift_seconds > MAX_CLOCK_DRIFT_S:
            return True
        if not state.errors.flags.get("e10_invalid_time"):
            return False
        # E10 with a correct clock means the device is not clearing the flag;
        # writing the time again every poll would queue a write forever.
        return (
            self.last_time_sync is None
            or dt_util.utcnow() - self.last_time_sync > E10_RESYNC_INTERVAL
        )

    # ------------------------------------------------------ queue flushing --
    @callback
    def _build_writes(self, raw: dict[str, Any]) -> list[tuple[str, bytes]]:
        """Turn the queue into GATT writes against the just-read device state.

        Called from inside the poll connection, so the settings block is
        modified from what the thermostat holds right now - a queue entry made
        hours ago must not resurrect stale neighbouring fields.
        """
        try:
            return self._writes_for(raw)
        except Exception:  # noqa: BLE001 - a bad queue entry must not wedge polling
            _LOGGER.exception(
                "%s: could not build queued writes - discarding them", self.address
            )
            self.pending.clear()
            self._in_flight = None
            self._schedule_save()
            return []

    def _writes_for(self, raw: dict[str, Any]) -> list[tuple[str, bytes]]:
        snapshot = self.pending.snapshot()
        self._in_flight = snapshot
        temperature = Temperature.parse(raw["temperature"])
        settings = Settings.parse(raw["settings"])

        ops: list[tuple[str, bytes]] = []
        if snapshot.sync_time:
            ops.append((UUID_CURRENT_TIME, DeviceTime.now().pack()))

        changes: dict[str, Any] = {}
        for key, value in snapshot.settings.items():
            changes[key] = DeviceMode(int(value)) if key == "mode" else value
        if snapshot.config_bits_on or snapshot.config_bits_off:
            changes["config_bits"] = (
                settings.config_bits | snapshot.config_bits_on
            ) & ~snapshot.config_bits_off
        if changes:
            ops.append((UUID_SETTINGS, settings.pack(**changes)))

        if snapshot.set_point is not None:
            ops.append(
                (UUID_TEMPERATURE, temperature.with_set_point(snapshot.set_point))
            )

        if snapshot.touches_schedule:
            parts = raw.get("schedule")
            if not parts:
                _LOGGER.warning(
                    "%s: dropping queued schedule change - this device does not "
                    "expose the schedule characteristics",
                    self.address,
                )
                self.pending.clear_schedule()
                snapshot.clear_schedule()
            else:
                schedule = Schedule.parse(*parts)
                if snapshot.schedule_home is not None:
                    schedule.home_temperature = snapshot.schedule_home
                if snapshot.schedule_away is not None:
                    schedule.away_temperature = snapshot.schedule_away
                if snapshot.schedule_days is not None:
                    for idx, marks in enumerate(snapshot.schedule_days):
                        if marks is not None:
                            schedule.days[idx] = list(marks)
                part_d, part_e, part_f = schedule.pack()
                ops += [
                    (UUID_SCHEDULE_1, part_d),
                    (UUID_SCHEDULE_2, part_e),
                    (UUID_SCHEDULE_3, part_f),
                ]
        return ops

    def _expire_pending(self) -> None:
        """Forget writes the device never came back to collect."""
        if self._queue_ttl_h <= 0 or self.pending.is_empty:
            return
        age = self.pending.age_seconds
        if age is not None and age > self._queue_ttl_h * 3600:
            _LOGGER.warning(
                "%s: discarding %d queued change(s) after %.1f h unreachable",
                self.address,
                self.pending.count,
                age / 3600,
            )
            self.pending.clear()
            self._schedule_save()

    @callback
    def async_apply_pending(self, state: EtrvState | None = None) -> None:
        """Overlay queued changes on the state entities read from.

        The user asked for 22 °C; showing them 21 °C until the valve is next
        reachable would look like the command was ignored.
        """
        state = state or self.data
        if state is None or self.pending.is_empty:
            return
        if self.pending.set_point is not None:
            state.temperature.set_point = self.pending.set_point
        for key, value in self.pending.settings.items():
            if key == "mode":
                state.settings.mode = DeviceMode(int(value))
            elif hasattr(state.settings, key):
                setattr(state.settings, key, value)
        if self.pending.config_bits_on or self.pending.config_bits_off:
            state.settings.config_bits = (
                state.settings.config_bits | self.pending.config_bits_on
            ) & ~self.pending.config_bits_off
        if state.schedule is not None:
            if self.pending.schedule_home is not None:
                state.schedule.home_temperature = self.pending.schedule_home
            if self.pending.schedule_away is not None:
                state.schedule.away_temperature = self.pending.schedule_away
            if self.pending.schedule_days is not None:
                for idx, marks in enumerate(self.pending.schedule_days):
                    if marks is not None:
                        state.schedule.days[idx] = list(marks)

    async def _async_queued(self) -> None:
        """Common tail of every write: show it, save it, try to deliver it."""
        self.async_apply_pending()
        self.async_update_listeners()
        self._schedule_save()
        await self.async_request_refresh()

    @callback
    def async_discard_pending(self) -> None:
        """Drop undelivered writes (user-initiated)."""
        if self.pending.is_empty:
            return
        _LOGGER.info("%s: discarding %d queued change(s)", self.address, self.pending.count)
        self.pending.clear()
        self._schedule_save()
        self.async_update_listeners()

    # ---------------------------------------------------- retry on sighting --
    @callback
    def async_device_seen(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """An advertisement arrived - the thermostat is back within range.

        This is what turns "queued" into "delivered" without waiting out the
        full poll interval: the moment a proxy hears the valve again, retry.
        """
        self.last_seen = dt_util.utcnow()
        if self._polling:
            return
        if self.last_update_success and self.pending.is_empty:
            return
        now = self.hass.loop.time()
        if now < self._next_retry:
            return
        self._next_retry = now + ADV_RETRY_MIN_INTERVAL_S
        _LOGGER.debug(
            "%s: seen via %s, retrying (%d queued)",
            self.address,
            service_info.source,
            self.pending.count,
        )
        self.config_entry.async_create_background_task(
            self.hass, self.async_refresh(), f"{DOMAIN} retry {self.address}"
        )

    def _arm_retry(self) -> None:
        """Back off after a failure, but stay far quicker than the poll interval.

        Advertisements alone are not enough to lean on: an eTRV that has drifted
        out of range can stay silent for many minutes, so a plain timer carries
        the recovery and the advertisement callback only makes it faster when a
        sighting does happen.
        """
        idx = min(self.consecutive_failures - 1, len(RETRY_BACKOFF_S) - 1)
        delay = RETRY_BACKOFF_S[idx]
        self._next_retry = self.hass.loop.time() + delay
        self.async_cancel_retry()
        self._retry_unsub = async_call_later(self.hass, delay, self._async_retry)

    @callback
    def async_cancel_retry(self) -> None:
        if self._retry_unsub is not None:
            self._retry_unsub()
            self._retry_unsub = None

    @callback
    def _async_retry(self, _now: datetime) -> None:
        self._retry_unsub = None
        if self.last_update_success and self.pending.is_empty:
            return
        self.config_entry.async_create_background_task(
            self.hass, self.async_refresh(), f"{DOMAIN} retry {self.address}"
        )

    # ------------------------------------------------------------- writes --
    async def async_set_temperature(self, value: float) -> None:
        self.pending.queue_set_point(value)
        await self._async_queued()

    async def async_set_mode(self, mode: DeviceMode) -> None:
        self.pending.queue_mode(mode)
        await self._async_queued()

    async def async_set_vacation(
        self, temperature: float | None, start: int, end: int
    ) -> None:
        changes: dict[str, Any] = {"vacation_from": start, "vacation_to": end}
        if temperature is not None:
            changes["vacation_temperature"] = temperature
        self.pending.queue_settings(**changes)
        await self._async_queued()

    async def async_update_settings(self, **changes: Any) -> None:
        """Queue settings-block changes by dataclass-field name."""
        self.pending.queue_settings(**changes)
        await self._async_queued()

    async def async_set_config_bit(self, mask: int, state: bool) -> None:
        """Set/clear a bit in the settings config byte (e.g. child lock)."""
        self.pending.queue_config_bit(mask, state)
        await self._async_queued()

    async def async_set_schedule_temps(
        self, home: float | None = None, away: float | None = None
    ) -> None:
        """Update the comfort (home) and/or setback (away) schedule temperatures."""
        self.pending.queue_schedule_temps(home=home, away=away)
        await self._async_queued()

    async def async_set_schedule_days(self, days: list[list[int] | None]) -> None:
        """Queue a weekly program; None entries leave that day untouched."""
        self.pending.queue_schedule_days(days)
        await self._async_queued()

    async def sync_time(self) -> None:
        self.pending.queue_sync_time()
        await self._async_queued()
