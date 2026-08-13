"""Payload (de)serialization for eTRV characteristics.

All multi-byte integers inside decrypted payloads are big-endian.
Temperatures are half-degree steps stored in a single byte.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, replace

from .const import ERROR_FLAGS, DeviceMode


def _to_temp(raw: int) -> float:
    return raw * 0.5


def _from_temp(value: float) -> int:
    return int(round(value * 2))


@dataclass
class Temperature:
    """Payload of UUID_TEMPERATURE (8 bytes decrypted)."""

    set_point: float
    room: float
    raw: bytes

    @classmethod
    def parse(cls, data: bytes) -> "Temperature":
        return cls(set_point=_to_temp(data[0]), room=_to_temp(data[1]), raw=bytes(data))

    def with_set_point(self, value: float) -> bytes:
        out = bytearray(self.raw)
        out[0] = _from_temp(value)
        return bytes(out)


@dataclass
class Settings:
    """Payload of UUID_SETTINGS (16 bytes decrypted).

    Layout: config_bits, t_min, t_max, t_frost, mode, t_vacation (bytes),
    vacation_from, vacation_to (int32), 2 bytes padding.
    """

    config_bits: int
    temperature_min: float
    temperature_max: float
    frost_protection: float
    mode: DeviceMode
    vacation_temperature: float
    vacation_from: int
    vacation_to: int
    raw: bytes

    @classmethod
    def parse(cls, data: bytes) -> "Settings":
        cfg, tmin, tmax, tfrost, mode, tvac, vfrom, vto = struct.unpack(
            ">6Bii2x", data[:16]
        )
        try:
            device_mode = DeviceMode(mode)
        except ValueError:
            device_mode = DeviceMode.MANUAL
        return cls(
            config_bits=cfg,
            temperature_min=_to_temp(tmin),
            temperature_max=_to_temp(tmax),
            frost_protection=_to_temp(tfrost),
            mode=device_mode,
            vacation_temperature=_to_temp(tvac),
            vacation_from=vfrom,
            vacation_to=vto,
            raw=bytes(data),
        )

    # config bit masks (verified against esphome-danfoss-eco device_data.h)
    BIT_ADAPTABLE_REGULATION = 0x01
    BIT_VERTICAL_INSTALLATION = 0x04
    BIT_DISPLAY_FLIP = 0x08
    BIT_SLOW_REGULATION = 0x10
    BIT_VALVE_INSTALLED = 0x40
    BIT_CHILD_LOCK = 0x80

    @property
    def adaptable_regulation(self) -> bool:
        return bool(self.config_bits & self.BIT_ADAPTABLE_REGULATION)

    @property
    def vertical_installation(self) -> bool:
        return bool(self.config_bits & self.BIT_VERTICAL_INSTALLATION)

    @property
    def display_flip(self) -> bool:
        return bool(self.config_bits & self.BIT_DISPLAY_FLIP)

    @property
    def slow_regulation(self) -> bool:
        return bool(self.config_bits & self.BIT_SLOW_REGULATION)

    @property
    def valve_installed(self) -> bool:
        return bool(self.config_bits & self.BIT_VALVE_INSTALLED)

    @property
    def child_lock(self) -> bool:
        return bool(self.config_bits & self.BIT_CHILD_LOCK)

    def pack(self, **changes: object) -> bytes:
        """Re-serialize, applying keyword overrides."""
        s = replace(self, **changes) if changes else self
        out = bytearray(self.raw[:16])
        out[0] = s.config_bits
        out[1] = _from_temp(s.temperature_min)
        out[2] = _from_temp(s.temperature_max)
        out[3] = _from_temp(s.frost_protection)
        out[4] = int(s.mode)
        out[5] = _from_temp(s.vacation_temperature)
        struct.pack_into(">ii", out, 6, s.vacation_from, s.vacation_to)
        return bytes(out)


@dataclass
class Errors:
    """Payload of UUID_ERRORS (8 bytes decrypted, uint16 flags at offset 0)."""

    flags: dict[str, bool]

    @classmethod
    def parse(cls, data: bytes) -> "Errors":
        bits = struct.unpack_from(">H", data, 0)[0]
        return cls(flags={name: bool(bits & (1 << bit)) for name, bit in ERROR_FLAGS.items()})

    @property
    def any_error(self) -> bool:
        return any(self.flags.values())


@dataclass
class DeviceTime:
    """Payload of UUID_CURRENT_TIME (8 bytes decrypted): local epoch + offset."""

    time_local: int
    offset: int

    @classmethod
    def parse(cls, data: bytes) -> "DeviceTime":
        t, off = struct.unpack(">ii", data[:8])
        return cls(time_local=t, offset=off)

    @classmethod
    def now(cls) -> "DeviceTime":
        offset = -time.timezone if not time.localtime().tm_isdst else -time.altzone
        return cls(time_local=int(time.time()) + offset, offset=offset)

    def pack(self) -> bytes:
        return struct.pack(">ii", self.time_local, self.offset)

    @property
    def drift_seconds(self) -> int:
        return abs(self.time_local - DeviceTime.now().time_local)


def parse_name(data: bytes) -> str:
    """Device name characteristic (decrypted, NUL-padded)."""
    return data.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
