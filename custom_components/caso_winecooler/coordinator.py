"""Data update coordinator for CASO Wine Cooler."""
import asyncio
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

# Minimum seconds between any two API requests (stays well within 5 req/min limit)
_MIN_REQUEST_INTERVAL = 15.0

# Overall per-request deadline, and a shorter cap on establishing the connection
# so a blocked/dropped IP fails in ~10s instead of hanging the full timeout.
_REQUEST_TIMEOUT = 30.0
_CONNECT_TIMEOUT = 10.0

# How many consecutive transient failures (429/timeout/connection) we serve the
# last known state for before surfacing the failure and going unavailable.
_MAX_STALE_POLLS = 3


class RateLimitError(UpdateFailed):
    """Raised when the API responds with HTTP 429."""


class TransientError(UpdateFailed):
    """A timeout or connection error — likely temporary, worth tolerating briefly."""


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
        self._last_request_time: float = 0.0
        self._consecutive_failures = 0

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post(self, url: str, payload: dict, *, wait: bool) -> dict | None:
        """Serialized POST request. All API traffic goes through here.

        The lock guarantees only one request runs at a time. When ``wait`` is
        True the throttle interval is honoured before sending; light commands
        pass ``wait=False`` so they respond immediately but still update the
        shared timestamp under the lock (so a following poll spaces itself).
        """
        async with self._request_lock:
            if wait:
                elapsed = time.monotonic() - self._last_request_time
                if elapsed < _MIN_REQUEST_INTERVAL:
                    wait_for = _MIN_REQUEST_INTERVAL - elapsed
                    _LOGGER.debug("Rate limit: waiting %.1fs before next request", wait_for)
                    await asyncio.sleep(wait_for)

            try:
                session = async_get_clientsession(self.hass)
                async with session.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(
                        total=_REQUEST_TIMEOUT, sock_connect=_CONNECT_TIMEOUT
                    ),
                ) as resp:
                    self._last_request_time = time.monotonic()
                    if resp.status == 401:
                        raise ConfigEntryAuthFailed("Invalid API key (401 Unauthorized)")
                    if resp.status == 429:
                        raise RateLimitError(
                            "API rate limit exceeded (429) — try increasing the polling interval"
                        )
                    if resp.status == 403:
                        raise UpdateFailed("Access denied (403 Forbidden)")
                    if resp.status not in (200, 204):
                        raise UpdateFailed(f"Unexpected API response: {resp.status}")
                    if resp.status == 200:
                        try:
                            data = await resp.json(content_type=None)
                        except Exception as err:
                            raise UpdateFailed(f"Invalid JSON response: {err}") from err
                        _LOGGER.debug(
                            "Response from %s: keys=%s",
                            url,
                            list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                        )
                        return data
                    return None
            except asyncio.TimeoutError as err:
                # str(TimeoutError) is empty — spell the deadline out so the UI is useful.
                raise TransientError(
                    f"Timeout after {_REQUEST_TIMEOUT:.0f}s (API did not respond)"
                ) from err
            except aiohttp.ClientError as err:
                raise TransientError(f"Connection error: {err}") from err

    async def _async_update_data(self) -> dict:
        """Fetch current status (1 request per poll interval)."""
        try:
            result = await self._post(
                f"{API_BASE}/Winecooler/Status",
                {"technicalDeviceId": self.device_id},
                wait=True,
            )
        except (RateLimitError, TransientError) as err:
            # Transient blips (429/timeout/connection) shouldn't flap entities to
            # unavailable on a single miss — serve the last state for a few polls.
            # (On the very first refresh self.data is None, so a real setup failure
            # still surfaces as ConfigEntryNotReady.)
            if self.data is not None and self._consecutive_failures < _MAX_STALE_POLLS:
                self._consecutive_failures += 1
                _LOGGER.warning(
                    "%s — keeping last known state (%d/%d)",
                    err,
                    self._consecutive_failures,
                    _MAX_STALE_POLLS,
                )
                return self.data
            raise
        self._consecutive_failures = 0
        if result is None:
            raise UpdateFailed("Empty response from status endpoint")
        return result

    async def async_set_light(self, zone: int, light_on: bool) -> None:
        """Send SetLight command immediately (no throttle wait) and apply the result."""
        data = await self._post(
            f"{API_BASE}/Winecooler/SetLight",
            {
                "technicalDeviceId": self.device_id,
                "zone": zone,
                "lightOn": light_on,
            },
            wait=False,
        )
        if data:
            self.async_set_updated_data(data)
