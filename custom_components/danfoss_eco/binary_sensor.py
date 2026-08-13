"""Problem binary sensor with decoded eTRV error flags."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN
from .coordinator import EtrvCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EtrvProblemSensor(entry.runtime_data)])


class EtrvProblemSensor(CoordinatorEntity[EtrvCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator)
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_problem"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

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
