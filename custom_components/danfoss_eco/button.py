"""Maintenance buttons for the eTRV."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DanfossEcoConfigEntry
from .coordinator import EtrvCoordinator
from .entity import EtrvEntity

# Serialize BLE commands to one device at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DanfossEcoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            EtrvSyncTimeButton(coordinator),
            EtrvRefreshButton(coordinator),
            EtrvDiscardPendingButton(coordinator),
        ]
    )


class EtrvSyncTimeButton(EtrvEntity, ButtonEntity):
    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "sync_time")

    async def async_press(self) -> None:
        await self.coordinator.sync_time()


class EtrvRefreshButton(EtrvEntity, ButtonEntity):
    """Force an immediate read of the thermostat (diagnostic)."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"
    # Must stay pressable when polls are failing - that is exactly when the
    # user wants to retry, and it also flushes anything queued.
    _always_available = True

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()


class EtrvDiscardPendingButton(EtrvEntity, ButtonEntity):
    """Throw away commands that never reached the thermostat."""

    _attr_translation_key = "discard_pending"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _always_available = True

    def __init__(self, coordinator: EtrvCoordinator) -> None:
        super().__init__(coordinator, "discard_pending")

    async def async_press(self) -> None:
        self.coordinator.async_discard_pending()
        await self.coordinator.async_request_refresh()
