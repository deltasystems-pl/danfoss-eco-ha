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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DanfossEcoConfigEntry
from .coordinator import EtrvCoordinator, EtrvState
from .entity import EtrvEntity


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
    EtrvSensorDescription(
        key="schedule",
        translation_key="schedule",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: (
            "programmed" if s.schedule and any(s.schedule.days) else "not set"
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [*(EtrvSensor(coordinator, d) for d in SENSORS), EtrvPendingSensor(coordinator)]
    )


class EtrvSensor(EtrvEntity, SensorEntity):
    entity_description: EtrvSensorDescription

    def __init__(
        self, coordinator: EtrvCoordinator, description: EtrvSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):  # noqa: ANN201
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        data = self.coordinator.data
        if data is None:
            return None
        if self.entity_description.key == "rssi":
            return {"source": data.source}
        if self.entity_description.key == "schedule" and data.schedule:
            return data.schedule.as_attributes()
        return None


class EtrvPendingSensor(EtrvEntity, SensorEntity):
    """How many changes are waiting for the thermostat to come back in range."""

    _attr_translation_key = "pending_writes"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _always_available = True

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "pending_writes")

    @property
    def native_value(self) -> int:
        return self.coordinator.pending.count

    @property
    def extra_state_attributes(self) -> dict:
        pending = self.coordinator.pending
        return {"queued_since": pending.queued_at, "changes": pending.describe()}
