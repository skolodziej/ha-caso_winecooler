"""Temperature sensors for CASO Wine Cooler / BBQ Cooler."""
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


# The BBQ cooler reports temperature as a string: usually numeric ("6"), but
# "LO"/"HI" at the extremes of its range. Per the device spec LO = 1 °C and
# HI = 12 °C (converted when the device reports in Fahrenheit).
_BBQ_LEVELS_CELSIUS = {"LO": 1.0, "HI": 12.0}


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


# BBQ cooler: a single temperature (reported as a string) and no target/zones.
BBQ_SENSOR_DESCRIPTIONS: tuple[CasoSensorDescription, ...] = (
    CasoSensorDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        data_key="temperature",
    ),
    CasoSensorDescription(
        key="last_updated",
        name="Last Updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        data_key="logTimestampUtc",
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

    if coordinator.is_bbq:
        entities = [
            CasoTemperatureSensor(coordinator, entry, desc)
            for desc in BBQ_SENSOR_DESCRIPTIONS
        ]
    else:
        two_zone = is_two_zone(data)
        entities = [
            CasoTemperatureSensor(coordinator, entry, desc)
            for desc in SENSOR_DESCRIPTIONS
            if desc.zone == 1 or two_zone
        ]
    async_add_entities(entities)


class CasoTemperatureSensor(CasoEntity, SensorEntity):
    """A temperature (or timestamp) sensor entity for the cooler."""

    entity_description: CasoSensorDescription

    @property
    def native_value(self) -> datetime | float | None:
        if self.coordinator.data is None:
            return None
        raw = self.coordinator.data.get(self.entity_description.data_key)
        if self.entity_description.device_class == SensorDeviceClass.TEMPERATURE:
            return self._coerce_temperature(raw)
        if self.entity_description.value_fn is not None:
            return self.entity_description.value_fn(raw)
        return raw

    def _coerce_temperature(self, raw) -> float | None:
        """Coerce a temperature reading to a number.

        Wine coolers report integers; the BBQ cooler reports a string that is
        usually numeric ("6") but is "LO"/"HI" at the extremes of its range.
        Map those to the documented setpoints (converting to °F when the device
        reports in Fahrenheit) so the entity shows a value instead of Unknown.
        """
        if raw is None:
            return None
        if isinstance(raw, str) and raw.strip().upper() in _BBQ_LEVELS_CELSIUS:
            celsius = _BBQ_LEVELS_CELSIUS[raw.strip().upper()]
            if self._is_fahrenheit():
                return round(celsius * 9 / 5 + 32)
            return celsius
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _is_fahrenheit(self) -> bool:
        return bool(
            self.coordinator.data
            and self.coordinator.data.get("temperatureUnit") == "F"
        )

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.device_class != SensorDeviceClass.TEMPERATURE:
            return None
        if self._is_fahrenheit():
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS
