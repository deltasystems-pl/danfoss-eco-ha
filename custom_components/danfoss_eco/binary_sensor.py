"""Problem binary sensor with decoded eTRV error flags."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DanfossEcoConfigEntry
from .coordinator import EtrvCoordinator
from .entity import EtrvEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [EtrvProblemSensor(coordinator), EtrvConnectionSensor(coordinator)]
    )


class EtrvProblemSensor(EtrvEntity, BinarySensorEntity):
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "problem")

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.errors.any_error

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.coordinator.data is None:
            return None
        return dict(self.coordinator.data.errors.flags)


class EtrvConnectionSensor(EtrvEntity, BinarySensorEntity):
    """Whether the last poll actually reached the thermostat.

    With cached readings on show, the other entities no longer go unavailable
    when the radio link drops - this one does that job instead, and stays
    available precisely when everything else is running on cache.
    """

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _always_available = True

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "connection")

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        coordinator = self.coordinator
        return {
            "last_success": (
                coordinator.last_success.isoformat()
                if coordinator.last_success
                else None
            ),
            "last_advertisement": (
                coordinator.last_seen.isoformat() if coordinator.last_seen else None
            ),
            "consecutive_failures": coordinator.consecutive_failures,
            "last_error": coordinator.last_error,
            "showing_cached_data": coordinator.is_stale,
        }
