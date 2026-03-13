"""Temperature sensors for CASO Wine Cooler."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import CasoWinecoolerCoordinator


@dataclass(frozen=True)
class CasoSensorDescription(SensorEntityDescription):
    data_key: str = ""
    zone: int = 1


SENSOR_DESCRIPTIONS: tuple[CasoSensorDescription, ...] = (
    CasoSensorDescription(
        key="temperature_zone1",
        name="Temperature Zone 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="temperature1",
        zone=1,
    ),
    CasoSensorDescription(
        key="target_temperature_zone1",
        name="Target Temperature Zone 1",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="targetTemperature1",
        zone=1,
    ),
    CasoSensorDescription(
        key="temperature_zone2",
        name="Temperature Zone 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="temperature2",
        zone=2,
    ),
    CasoSensorDescription(
        key="target_temperature_zone2",
        name="Target Temperature Zone 2",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        data_key="targetTemperature2",
        zone=2,
    ),
)


def _is_two_zone(data: dict) -> bool:
    """Return True if the device has a second zone with valid data."""
    return data.get("temperature2") is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CasoWinecoolerCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    two_zone = _is_two_zone(data)

    entities = [
        CasoTemperatureSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
        if desc.zone == 1 or two_zone
    ]
    async_add_entities(entities)


class CasoTemperatureSensor(CoordinatorEntity[CasoWinecoolerCoordinator], SensorEntity):
    """A temperature sensor entity for one zone of the wine cooler."""

    entity_description: CasoSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CasoWinecoolerCoordinator,
        entry: ConfigEntry,
        description: CasoSensorDescription,
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
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.data_key)

    @property
    def native_unit_of_measurement(self) -> str:
        if self.coordinator.data and self.coordinator.data.get("temperatureUnit") == "F":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS
