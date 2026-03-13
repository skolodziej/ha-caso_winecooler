"""Data update coordinator for CASO Wine Cooler."""
import logging
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)


class CasoWinecoolerCoordinator(DataUpdateCoordinator):
    """Coordinator fetches status once per interval and shares data with all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        device_id: str,
        device_name: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"CASO Winecooler {device_name}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api_key = api_key
        self.device_id = device_id
        self.device_name = device_name

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _async_update_data(self) -> dict:
        """Fetch current status from the CASO API (1 request per poll)."""
        url = f"{API_BASE}/Winecooler/Status"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._headers(),
                    json={"technicalDeviceId": self.device_id},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 401:
                        raise UpdateFailed("Invalid API key (401 Unauthorized)")
                    if resp.status == 403:
                        raise UpdateFailed("Access denied (403 Forbidden)")
                    if resp.status != 200:
                        raise UpdateFailed(f"Unexpected API response: {resp.status}")
                    data = await resp.json()
                    _LOGGER.debug("Status for %s: %s", self.device_id, data)
                    return data
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Connection error: {err}") from err

    async def async_set_light(self, zone: int, light_on: bool) -> None:
        """Send SetLight command and refresh coordinator data from the response."""
        url = f"{API_BASE}/Winecooler/SetLight"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._headers(),
                    json={
                        "technicalDeviceId": self.device_id,
                        "zone": zone,
                        "lightOn": light_on,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status not in (200, 204):
                        raise ValueError(f"SetLight failed: {resp.status}")
                    if resp.status == 200:
                        # Update coordinator data directly from the response
                        # so we don't need an extra poll request
                        data = await resp.json()
                        if data:
                            self.async_set_updated_data(data)
        except aiohttp.ClientError as err:
            _LOGGER.error("SetLight request failed: %s", err)
            raise
