"""BLE transport for Danfoss Eco eTRV devices.

Uses Home Assistant's bluetooth stack, so it works with local adapters and
ESPHome Bluetooth proxies alike. Measured on real Eco 2 units (2026-08):
connect + service discovery ~3 s, characteristic reads <1 s - comfortably
inside proxy GATT limits despite the device's slow-BLE reputation (which
stems from BlueZ hosts).
"""

from __future__ import annotations

import asyncio
import logging
import struct
from collections.abc import Callable

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    close_stale_connections_by_address,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import (
    SECRET_KEY_LENGTH,
    UUID_BATTERY,
    UUID_CURRENT_TIME,
    UUID_ERRORS,
    UUID_NAME,
    UUID_PIN,
    UUID_SCHEDULE_1,
    UUID_SCHEDULE_2,
    UUID_SCHEDULE_3,
    UUID_SECRET_KEY,
    UUID_SETTINGS,
    UUID_TEMPERATURE,
)
from .crypto import EtrvCryptoError, etrv_decode, etrv_encode

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 45.0

# All eTRVs in a home usually share one Bluetooth proxy, and a proxy has very
# few connection slots. Letting three thermostats dial out at the same time is
# the fastest way to produce "no backend with an available connection slot", so
# every connection this integration makes is serialized process-wide.
_BLE_LOCK = asyncio.Lock()

# After a write, re-read the characteristic we touched so the entity shows the
# value the device actually accepted rather than the value we hoped for.
_REREAD_KEYS = {
    UUID_TEMPERATURE: "temperature",
    UUID_SETTINGS: "settings",
    UUID_CURRENT_TIME: "time",
}
_SCHEDULE_UUIDS = (UUID_SCHEDULE_1, UUID_SCHEDULE_2, UUID_SCHEDULE_3)

# Give the valve a moment to commit a write before reading it back.
WRITE_SETTLE_S = 0.5


class EtrvError(Exception):
    """Communication failure."""


class EtrvNotFoundError(EtrvError):
    """No connectable BLEDevice available."""


class EtrvButtonNotPressed(EtrvError):
    """Secret-key characteristic absent - pairing button was not pressed."""


