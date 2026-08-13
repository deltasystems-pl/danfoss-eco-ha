"""Diagnostic sensors: battery, room temperature, RSSI, last poll."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN
from .coordinator import EtrvCoordinator, EtrvState


@dataclass(frozen=True, kw_only=True)
class EtrvSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EtrvState], object]


SENSORS: tuple[EtrvSensorDescription, ...] = (
    EtrvSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery,
    ),
    EtrvSensorDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature.room,
    ),
    EtrvSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
        value_fn=lambda s: s.rssi,
    ),
    EtrvSensorDescription(
        key="last_poll",
        translation_key="last_poll",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_poll,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(EtrvSensor(coordinator, d) for d in SENSORS)


class EtrvSensor(CoordinatorEntity[EtrvCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: EtrvSensorDescription

    def __init__(
        self, coordinator: EtrvCoordinator, description: EtrvSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

    @property
    def native_value(self):  # noqa: ANN201
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key == "rssi" and self.coordinator.data:
            return {"source": self.coordinator.data.source}
        return None
