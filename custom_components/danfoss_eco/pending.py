"""Pending-write queue for one eTRV.

A Danfoss Eco is a sleepy battery device that is often only reachable for a few
seconds at a time - and sometimes not at all, when the nearest Bluetooth proxy
is too far away. Failing a service call in that situation is useless to the
user: what they asked for ("heat this room to 22") is still what they want five
minutes later.

So every write is recorded here instead of going straight to the radio, and the
coordinator flushes the queue on its next successful connection.

Everything is *coalesced*, never appended: a setpoint is a desired end state,
not an event. Setting 21 then 22 while offline must result in exactly one write
of 22, not two writes the valve has to chew through. The same holds for config
bits (last toggle wins) and schedule temperatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .const import DeviceMode

# Human-readable labels for the settings fields, used by the "pending writes"
# sensor so the user can see what is still waiting to be delivered.
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_SETTINGS_LABELS = {
    "mode": "mode",
    "temperature_min": "minimum setpoint",
    "temperature_max": "maximum setpoint",
    "frost_protection": "frost protection",
    "vacation_temperature": "vacation temperature",
    "vacation_from": "vacation start",
    "vacation_to": "vacation end",
}


@dataclass
class PendingWrites:
    """Coalesced set of changes waiting for the thermostat to be reachable."""

    set_point: float | None = None
    # Settings-block field overrides (Settings dataclass field name -> value).
    # "mode" is held as a plain int so the queue stays JSON-serializable.
    settings: dict[str, Any] = field(default_factory=dict)
    config_bits_on: int = 0
    config_bits_off: int = 0
    schedule_home: float | None = None
    schedule_away: float | None = None
    # Seven entries, Monday first; None means "leave this day as the device
    # has it", so editing Monday alone never clobbers the rest of the week.
    schedule_days: list[list[int] | None] | None = None
    sync_time: bool = False
    # When the oldest still-queued change was made (ISO string, UTC).
    queued_at: str | None = None

    # ------------------------------------------------------------ queueing --
    def _stamp(self) -> None:
        if self.queued_at is None:
            self.queued_at = datetime.now(UTC).isoformat()

    def queue_set_point(self, value: float) -> None:
        self.set_point = value
        self._stamp()

    def queue_settings(self, **changes: Any) -> None:
        if not changes:
            return
        for key, value in changes.items():
            self.settings[key] = int(value) if key == "mode" else value
        self._stamp()

    def queue_mode(self, mode: DeviceMode) -> None:
        self.queue_settings(mode=int(mode))

    def queue_config_bit(self, mask: int, state: bool) -> None:
        """Remember a config-bit toggle; the newest toggle of a bit wins."""
        if state:
            self.config_bits_on |= mask
            self.config_bits_off &= ~mask
        else:
            self.config_bits_off |= mask
            self.config_bits_on &= ~mask
        self._stamp()

    def queue_schedule_temps(
        self, home: float | None = None, away: float | None = None
    ) -> None:
        if home is None and away is None:
            return
        if home is not None:
            self.schedule_home = home
        if away is not None:
            self.schedule_away = away
        self._stamp()

    def queue_schedule_days(self, days: list[list[int] | None]) -> None:
        """Merge per-day programs; days left as None keep whatever is queued."""
        if self.schedule_days is None:
            self.schedule_days = [None] * 7
        for idx, marks in enumerate(days[:7]):
            if marks is not None:
                self.schedule_days[idx] = list(marks)
        self._stamp()

    def queue_sync_time(self) -> None:
        self.sync_time = True
        self._stamp()

    # ------------------------------------------------------------- state ----
    @property
    def is_empty(self) -> bool:
        return not (
            self.set_point is not None
            or self.settings
            or self.config_bits_on
            or self.config_bits_off
            or self.schedule_home is not None
            or self.schedule_away is not None
            or self.schedule_days is not None
            or self.sync_time
        )

    @property
    def touches_schedule(self) -> bool:
        return (
            self.schedule_home is not None
            or self.schedule_away is not None
            or self.schedule_days is not None
        )

    @property
    def count(self) -> int:
        """Number of distinct changes waiting (what the sensor reports)."""
        n = len(self.settings)
        n += 1 if self.set_point is not None else 0
        n += bin(self.config_bits_on | self.config_bits_off).count("1")
        n += 1 if self.schedule_home is not None else 0
        n += 1 if self.schedule_away is not None else 0
        n += 1 if self.schedule_days is not None else 0
        n += 1 if self.sync_time else 0
        return n

    def clear(self) -> None:
        self.set_point = None
        self.settings = {}
        self.config_bits_on = 0
        self.config_bits_off = 0
        self.schedule_home = None
        self.schedule_away = None
        self.schedule_days = None
        self.sync_time = False
        self.queued_at = None

    def clear_schedule(self) -> None:
        self.schedule_home = None
        self.schedule_away = None
        self.schedule_days = None

    def snapshot(self) -> "PendingWrites":
        """Copy taken when a flush starts, so writes queued mid-flush survive."""
        return PendingWrites(
            set_point=self.set_point,
            settings=dict(self.settings),
            config_bits_on=self.config_bits_on,
            config_bits_off=self.config_bits_off,
            schedule_home=self.schedule_home,
            schedule_away=self.schedule_away,
            schedule_days=(
                [None if d is None else list(d) for d in self.schedule_days]
                if self.schedule_days
                else None
            ),
            sync_time=self.sync_time,
            queued_at=self.queued_at,
        )

    def subtract(self, applied: "PendingWrites") -> None:
        """Drop everything `applied` delivered, keeping newer changes intact.

        A user can move the setpoint again while the flush connection is open;
        clearing the queue wholesale would silently swallow that change.
        """
        if applied.set_point is not None and self.set_point == applied.set_point:
            self.set_point = None
        for key, value in applied.settings.items():
            if self.settings.get(key) == value:
                self.settings.pop(key, None)
        self.config_bits_on &= ~applied.config_bits_on
        self.config_bits_off &= ~applied.config_bits_off
        if applied.schedule_home is not None and self.schedule_home == applied.schedule_home:
            self.schedule_home = None
        if applied.schedule_away is not None and self.schedule_away == applied.schedule_away:
            self.schedule_away = None
        if applied.schedule_days is not None and self.schedule_days == applied.schedule_days:
            self.schedule_days = None
        if applied.sync_time:
            self.sync_time = False
        if self.is_empty:
            self.queued_at = None

    @property
    def age_seconds(self) -> float | None:
        if self.queued_at is None:
            return None
        try:
            queued = datetime.fromisoformat(self.queued_at)
        except ValueError:
            return None
        return (datetime.now(UTC) - queued).total_seconds()

    # -------------------------------------------------------- presentation --
    def describe(self) -> list[str]:
        """Human-readable list of what is still waiting to be written."""
        out: list[str] = []
        if self.set_point is not None:
            out.append(f"setpoint -> {self.set_point} °C")
        for key, value in self.settings.items():
            label = _SETTINGS_LABELS.get(key, key)
            if key == "mode":
                try:
                    value = DeviceMode(int(value)).name.lower()
                except ValueError:
                    pass
            out.append(f"{label} -> {value}")
        for mask, state in ((self.config_bits_on, "on"), (self.config_bits_off, "off")):
            bit = 1
            while bit <= 0x80:
                if mask & bit:
                    out.append(f"config bit {bit:#04x} -> {state}")
                bit <<= 1
        if self.schedule_home is not None:
            out.append(f"comfort temperature -> {self.schedule_home} °C")
        if self.schedule_away is not None:
            out.append(f"setback temperature -> {self.schedule_away} °C")
        if self.schedule_days is not None:
            named = [
                _WEEKDAYS[i]
                for i, d in enumerate(self.schedule_days)
                if d is not None
            ]
            out.append(f"weekly program ({', '.join(named)})")
        if self.sync_time:
            out.append("clock sync")
        return out

    # ------------------------------------------------------- serialization --
    def as_dict(self) -> dict[str, Any]:
        return {
            "set_point": self.set_point,
            "settings": self.settings,
            "config_bits_on": self.config_bits_on,
            "config_bits_off": self.config_bits_off,
            "schedule_home": self.schedule_home,
            "schedule_away": self.schedule_away,
            "schedule_days": self.schedule_days,
            "sync_time": self.sync_time,
            "queued_at": self.queued_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PendingWrites":
        if not data:
            return cls()
        days = data.get("schedule_days")
        return cls(
            set_point=data.get("set_point"),
            settings=dict(data.get("settings") or {}),
            config_bits_on=int(data.get("config_bits_on") or 0),
            config_bits_off=int(data.get("config_bits_off") or 0),
            schedule_home=data.get("schedule_home"),
            schedule_away=data.get("schedule_away"),
            schedule_days=(
                [None if d is None else list(d) for d in days] if days else None
            ),
            sync_time=bool(data.get("sync_time")),
            queued_at=data.get("queued_at"),
        )
