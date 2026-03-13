"""Light entities for CASO Wine Cooler."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity, LightEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import CasoWinecoolerCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CasoLightDescription(LightEntityDescription):
    data_key: str = ""
    zone: int = 1


# zone=0 controls all zones simultaneously
ALL_ZONES_DESCRIPTION = CasoLightDescription(
    key="light_all_zones",
    name="Light",
    data_key="",   # derived from light1 + light2
    zone=0,
)

ZONE_DESCRIPTIONS: tuple[CasoLightDescription, ...] = (
    CasoLightDescription(
        key="light_zone1",
        name="Light Zone 1",
        data_key="light1",
        zone=1,
    ),
    CasoLightDescription(
        key="light_zone2",
        name="Light Zone 2",
        data_key="light2",
        zone=2,
    ),
)


def _is_two_zone(data: dict) -> bool:
    return data.get("temperature2") is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CasoWinecoolerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    two_zone = _is_two_zone(data)

    entities: list[CasoLightEntity] = []

    if two_zone:
        # Combined "all zones" entity + individual zone entities
        entities.append(CasoAllZonesLightEntity(coordinator, entry, ALL_ZONES_DESCRIPTION))
        entities.extend(
            CasoLightEntity(coordinator, entry, desc) for desc in ZONE_DESCRIPTIONS
        )
    else:
        # Single-zone device: zone 0 == zone 1, use the simpler all-zones entity
        entities.append(CasoAllZonesLightEntity(coordinator, entry, ALL_ZONES_DESCRIPTION))

    async_add_entities(entities)


class CasoLightEntity(CoordinatorEntity[CasoWinecoolerCoordinator], LightEntity):
    """Controls the interior light of a single zone."""

    entity_description: CasoLightDescription
    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        coordinator: CasoWinecoolerCoordinator,
        entry: ConfigEntry,
        description: CasoLightDescription,
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

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get(self.entity_description.data_key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_light(zone=self.entity_description.zone, light_on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_light(zone=self.entity_description.zone, light_on=False)


class CasoAllZonesLightEntity(CasoLightEntity):
    """Controls all zones at once via zone=0. On if any zone is on."""

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        light1 = self.coordinator.data.get("light1")
        light2 = self.coordinator.data.get("light2")
        # True if at least one zone is on; False only when all known zones are off
        values = [v for v in (light1, light2) if v is not None]
        return any(values) if values else None
