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
from danfoss_eco.protocol import Errors, Schedule, Settings, Temperature  # noqa: E402

# TV (00:04:2F:80:BB:16) schedule, decoded bytes captured from real hardware
SCHED_D = bytes.fromhex("2e2a0e2c000000000e2c000000000e2c00000000")  # 20B
SCHED_E = bytes.fromhex("0e2c000000000e2c00000000")  # 12B
SCHED_F = bytes.fromhex("0e2c000000000e2c00000000")  # 12B

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


def test_schedule_parse():
    s = Schedule.parse(SCHED_D, SCHED_E, SCHED_F)
    assert s.home_temperature == 23.0, s.home_temperature
    assert s.away_temperature == 21.0, s.away_temperature
    assert len(s.days) == 7
    # every day: transitions at 07:00 (mark 14) and 22:00 (mark 44)
    for d in range(7):
        assert s.days[d] == [14, 44], (d, s.days[d])
    intervals = s.day_intervals(0)
    assert intervals == [
        ("00:00", "07:00", False),
        ("07:00", "22:00", True),
        ("22:00", "24:00", False),
    ], intervals


def test_schedule_pack_roundtrip():
    s = Schedule.parse(SCHED_D, SCHED_E, SCHED_F)
    d, e, f = s.pack()
    assert d == SCHED_D, d.hex()
    assert e == SCHED_E, e.hex()
    assert f == SCHED_F, f.hex()
    # modify and re-parse
    s.home_temperature = 22.5
    s.days[2] = [12, 40]  # Wed: 06:00-20:00 home
    s2 = Schedule.parse(*s.pack())
    assert s2.home_temperature == 22.5
    assert s2.days[2] == [12, 40]
    assert s2.days[0] == [14, 44]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all good")
