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
    UUID_SECRET_KEY,
    UUID_SETTINGS,
    UUID_TEMPERATURE,
)
from .crypto import EtrvCryptoError, etrv_decode, etrv_encode

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 45.0


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
        self._lock = asyncio.Lock()

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

    async def read_state(self) -> dict[str, object]:
        """One connection, full state read (including the weekly schedule).

        The Danfoss Eco is a sleepy battery device, so everything is read in a
        single connection per poll to minimise radio wake-ups. The schedule is
        best-effort: devices that lack those characteristics still return state.
        """
        async with self._lock:
            client = await self._connect()
            try:
                battery = (await self._read(client, UUID_BATTERY, decode=False))[0]
                temperature = await self._read(client, UUID_TEMPERATURE)
                settings = await self._read(client, UUID_SETTINGS)
                errors = await self._read(client, UUID_ERRORS)
                device_time = await self._read(client, UUID_CURRENT_TIME)
                schedule: tuple[bytes, bytes, bytes] | None = None
                try:
                    schedule = (
                        await self._read(client, UUID_SCHEDULE_1),
                        await self._read(client, UUID_SCHEDULE_2),
                        await self._read(client, UUID_SCHEDULE_3),
                    )
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
            finally:
                await client.disconnect()

    async def write_schedule(self, part_d: bytes, part_e: bytes, part_f: bytes) -> None:
        """Write the three schedule characteristics (plaintext in; encrypted out)."""
        async with self._lock:
            client = await self._connect()
            try:
                await self._write(client, UUID_SCHEDULE_1, part_d)
                await self._write(client, UUID_SCHEDULE_2, part_e)
                await self._write(client, UUID_SCHEDULE_3, part_f)
            finally:
                await client.disconnect()

    async def write_char(self, uuid: str, payload: bytes) -> None:
        async with self._lock:
            client = await self._connect()
            try:
                await self._write(client, uuid, payload)
            finally:
                await client.disconnect()

    async def read_name(self) -> str | None:
        from .protocol import parse_name

        async with self._lock:
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
        async with self._lock:
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
