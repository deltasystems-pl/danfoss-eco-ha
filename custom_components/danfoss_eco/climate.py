"""Climate entity for the Danfoss Eco eTRV."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
    PRESET_AWAY,
    PRESET_NONE,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL, DeviceMode
from .coordinator import EtrvCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([EtrvClimate(entry.runtime_data, entry)])


class EtrvClimate(CoordinatorEntity[EtrvCoordinator], ClimateEntity):
    """The radiator valve as a thermostat."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO]
    _attr_preset_modes = [PRESET_NONE, PRESET_AWAY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(self, coordinator: EtrvCoordinator, entry: DanfossEcoConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = format_mac(coordinator.address)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, format_mac(coordinator.address))},
            connections={("bluetooth", coordinator.address)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    # ------------------------------------------------------------ state ----
    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.temperature.room if self.coordinator.data else None

    @property
    def target_temperature(self) -> float | None:
        return (
            self.coordinator.data.temperature.set_point if self.coordinator.data else None
        )

    @property
    def min_temp(self) -> float:
        if self.coordinator.data:
            return self.coordinator.data.settings.temperature_min
        return 6.0

    @property
    def max_temp(self) -> float:
        if self.coordinator.data:
            return self.coordinator.data.settings.temperature_max
        return 28.0

    @property
    def hvac_mode(self) -> HVACMode:
        if not self.coordinator.data:
            return HVACMode.HEAT
        mode = self.coordinator.data.settings.mode
        if mode == DeviceMode.SCHEDULED:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        data = self.coordinator.data
        if not data:
            return None
        if data.temperature.room > data.temperature.set_point:
            return HVACAction.IDLE
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str:
        data = self.coordinator.data
        if data and data.settings.mode == DeviceMode.VACATION:
            return PRESET_AWAY
        return PRESET_NONE

    # ---------------------------------------------------------- commands ---
    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_set_temperature(float(temp))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        target = (
            DeviceMode.SCHEDULED if hvac_mode == HVACMode.AUTO else DeviceMode.MANUAL
        )
        await self.coordinator.async_set_mode(target)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == PRESET_AWAY:
            await self.coordinator.async_set_mode(DeviceMode.VACATION)
        else:
            await self.coordinator.async_set_mode(DeviceMode.MANUAL)
