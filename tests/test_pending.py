"""Tests for the pending-write queue.

The queue is what stands between "the thermostat was out of range" and "the
command was lost", so the coalescing and subtract rules are worth pinning down.

Run: python tests/test_pending.py (or python -m pytest tests/).
"""

import importlib.util
import os
import sys
import types

_DIR = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "danfoss_eco"
)

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
pending_mod = _load("pending")
PendingWrites = pending_mod.PendingWrites

BIT_CHILD_LOCK = 0x80
BIT_SLOW = 0x10


def test_setpoint_coalesces():
    p = PendingWrites()
    p.queue_set_point(21.0)
    p.queue_set_point(22.5)
    assert p.set_point == 22.5
    assert p.count == 1  # one write reaches the valve, not two


def test_config_bit_last_toggle_wins():
    p = PendingWrites()
    p.queue_config_bit(BIT_CHILD_LOCK, True)
    p.queue_config_bit(BIT_CHILD_LOCK, False)
    assert p.config_bits_on == 0
    assert p.config_bits_off == BIT_CHILD_LOCK
    p.queue_config_bit(BIT_SLOW, True)
    assert p.config_bits_on == BIT_SLOW
    assert p.count == 2


def test_empty_and_clear():
    p = PendingWrites()
    assert p.is_empty
    assert p.queued_at is None
    p.queue_sync_time()
    assert not p.is_empty and p.queued_at is not None
    p.clear()
    assert p.is_empty and p.queued_at is None


def test_subtract_keeps_changes_made_during_the_flush():
    """A setpoint moved while the BLE connection is open must survive."""
    p = PendingWrites()
    p.queue_set_point(21.0)
    p.queue_config_bit(BIT_CHILD_LOCK, True)
    in_flight = p.snapshot()

    # ... user drags the slider again while the write is on the wire
    p.queue_set_point(23.0)

    p.subtract(in_flight)
    assert p.set_point == 23.0, "newer setpoint was swallowed"
    assert p.config_bits_on == 0, "delivered config bit stayed queued"
    assert p.count == 1
    assert p.queued_at is not None


def test_subtract_empties_when_everything_was_delivered():
    p = PendingWrites()
    p.queue_set_point(21.0)
    p.queue_mode(1)
    p.queue_schedule_temps(home=22.0, away=18.0)
    p.queue_sync_time()
    p.subtract(p.snapshot())
    assert p.is_empty
    assert p.queued_at is None


def test_schedule_days_merge_per_day():
    p = PendingWrites()
    p.queue_schedule_days([[14, 44], None, None, None, None, None, None])
    p.queue_schedule_days([None, None, [12, 40], None, None, None, None])
    assert p.schedule_days[0] == [14, 44]
    assert p.schedule_days[2] == [12, 40]
    assert p.schedule_days[1] is None, "untouched day must stay untouched"


def test_roundtrip_through_storage():
    p = PendingWrites()
    p.queue_set_point(22.0)
    p.queue_settings(temperature_max=25.0)
    p.queue_config_bit(BIT_CHILD_LOCK, False)
    p.queue_schedule_days([None, [10, 30], None, None, None, None, None])
    restored = PendingWrites.from_dict(p.as_dict())
    assert restored == p, "queue did not survive a restart"


def test_describe_is_human_readable():
    p = PendingWrites()
    p.queue_set_point(22.0)
    p.queue_mode(1)
    p.queue_sync_time()
    text = " | ".join(p.describe())
    assert "22.0" in text
    assert "scheduled" in text
    assert "clock sync" in text


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("all good")
