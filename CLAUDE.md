# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration for the CASO Wine Cooler, installed via HACS from a private GitHub repository. There are no build steps, no tests, and no linter config — changes are deployed by pushing to GitHub and updating via HACS.

## Deployment

1. Push changes to `main`
2. In HA: **HACS → CASO Wine Cooler → Update**
3. Restart Home Assistant

## API

- Base URL: `https://publickitchenapi.casoapp.com/api/v1.2`
- Auth: `x-api-key` header
- Rate limit: unknown, treat as ~5 req/min max
- Spec: `https://publickitchenapi.casoapp.com/swagger/index.html` (v1.0–v1.2)

Relevant endpoints:
- `GET /Devices/GetDevices` — used only in config flow to list devices
- `POST /Winecooler/Status` — body `{technicalDeviceId}` — returns full device state
- `POST /Winecooler/SetLight` — body `{technicalDeviceId, zone, lightOn}` — zone 0 = all zones, 1/2 = individual zones; returns updated state

**There is no SetTemperature endpoint** in any API version.

## Architecture

All API calls go through `CasoWinecoolerCoordinator` (one per config entry), which enforces a minimum 15s gap between requests via `_throttled_post` + an `asyncio.Lock`. Entities never call the API directly.

- **`coordinator.py`** — single source of truth for all HTTP calls and rate limiting; `async_set_light` updates coordinator state directly from the API response (no extra poll needed)
- **`config_flow.py`** — two-step flow: API key → device selection; `GetDevices` is the only call made outside the coordinator
- **`__init__.py`** — creates coordinator, calls `first_refresh`, then sets up platforms
- **`sensor.py`** / **`light.py`** / **`binary_sensor.py`** — all extend `CoordinatorEntity`, read from `coordinator.data`

### Two-zone detection

The device may have one or two cooling zones. Zone 2 entities are only created if `coordinator.data["temperature2"] is not None`. This check happens in each platform's `async_setup_entry`.

### Light zones

`light.py` creates a "Light" entity using `zone=0` (controls all zones in one API call). On two-zone devices it additionally creates "Light Zone 1" and "Light Zone 2" entities. `CasoAllZonesLightEntity` subclasses `CasoLightEntity` and overrides `is_on` to return `True` if any zone is on.
