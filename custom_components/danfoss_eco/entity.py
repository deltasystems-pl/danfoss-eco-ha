"""Shared entity base for the Danfoss Eco integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EtrvCoordinator


class EtrvEntity(CoordinatorEntity[EtrvCoordinator]):
    """Base entity: device identity plus cache-aware availability.

    The default `CoordinatorEntity.available` goes false the instant a poll
    fails, which for a BLE valve behind a distant proxy means the whole device
    disappears from the dashboard over one missed connection. Here availability
    follows the *cached reading* instead: the entity stays usable (and
    writable - commands queue) for as long as the cache is considered valid.
    """

    _attr_has_entity_name = True
    # Entities that must stay usable precisely when the device is unreachable
    # (Refresh now, the queue sensor, connection status) set this.
    _always_available = False

    def __init__(self, coordinator: EtrvCoordinator, key: str | None = None) -> None:
        super().__init__(coordinator)
        mac = format_mac(coordinator.address)
        self._attr_unique_id = f"{mac}_{key}" if key else mac
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, mac)})

    @property
    def available(self) -> bool:
        if self._always_available:
            return True
        return self.coordinator.cache_valid
