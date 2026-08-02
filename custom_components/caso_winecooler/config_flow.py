"""Config flow for CASO Wine Cooler integration."""
import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    API_BASE,
    CONF_API_KEY,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE_BBQ,
    DEVICE_TYPE_WINE,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def _detect_device_type(api_key: str, device_id: str) -> str:
    """Detect whether a device is a BBQ cooler or a wine cooler.

    GetDevices exposes no type field, so we probe the BBQ status endpoint:
    a 200 means the device is a BBQ cooler; anything else (typically 400 for a
    wine cooler, or a network hiccup) falls back to wine cooler, which is both
    the common case and the originally supported type.
    """
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{API_BASE}/BbqCooler/GetStatus",
                headers=headers,
                params={"technicalDeviceId": device_id},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    return DEVICE_TYPE_BBQ
    except (aiohttp.ClientError, asyncio.TimeoutError):
        _LOGGER.debug("BBQ probe failed for %s, assuming wine cooler", device_id)
    return DEVICE_TYPE_WINE


async def _fetch_devices(api_key: str) -> list[dict]:
    """Fetch device list from CASO API."""
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_BASE}/Devices/GetDevices",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise ValueError("invalid_auth")
            if resp.status == 429:
                raise ValueError("rate_limit")
            if resp.status != 200:
                raise ValueError("cannot_connect")
            try:
                return await resp.json(content_type=None)
            except Exception as err:
                raise ValueError("cannot_connect") from err


async def _validate_api_key(hass: HomeAssistant, api_key: str) -> list[dict]:
    """Validate key and return devices. Raises ValueError with error key on failure."""
    try:
        devices = await _fetch_devices(api_key)
    except aiohttp.ClientError:
        raise ValueError("cannot_connect")
    if not devices:
        raise ValueError("no_devices")
    return devices


class CasoWinecoolerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._devices: list[dict] = []
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle re-authentication after the API key was rejected (401)."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Prompt for a new API key and update the existing entry."""
        errors: dict[str, str] = {}

        if user_input is not None and self._reauth_entry is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await _validate_api_key(self.hass, api_key)
            except ValueError as err:
                errors["base"] = str(err)
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                self._devices = await _validate_api_key(self.hass, api_key)
                self._api_key = api_key
                return await self.async_step_device()
            except ValueError as err:
                errors["base"] = str(err)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        device_options = {
            d["technicalDeviceId"]: d.get("deviceName") or d["technicalDeviceId"]
            for d in self._devices
        }

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            device_name = device_options[device_id]
            scan_interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            # Prevent duplicate entries
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            device_type = await _detect_device_type(self._api_key, device_id)

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: device_name,
                    CONF_DEVICE_TYPE: device_type,
                    CONF_SCAN_INTERVAL: scan_interval,
                },
            )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): vol.In(device_options),
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL)),
                }
            ),
            errors=errors,
        )
