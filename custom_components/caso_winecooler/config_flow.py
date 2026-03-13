"""Config flow for CASO Wine Cooler integration."""
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
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def _fetch_devices(api_key: str) -> list[dict]:
    """Fetch device list from CASO API."""
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://publickitchenapi.casoapp.com/api/v1.2/Devices/GetDevices",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise ValueError("invalid_auth")
            if resp.status != 200:
                raise ValueError("cannot_connect")
            return await resp.json()


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

            return self.async_create_entry(
                title=device_name,
                data={
                    CONF_API_KEY: self._api_key,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: device_name,
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
