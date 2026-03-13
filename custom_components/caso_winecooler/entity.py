"""Shared base entity for CASO Wine Cooler."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import CasoWinecoolerCoordinator


def is_two_zone(data: dict) -> bool:
    """Return True if the device has a second cooling zone."""
    return data.get("temperature2") is not None


class CasoEntity(CoordinatorEntity[CasoWinecoolerCoordinator]):
    """Base entity shared by all CASO Wine Cooler platforms."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CasoWinecoolerCoordinator,
        entry: ConfigEntry,
        description,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_{description.key}"
        self._device_name = entry.data.get(CONF_DEVICE_NAME, coordinator.device_id)
        self._device_id = entry.data[CONF_DEVICE_ID]

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._device_name,
            "manufacturer": "CASO",
            "model": "Wine Cooler",
        }
