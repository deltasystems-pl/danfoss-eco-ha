"""Configuration switches for the eTRV (settings config bits)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN
from .coordinator import EtrvCoordinator
from .protocol import Settings

# Serialize BLE commands to one device at a time.
PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EtrvSwitchDescription(SwitchEntityDescription):
    bit_mask: int


SWITCHES: tuple[EtrvSwitchDescription, ...] = (
    EtrvSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:lock-outline",
        bit_mask=Settings.BIT_CHILD_LOCK,
    ),
    EtrvSwitchDescription(
        key="adaptable_regulation",
        translation_key="adaptable_regulation",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:brain",
        bit_mask=Settings.BIT_ADAPTABLE_REGULATION,
    ),
    EtrvSwitchDescription(
        key="slow_regulation",
        translation_key="slow_regulation",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:speedometer-slow",
        bit_mask=Settings.BIT_SLOW_REGULATION,
    ),
    EtrvSwitchDescription(
        key="display_flip",
        translation_key="display_flip",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:phone-rotate-landscape",
        bit_mask=Settings.BIT_DISPLAY_FLIP,
    ),
    EtrvSwitchDescription(
        key="vertical_installation",
        translation_key="vertical_installation",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:swap-vertical",
        bit_mask=Settings.BIT_VERTICAL_INSTALLATION,
        entity_registry_enabled_default=False,
    ),
    EtrvSwitchDescription(
        key="valve_installed",
        translation_key="valve_installed",
        entity_category=EntityCategory.CONFIG,
        icon="mdi:wrench",
        bit_mask=Settings.BIT_VALVE_INSTALLED,
        # Toggling re-triggers valve adaptation - keep it opt-in.
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(EtrvConfigSwitch(coordinator, d) for d in SWITCHES)


class EtrvConfigSwitch(CoordinatorEntity[EtrvCoordinator], SwitchEntity):
    """One settings config bit as a switch."""

    _attr_has_entity_name = True
    entity_description: EtrvSwitchDescription

    def __init__(
        self, coordinator: EtrvCoordinator, description: EtrvSwitchDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_{description.key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(
            self.coordinator.data.settings.config_bits & self.entity_description.bit_mask
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_config_bit(self.entity_description.bit_mask, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_config_bit(self.entity_description.bit_mask, False)
