"""Data update coordinator for CASO Wine Cooler."""
import asyncio
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

# Minimum seconds between any two API requests (stays well within 5 req/min limit)
_MIN_REQUEST_INTERVAL = 15.0


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
        self._request_lock = asyncio.Lock()
        # Treat coordinator creation as a recent request so the first poll waits
        # the full throttle interval — avoids a 429 when the config flow just
        # made a request seconds before setup completes.
        self._last_request_time: float = time.monotonic()

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _throttled_post(self, url: str, payload: dict) -> dict | None:
        """Execute a POST request, enforcing a minimum interval between requests."""
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < _MIN_REQUEST_INTERVAL:
                wait = _MIN_REQUEST_INTERVAL - elapsed
                _LOGGER.debug("Rate limit: waiting %.1fs before next request", wait)
                await asyncio.sleep(wait)

            try:
                session = async_get_clientsession(self.hass)
                async with session.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    self._last_request_time = time.monotonic()
                    if resp.status == 429:
                        raise UpdateFailed("API rate limit exceeded (429) — try increasing the polling interval")
                    if resp.status == 401:
                        raise UpdateFailed("Invalid API key (401 Unauthorized)")
                    if resp.status == 403:
                        raise UpdateFailed("Access denied (403 Forbidden)")
                    if resp.status not in (200, 204):
                        raise UpdateFailed(f"Unexpected API response: {resp.status}")
                    if resp.status == 200:
                        try:
                            data = await resp.json(content_type=None)
                        except Exception as err:
                            raise UpdateFailed(f"Invalid JSON response: {err}") from err
                        _LOGGER.debug("Response from %s: keys=%s", url, list(data.keys()) if isinstance(data, dict) else type(data).__name__)
                        return data
                    return None
            except aiohttp.ClientError as err:
                raise UpdateFailed(f"Connection error: {err}") from err

    async def _async_update_data(self) -> dict:
        """Fetch current status (1 request per poll interval)."""
        result = await self._throttled_post(
            f"{API_BASE}/Winecooler/Status",
            {"technicalDeviceId": self.device_id},
        )
        if result is None:
            raise UpdateFailed("Empty response from status endpoint")
        return result

    async def async_set_light(self, zone: int, light_on: bool) -> None:
        """Send SetLight command; update coordinator state from the response."""
        try:
            data = await self._throttled_post(
                f"{API_BASE}/Winecooler/SetLight",
                {
                    "technicalDeviceId": self.device_id,
                    "zone": zone,
                    "lightOn": light_on,
                },
            )
            if data:
                self.async_set_updated_data(data)
        except UpdateFailed as err:
            _LOGGER.error("SetLight failed: %s", err)
            raise
