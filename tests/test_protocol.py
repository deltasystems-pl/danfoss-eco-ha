"""Round-trip tests for crypto + protocol using data captured from real devices.

Run: python -m pytest tests/ (or just `python tests/test_protocol.py`).
"""

import importlib.util
import os

_DIR = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "danfoss_eco"
)


def _load(mod: str):
    spec = importlib.util.spec_from_file_location(
        f"danfoss_eco_{mod}", os.path.join(_DIR, f"{mod}.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# const is imported by protocol via relative import; load it under its package name
import sys  # noqa: E402
import types  # noqa: E402

pkg = types.ModuleType("danfoss_eco")
pkg.__path__ = [_DIR]
sys.modules["danfoss_eco"] = pkg

from danfoss_eco.crypto import etrv_decode, etrv_encode  # noqa: E402
from danfoss_eco.protocol import Errors, Settings, Temperature  # noqa: E402

# Jadalnia (00:04:2F:DE:65:8E), key + raw payloads logged by the ESP component
KEY = bytes.fromhex("8d3abffbb017d3537727efe5ee53aee7")
TEMP_RAW = bytes.fromhex("40da871b89cadecc")
SETTINGS_RAW = bytes.fromhex("12cdb3ace694bc1e3a701ca74cac8994")


def test_temperature_decode():
    data = etrv_decode(TEMP_RAW, KEY)
    t = Temperature.parse(data)
    # ESP decoded: room=24.5 target=23.0
    assert t.room == 24.5, t.room
    assert t.set_point == 23.0, t.set_point


def test_settings_decode():
    data = etrv_decode(SETTINGS_RAW, KEY)
    s = Settings.parse(data)
    # ESP decoded: min=19.5 max=24.5 mode=3, frost=6.0, vacation=10.5,
    # adaptable=1 vertical=0 display_flip=0 slow=0 valve=1 lock=1
    assert s.temperature_min == 19.5, s.temperature_min
    assert s.temperature_max == 24.5, s.temperature_max
    assert s.frost_protection == 6.0, s.frost_protection
    assert s.vacation_temperature == 10.5, s.vacation_temperature
    assert s.adaptable_regulation is True
    assert s.vertical_installation is False
    assert s.display_flip is False
    assert s.slow_regulation is False
    assert s.valve_installed is True
    assert s.child_lock is True


def test_crypto_roundtrip():
    data = etrv_decode(SETTINGS_RAW, KEY)
    assert etrv_decode(etrv_encode(data, KEY), KEY) == data


def test_settings_pack_roundtrip():
    data = etrv_decode(SETTINGS_RAW, KEY)
    s = Settings.parse(data)
    # change max temp, re-pack, re-parse
    packed = s.pack(temperature_max=26.0)
    s2 = Settings.parse(packed)
    assert s2.temperature_max == 26.0
    assert s2.temperature_min == s.temperature_min
    assert s2.child_lock is True  # config bits preserved


def test_config_bit_toggle():
    data = etrv_decode(SETTINGS_RAW, KEY)
    s = Settings.parse(data)
    bits = s.config_bits & ~Settings.BIT_CHILD_LOCK  # turn lock off
    s2 = Settings.parse(s.pack(config_bits=bits))
    assert s2.child_lock is False
    assert s2.adaptable_regulation is True  # others intact


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all good")
