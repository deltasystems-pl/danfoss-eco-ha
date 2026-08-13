"""Sync-time button for the eTRV."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DanfossEcoConfigEntry
from .const import DOMAIN
from .coordinator import EtrvCoordinator

# Serialize BLE commands to one device at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [EtrvSyncTimeButton(coordinator), EtrvRefreshButton(coordinator)]
    )


class _EtrvButton(CoordinatorEntity[EtrvCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _key: str

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator)
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_{self._key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})


class EtrvSyncTimeButton(_EtrvButton):
    _key = "sync_time"
    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        await self.coordinator.sync_time()
        await self.coordinator.async_request_refresh()


class EtrvRefreshButton(_EtrvButton):
    """Force an immediate read of the thermostat (diagnostic)."""

    _key = "refresh"
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    @property
    def available(self) -> bool:
        # Must stay pressable even when polls are failing - that's exactly when
        # the user wants to retry fetching data.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
