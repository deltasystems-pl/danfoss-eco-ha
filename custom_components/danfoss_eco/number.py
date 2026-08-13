"""Number entities for eTRV settings temperatures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN
from .coordinator import EtrvCoordinator, EtrvState


@dataclass(frozen=True, kw_only=True)
class EtrvNumberDescription(NumberEntityDescription):
    value_fn: Callable[[EtrvState], float]
    settings_field: str


NUMBERS: tuple[EtrvNumberDescription, ...] = (
    EtrvNumberDescription(
        key="temperature_min",
        translation_key="temperature_min",
        native_min_value=4.0,
        native_max_value=15.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.settings.temperature_min,
        settings_field="temperature_min",
    ),
    EtrvNumberDescription(
        key="temperature_max",
        translation_key="temperature_max",
        native_min_value=15.0,
        native_max_value=28.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.settings.temperature_max,
        settings_field="temperature_max",
    ),
    EtrvNumberDescription(
        key="frost_protection",
        translation_key="frost_protection",
        native_min_value=4.0,
        native_max_value=10.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.settings.frost_protection,
        settings_field="frost_protection",
    ),
    EtrvNumberDescription(
        key="vacation_temperature",
        translation_key="vacation_temperature",
        native_min_value=4.0,
        native_max_value=28.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.settings.vacation_temperature,
        settings_field="vacation_temperature",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(EtrvNumber(coordinator, d) for d in NUMBERS)


class EtrvNumber(CoordinatorEntity[EtrvCoordinator], NumberEntity):
    _attr_has_entity_name = True
    entity_description: EtrvNumberDescription

    def __init__(
        self, coordinator: EtrvCoordinator, description: EtrvNumberDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_update_settings(
            **{self.entity_description.settings_field: value}
        )
