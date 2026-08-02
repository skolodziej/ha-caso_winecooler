"""Data update coordinator for CASO Wine Cooler / BBQ Cooler."""
import asyncio
import logging
import time
from datetime import timedelta

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import API_BASE, DEVICE_TYPE_BBQ, DEVICE_TYPE_WINE

_LOGGER = logging.getLogger(__name__)

# Minimum seconds between any two API requests (stays well within 5 req/min limit)
_MIN_REQUEST_INTERVAL = 15.0

# Overall per-request deadline. A healthy device answers in well under a second;
# the shorter sock_connect cap lets a blocked/dropped IP fail fast (~10s) instead
# of waiting out the full deadline. (A cooler stuck in a fault state can make the
# cloud's Status response hang, which surfaces as a TransientError timeout.)
_REQUEST_TIMEOUT = 30.0
_CONNECT_TIMEOUT = 10.0

# How many consecutive transient failures (429/timeout/connection) we serve the
# last known state for before surfacing the failure and going unavailable.
_MAX_STALE_POLLS = 3

# The CASO API rate-limits aggressively (a burst of a few requests within a
# second can already return 429), which is easy to trip during setup when the
# config flow's GetDevices + type probe land just before the first poll. Retry a
# 429 a couple of times with a backoff so it resolves silently instead of
# surfacing as an error the user has to wait out.
_MAX_429_RETRIES = 2
_RETRY_BACKOFF = 15.0


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
        device_type: str = DEVICE_TYPE_WINE,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"CASO {device_name}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api_key = api_key
        self.device_id = device_id
        self.device_name = device_name
        self.device_type = device_type
        self.is_bbq = device_type == DEVICE_TYPE_BBQ
        self._request_lock = asyncio.Lock()
        self._last_request_time: float = 0.0
        self._consecutive_failures = 0

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        url: str,
        *,
        wait: bool,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict | None:
        """Serialized HTTP request. All API traffic goes through here.

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

            session = async_get_clientsession(self.hass)
            for attempt in range(_MAX_429_RETRIES + 1):
                try:
                    async with session.request(
                        method,
                        url,
                        headers=self._headers(),
                        json=json,
                        params=params,
                        timeout=aiohttp.ClientTimeout(
                            total=_REQUEST_TIMEOUT, sock_connect=_CONNECT_TIMEOUT
                        ),
                    ) as resp:
                        self._last_request_time = time.monotonic()
                        if resp.status == 401:
                            raise ConfigEntryAuthFailed("Invalid API key (401 Unauthorized)")
                        if resp.status == 429:
                            if attempt < _MAX_429_RETRIES:
                                _LOGGER.debug(
                                    "Rate limited (429), retrying in %.0fs (%d/%d)",
                                    _RETRY_BACKOFF,
                                    attempt + 1,
                                    _MAX_429_RETRIES,
                                )
                                await asyncio.sleep(_RETRY_BACKOFF)
                                continue
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

    async def _fetch_status(self, *, wait: bool) -> dict | None:
        """Fetch device status via the endpoint matching this device's type."""
        if self.is_bbq:
            # BBQ cooler: GET with the id as a query parameter.
            return await self._request(
                "GET",
                f"{API_BASE}/BbqCooler/GetStatus",
                wait=wait,
                params={"technicalDeviceId": self.device_id},
            )
        # Wine cooler: POST with the id in the body.
        return await self._request(
            "POST",
            f"{API_BASE}/Winecooler/Status",
            wait=wait,
            json={"technicalDeviceId": self.device_id},
        )

    async def _async_update_data(self) -> dict:
        """Fetch current status (1 request per poll interval)."""
        try:
            result = await self._fetch_status(wait=True)
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
        if self.is_bbq:
            # BBQ cooler has a single light and no zones.
            data = await self._request(
                "POST",
                f"{API_BASE}/BbqCooler/SetLight",
                wait=False,
                json={"technicalDeviceId": self.device_id, "light": light_on},
            )
        else:
            data = await self._request(
                "POST",
                f"{API_BASE}/Winecooler/SetLight",
                wait=False,
                json={
                    "technicalDeviceId": self.device_id,
                    "zone": zone,
                    "lightOn": light_on,
                },
            )
        if data:
            self.async_set_updated_data(data)
