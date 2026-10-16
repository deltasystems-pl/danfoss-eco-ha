"""Tests for the BLE transport's stale service cache handling.

bleak and Home Assistant are stubbed, so this runs without either installed.

Run: python tests/test_ble.py (or python -m pytest tests/).
"""

import asyncio
import importlib.util
import os
import sys
import types

_DIR = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "danfoss_eco"
)


class BleakError(Exception):
    pass


class BleakCharacteristicNotFoundError(BleakError):
    pass


def _stub(name: str, **attrs) -> None:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module


_stub("bleak")
_stub(
    "bleak.exc",
    BleakError=BleakError,
    BleakCharacteristicNotFoundError=BleakCharacteristicNotFoundError,
)
_stub(
    "bleak_retry_connector",
    BleakClientWithServiceCache=object,
    close_stale_connections_by_address=None,
    establish_connection=None,
)
_stub("homeassistant")
_stub("homeassistant.components", bluetooth=None)
_stub("homeassistant.core", HomeAssistant=object)

pkg = types.ModuleType("danfoss_eco")
pkg.__path__ = [_DIR]
sys.modules["danfoss_eco"] = pkg


def _load(mod: str):
    spec = importlib.util.spec_from_file_location(
        f"danfoss_eco.{mod}", os.path.join(_DIR, f"{mod}.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"danfoss_eco.{mod}"] = module
    spec.loader.exec_module(module)
    return module


_load("const")
_load("crypto")
ble = _load("ble")
UUID_ERRORS = sys.modules["danfoss_eco.const"].UUID_ERRORS
KEY = bytes(16)


class FakeClient:
    """Service table without one characteristic, like a stale BlueZ cache."""

    def __init__(self, missing: set[str]):
        self.missing = missing
        self.cache_cleared = False
        self.disconnected = False

    async def read_gatt_char(self, uuid):
        if uuid in self.missing:
            raise BleakCharacteristicNotFoundError(
                f"Characteristic {uuid} was not found!"
            )
        return bytes(8)

    async def write_gatt_char(self, uuid, data, response=True):
        if uuid in self.missing:
            raise BleakCharacteristicNotFoundError(
                f"Characteristic {uuid} was not found!"
            )

    async def clear_cache(self):
        self.cache_cleared = True
        return True

    async def disconnect(self):
        self.disconnected = True


def _read_state(missing: set[str]) -> tuple[FakeClient, Exception | None]:
    client = FakeClient(missing)
    etrv = ble.EtrvClient.__new__(ble.EtrvClient)
    etrv.address = "00:04:2F:00:00:00"
    etrv._key = KEY

    async def connect():
        return client

    etrv._connect = connect
    try:
        asyncio.run(etrv.read_state())
    except ble.EtrvError as err:
        return client, err
    return client, None


def test_missing_characteristic_clears_service_cache():
    client, err = _read_state({UUID_ERRORS})
    assert isinstance(err, ble.EtrvCharacteristicMissing), err
    assert client.cache_cleared
    assert client.disconnected


def test_missing_schedule_keeps_service_cache():
    # The schedule is best-effort; devices without it must not re-discover
    # services on every poll.
    client, err = _read_state({ble.UUID_SCHEDULE_1})
    assert err is None, err
    assert not client.cache_cleared


def test_successful_poll_keeps_service_cache():
    client, err = _read_state(set())
    assert err is None, err
    assert not client.cache_cleared
    assert client.disconnected


def test_missing_pin_characteristic_clears_service_cache():
    # Seen on real hardware: the stale table can lack the PIN characteristic,
    # so the poll fails while connecting, before any read.
    client = FakeClient({ble.UUID_PIN})
    etrv = ble.EtrvClient.__new__(ble.EtrvClient)
    etrv.address = "00:04:2F:00:00:00"
    etrv._key = KEY
    etrv._pin = 0

    async def establish_connection(*args, **kwargs):
        return client

    async def close_stale(address):
        pass

    patched = {
        "bluetooth": types.SimpleNamespace(
            async_ble_device_from_address=lambda *a, **k: object()
        ),
        "establish_connection": establish_connection,
        "close_stale_connections_by_address": close_stale,
    }
    saved = {name: getattr(ble, name) for name in patched}
    etrv._hass = None
    try:
        for name, value in patched.items():
            setattr(ble, name, value)
        asyncio.run(etrv._connect())
    except ble.EtrvCharacteristicMissing:
        pass
    else:
        raise AssertionError("expected EtrvCharacteristicMissing")
    finally:
        for name, value in saved.items():
            setattr(ble, name, value)
    assert client.cache_cleared
    assert client.disconnected


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all good")
