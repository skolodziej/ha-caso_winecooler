# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration for the CASO Wine Cooler, installed via HACS from a public GitHub repository. There are no build steps, no tests, and no linter config — changes are deployed by pushing to GitHub and creating a release.

## Deployment

1. Push changes to `main`
2. Bump `version` in `manifest.json` (semver: `1.0.0` → `1.0.1`)
3. On GitHub: **Releases → Draft a new release → Tag** = `v<version>` → Publish
4. In HA: **HACS → CASO Wine Cooler → Update**
5. Restart Home Assistant

HACS matches the GitHub release tag against `manifest.json`. Without a new release, HACS will not show an update to end users.

## API

- Base URL: `https://publickitchenapi.casoapp.com/api/v1.2`
- Auth: `x-api-key` header
- Rate limit: unknown, treat as ~5 req/min max
- Spec: `https://publickitchenapi.casoapp.com/swagger/index.html` (v1.0–v1.2)

Relevant endpoints:
- `GET /Devices/GetDevices` — used only in config flow to list devices
- `POST /Winecooler/Status` — body `{technicalDeviceId}` — returns full device state
- `POST /Winecooler/SetLight` — body `{technicalDeviceId, zone, lightOn}` — zone 0 = all zones, 1/2 = individual zones; returns updated state

Unused endpoints (no added value):
- `GET /Winecooler/GetStatus` — GET variant of Status, same response
- `GET /UserDetails/GetUserDetails` — user profile, not relevant for HA

**There is no SetTemperature endpoint** in any API version.

## Architecture

All API calls go through `CasoWinecoolerCoordinator` (one per config entry), which enforces a minimum 15s gap between requests via `_throttled_post` + an `asyncio.Lock`. Entities never call the API directly. The coordinator uses HA's shared `aiohttp` session (`async_get_clientsession`).

- **`coordinator.py`** — single source of truth for all HTTP calls and rate limiting; `async_set_light` updates coordinator state directly from the API response (no extra poll needed)
- **`entity.py`** — `CasoEntity` base class shared by all platforms; holds `device_info`, `_attr_has_entity_name`, and common `__init__`; also exports `is_two_zone()`
- **`config_flow.py`** — two-step flow: API key → device selection; `GetDevices` is the only call made outside the coordinator
- **`__init__.py`** — creates coordinator, calls `first_refresh`, then sets up platforms
- **`sensor.py`** / **`light.py`** / **`binary_sensor.py`** — all extend `CasoEntity` + the platform entity class, read from `coordinator.data`

### Rate limiting & startup

The coordinator initialises `_last_request_time = time.monotonic()` so the first poll is always delayed by the full 15s throttle interval. This prevents a 429 caused by the config flow's `GetDevices` request running immediately before `first_refresh`. On 429 the coordinator raises `UpdateFailed`; HA retries at the next poll interval.

### Two-zone detection

The device may have one or two cooling zones. Zone 2 entities are only created if `coordinator.data["temperature2"] is not None`. This check happens in each platform's `async_setup_entry` via `is_two_zone()` from `entity.py`.

### Light zones

`light.py` creates a "Light" entity using `zone=0` (controls all zones in one API call). On two-zone devices it additionally creates "Light Zone 1" and "Light Zone 2" entities. `CasoAllZonesLightEntity` subclasses `CasoLightEntity` and overrides `is_on` to return `True` if any zone is on.

### Sensors

| Entity | Platform | `data_key` | Notes |
|---|---|---|---|
| Temperature Zone 1/2 | sensor | `temperature1/2` | Unit follows `temperatureUnit` field (°C/°F) |
| Target Temperature Zone 1/2 | sensor | `targetTemperature1/2` | Read-only, no SetTemperature API |
| Last Updated | sensor | `logTimestampUtc` | Timestamp of last device report; parsed as UTC-aware datetime |
| Power Zone 1/2 | binary_sensor | `power1/2` | — |
| Light / Light Zone 1/2 | light | `light1/2` | zone=0 controls all zones |