class EtrvClient:
    """Short-lived-connection client for one eTRV."""

    def __init__(
        self, hass: HomeAssistant, address: str, secret_key: bytes | None, pin: int = 0
    ) -> None:
        self._hass = hass
        self.address = address
        self._key = secret_key
        self._pin = pin

    async def _connect(self) -> BleakClientWithServiceCache:
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, self.address, connectable=True
        )
        if ble_device is None:
            raise EtrvNotFoundError(
                f"{self.address} is not seen by any Bluetooth adapter/proxy"
            )
        try:
            await close_stale_connections_by_address(self.address)
        except Exception:  # noqa: BLE001 - best effort
            pass
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.address,
                max_attempts=2,
            )
        except (BleakError, TimeoutError) as err:
            raise EtrvError(f"Cannot connect to {self.address}: {err}") from err
        try:
            pin_bytes = struct.pack(">I", self._pin)
            await client.write_gatt_char(UUID_PIN, pin_bytes, response=True)
        except BleakError as err:
            await client.disconnect()
            raise EtrvError(f"PIN write failed: {err}") from err
        return client

    async def _read(self, client, uuid: str, *, decode: bool = True) -> bytes:
        try:
            data = bytes(await client.read_gatt_char(uuid))
        except BleakError as err:
            raise EtrvError(f"Read {uuid[4:8]} failed: {err}") from err
        if not decode:
            return data
        if self._key is None:
            raise EtrvError("Secret key not configured")
        try:
            return etrv_decode(data, self._key)
        except EtrvCryptoError as err:
            raise EtrvError(str(err)) from err

    async def _write(self, client, uuid: str, payload: bytes) -> None:
        if self._key is None:
            raise EtrvError("Secret key not configured")
        try:
            await client.write_gatt_char(
                uuid, etrv_encode(payload, self._key), response=True
            )
        except BleakError as err:
            raise EtrvError(f"Write {uuid[4:8]} failed: {err}") from err

    async def _read_all(self, client) -> dict[str, object]:
        """Read every characteristic we care about over an open connection."""
        battery = (await self._read(client, UUID_BATTERY, decode=False))[0]
        temperature = await self._read(client, UUID_TEMPERATURE)
        settings = await self._read(client, UUID_SETTINGS)
        errors = await self._read(client, UUID_ERRORS)
        device_time = await self._read(client, UUID_CURRENT_TIME)
        schedule: tuple[bytes, bytes, bytes] | None = None
        try:
            schedule = await self._read_schedule(client)
        except EtrvError as err:
            _LOGGER.debug("%s: schedule read skipped: %s", self.address, err)
        return {
            "battery": battery,
            "temperature": temperature,
            "settings": settings,
            "errors": errors,
            "time": device_time,
            "schedule": schedule,
        }

    async def _read_schedule(self, client) -> tuple[bytes, bytes, bytes]:
        return (
            await self._read(client, UUID_SCHEDULE_1),
            await self._read(client, UUID_SCHEDULE_2),
            await self._read(client, UUID_SCHEDULE_3),
        )

    async def read_state(
        self,
        build_writes: Callable[[dict[str, object]], list[tuple[str, bytes]]] | None = None,
    ) -> dict[str, object]:
        """One connection: full state read, plus any queued writes.

        The Danfoss Eco is a sleepy battery device, so everything happens in a
        single connection per poll to minimise radio wake-ups. `build_writes`
        gets the freshly read payloads and returns the writes to perform - the
        settings block is a read-modify-write, so queued changes must be
        applied to what the device holds *now*, not to a cached copy that may
        be hours old.

        The schedule is best-effort: devices that lack those characteristics
        still return state.
        """
        async with _BLE_LOCK:
            client = await self._connect()
            try:
                raw = await self._read_all(client)
                if build_writes is None:
                    return raw
                ops = build_writes(raw)
                if not ops:
                    return raw
                written: set[str] = set()
                for uuid, payload in ops:
                    await self._write(client, uuid, payload)
                    written.add(uuid)
                _LOGGER.debug("%s: flushed %d queued write(s)", self.address, len(ops))
                await asyncio.sleep(WRITE_SETTLE_S)
                for uuid in written:
                    if (key := _REREAD_KEYS.get(uuid)) is not None:
                        raw[key] = await self._read(client, uuid)
                if written.intersection(_SCHEDULE_UUIDS):
                    raw["schedule"] = await self._read_schedule(client)
                return raw
            finally:
                await client.disconnect()

    async def read_name(self) -> str | None:
        from .protocol import parse_name

        async with _BLE_LOCK:
            client = await self._connect()
            try:
                return parse_name(await self._read(client, UUID_NAME))
            except EtrvError:
                return None
            finally:
                await client.disconnect()

    async def retrieve_secret_key(self) -> bytes:
        """Read the secret key. The pairing button must have been pressed.

        The key characteristic only appears in the GATT table while the
        pairing window is open, so callers should instruct the user to press
        the timer button right before/while this runs.
        """
        async with _BLE_LOCK:
            client = await self._connect()
            try:
                char = client.services.get_characteristic(UUID_SECRET_KEY)
                if char is None:
                    # A cached (stale) service table can hide the key char -
                    # drop the cache so the next attempt re-discovers.
                    try:
                        await client.clear_cache()
                    except Exception:  # noqa: BLE001
                        pass
                    raise EtrvButtonNotPressed(
                        "Pairing window closed - key characteristic not present"
                    )
                data = bytes(await client.read_gatt_char(UUID_SECRET_KEY))
                if len(data) < SECRET_KEY_LENGTH:
                    raise EtrvError(f"Short secret key: {len(data)} bytes")
                key = data[:SECRET_KEY_LENGTH]
                self._key = key
                return key
            except BleakError as err:
                raise EtrvError(f"Secret key read failed: {err}") from err
            finally:
                await client.disconnect()
