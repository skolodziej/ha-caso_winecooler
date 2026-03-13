"""Power state binary sensors for CASO Wine Cooler."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import CasoWinecoolerCoordinator
from .entity import CasoEntity, is_two_zone


@dataclass(frozen=True)
class CasoBinarySensorDescription(BinarySensorEntityDescription):
    data_key: str = ""
    zone: int = 1


BINARY_SENSOR_DESCRIPTIONS: tuple[CasoBinarySensorDescription, ...] = (
    CasoBinarySensorDescription(
        key="power_zone1",
        name="Power Zone 1",
        device_class=BinarySensorDeviceClass.POWER,
        data_key="power1",
        zone=1,
    ),
    CasoBinarySensorDescription(
        key="power_zone2",
        name="Power Zone 2",
        device_class=BinarySensorDeviceClass.POWER,
        data_key="power2",
        zone=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CasoWinecoolerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    two_zone = is_two_zone(data)

    entities = [
        CasoPowerSensor(coordinator, entry, desc)
        for desc in BINARY_SENSOR_DESCRIPTIONS
        if desc.zone == 1 or two_zone
    ]
    async_add_entities(entities)


class CasoPowerSensor(CasoEntity, BinarySensorEntity):
    """Indicates whether a zone is powered on."""

    entity_description: CasoBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get(self.entity_description.data_key))
