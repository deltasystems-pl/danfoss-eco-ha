"""Constants for the Danfoss Eco integration."""

from __future__ import annotations

from enum import IntEnum

DOMAIN = "danfoss_eco"

MANUFACTURER = "Danfoss"
MODEL = "Eco (eTRV)"

# Danfoss OUI prefix used in advertisements ("<digit>;0:04:2F:xx:yy:zz;eTRV")
DANFOSS_OUI = "00:04:2F"

CONF_SECRET_KEY = "secret_key"
CONF_PIN = "pin"
CONF_POLL_INTERVAL = "poll_interval"
CONF_AUTO_TIME_SYNC = "auto_time_sync"

DEFAULT_PIN = 0
DEFAULT_POLL_INTERVAL_MIN = 15
DEFAULT_AUTO_TIME_SYNC = True

# --- GATT UUIDs (settings service) -----------------------------------------
UUID_SERVICE_SETTINGS = "10020000-2749-0001-0000-00805f9b042f"
UUID_PIN = "10020001-2749-0001-0000-00805f9b042f"
UUID_SETTINGS = "10020003-2749-0001-0000-00805f9b042f"
UUID_TEMPERATURE = "10020005-2749-0001-0000-00805f9b042f"
UUID_NAME = "10020006-2749-0001-0000-00805f9b042f"
UUID_CURRENT_TIME = "10020008-2749-0001-0000-00805f9b042f"
UUID_ERRORS = "10020009-2749-0001-0000-00805f9b042f"
UUID_SECRET_KEY = "1002000b-2749-0001-0000-00805f9b042f"
# Schedule characteristics (never fully documented by prior projects; probed here).
UUID_SCHEDULE_1 = "1002000d-2749-0001-0000-00805f9b042f"
UUID_SCHEDULE_2 = "1002000e-2749-0001-0000-00805f9b042f"
UUID_SCHEDULE_3 = "1002000f-2749-0001-0000-00805f9b042f"

UUID_BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"

SECRET_KEY_LENGTH = 16


class DeviceMode(IntEnum):
    """Operating mode byte in the settings block."""

    MANUAL = 0
    SCHEDULED = 1
    VACATION = 3
    HOLD = 5


ATTR_LAST_POLL = "last_poll"
ATTR_RSSI = "rssi"
ATTR_SOURCE = "source"

ERROR_FLAGS = {
    "e9_valve_does_not_close": 8,
    "e10_invalid_time": 9,
    "e14_low_battery": 13,
    "e15_very_low_battery": 14,
}
