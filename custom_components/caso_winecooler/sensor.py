"""Temperature sensors for CASO Wine Cooler."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

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
import homeassistant.util.dt as dt_util

from .coordinator import CasoWinecoolerCoordinator
from .const import DOMAIN
from .entity import CasoEntity, is_two_zone


def _parse_utc_timestamp(v: str | None) -> datetime | None:
    if not v:
        return None
    dt = dt_util.parse_datetime(v)
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class CasoSensorDescription(SensorEntityDescription):
    data_key: str = ""
    zone: int = 1
    value_fn: Callable[[str | None], datetime | float | None] | None = None


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
    CasoSensorDescription(
        key="last_updated",
        name="Last Updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        data_key="logTimestampUtc",
        zone=1,
        value_fn=_parse_utc_timestamp,
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
        CasoTemperatureSensor(coordinator, entry, desc)
        for desc in SENSOR_DESCRIPTIONS
        if desc.zone == 1 or two_zone
    ]
    async_add_entities(entities)


class CasoTemperatureSensor(CasoEntity, SensorEntity):
    """A temperature sensor entity for one zone of the wine cooler."""

    entity_description: CasoSensorDescription

    @property
    def native_value(self) -> datetime | float | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self.entity_description.data_key)
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(raw)
        return raw

    @property
    def native_unit_of_measurement(self) -> str:
        if self.coordinator.data and self.coordinator.data.get("temperatureUnit") == "F":
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS
