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
    async_add_entities([EtrvSyncTimeButton(entry.runtime_data)])


class EtrvSyncTimeButton(CoordinatorEntity[EtrvCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator)
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_sync_time"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

    async def async_press(self) -> None:
        await self.coordinator.sync_time()
        await self.coordinator.async_request_refresh()
