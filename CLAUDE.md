# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration for CASO coolers (wine coolers and the smaller BBQ cooler), installed via HACS from a public GitHub repository. There are no build steps, no tests, and no linter config — changes are deployed by pushing to GitHub and creating a release.

## Deployment

1. Push changes to `main`
2. Bump `version` in `manifest.json` (semver: `1.0.0` → `1.0.1`)
3. On GitHub: **Releases → Draft a new release → Tag** = `v<version>` → Publish
4. In HA: **HACS → CASO Wine Cooler → Update**
5. Restart Home Assistant

HACS matches the GitHub release tag against `manifest.json`. Without a new release, HACS will not show an update to end users.

## API

- Base URL: `https://publickitchenapi.casoapp.com/api/v1.3`
- Auth: `x-api-key` header
- Rate limit: unknown, treat as ~5 req/min max
- Spec: `https://publickitchenapi.casoapp.com/swagger/index.html` (v1.0–v1.3)

Relevant endpoints:
- `GET /Devices/GetDevices` — used only in config flow to list devices. **Has no device-type field**, so wine vs BBQ is detected by probing (see below).
- `POST /Winecooler/Status` — body `{technicalDeviceId}` — returns full wine-cooler state
- `POST /Winecooler/SetLight` — body `{technicalDeviceId, zone, lightOn}` — zone 0 = all zones, 1/2 = individual zones; returns updated state
- `GET /BbqCooler/GetStatus?technicalDeviceId=…` — returns BBQ-cooler state (single `temperature` as a **string**, single `power`, single `light`, no zones, no target)
- `POST /BbqCooler/SetLight` — body `{technicalDeviceId, light}` (bool, no zone); returns updated state

Unused endpoints (no added value):
- `GET /Winecooler/GetStatus` — GET variant of Status, same response and same ~30s+ latency
- `GET /UserDetails/GetUserDetails` — user profile, not relevant for HA

**There is no SetTemperature endpoint** in any API version.

### Device-type detection

`GetDevices` returns no type field, so the config flow probes `GET /BbqCooler/GetStatus` for the selected device: a 200 means BBQ cooler, anything else (typically 400) means wine cooler. The result is stored as `device_type` (`winecooler`/`bbqcooler`) on the config entry. Entries created before this existed have no `device_type` and default to wine cooler. `coordinator.is_bbq` drives all per-type branching (status endpoint, SetLight payload, which entities each platform creates).

## Architecture

All API calls go through `CasoWinecoolerCoordinator` (one per config entry), which enforces a minimum 15s gap between requests via `_request` + an `asyncio.Lock`. Entities never call the API directly. The coordinator uses HA's shared `aiohttp` session (`async_get_clientsession`). `coordinator.is_bbq` (from the stored `device_type`) selects the wine vs BBQ endpoints and payloads.

- **`coordinator.py`** — single source of truth for all HTTP calls and rate limiting; `_fetch_status` picks the wine (`POST Winecooler/Status`) or BBQ (`GET BbqCooler/GetStatus`) endpoint; `async_set_light` sends the wine (`zone`/`lightOn`) or BBQ (`light`) payload and updates coordinator state directly from the API response (no extra poll needed)
- **`entity.py`** — `CasoEntity` base class shared by all platforms; holds `device_info` (model = "BBQ Cooler"/"Wine Cooler"), `_attr_has_entity_name`, and common `__init__`; also exports `is_two_zone()`
- **`config_flow.py`** — two-step flow: API key → device selection; `GetDevices` and the BBQ-detection probe (`_detect_device_type`) are the only calls made outside the coordinator
- **`__init__.py`** — creates coordinator (passing `device_type`), calls `first_refresh`, then sets up platforms
- **`sensor.py`** / **`light.py`** / **`binary_sensor.py`** — all extend `CasoEntity` + the platform entity class, read from `coordinator.data`, and branch on `coordinator.is_bbq` to create the right entities

### Rate limiting & requests

All API traffic goes through `coordinator._request(method, url, wait=..., json=..., params=...)`, serialized by `_request_lock`. `wait=True` (polling) honours the 15s throttle interval before sending; `wait=False` (light commands) sends immediately but still updates `_last_request_time` under the lock, so a following poll spaces itself. `_last_request_time` starts at `0.0`, so the first poll fires immediately — startup is never blocked.

Requests use a 30s total deadline with a 10s `sock_connect` cap, so a blocked/dropped IP fails in ~10s instead of hanging the full timeout. A healthy device answers in well under a second. If the physical cooler is stuck in a fault state (e.g. a `CE1` error on its display), the cloud's `Status` response can hang and surface as a `TransientError` timeout — that is a device problem, not a network or integration one (power-cycling the cooler clears it).

Error handling in `_request`:
- **401** → `ConfigEntryAuthFailed` → HA starts the reauth flow (`async_step_reauth` in `config_flow.py` re-prompts for the API key).
- **429** → retried in-place up to `_MAX_429_RETRIES` (2) times with a `_RETRY_BACKOFF` (15s) wait before raising `RateLimitError`; the config-flow requests (`_fetch_devices`, `_detect_device_type`) do the same. This absorbs the aggressive burst throttling that setup trips (GetDevices + type probe + first poll landing together) so it resolves silently instead of surfacing an error. **timeout / connection error** → `TransientError`. `RateLimitError` and `TransientError` both subclass `UpdateFailed`; `_async_update_data` serves the last known state for up to `_MAX_STALE_POLLS` (3) consecutive transient failures before propagating, so entities don't flap to unavailable on a single blip. On the first refresh `self.data` is None, so a real setup failure still surfaces as `ConfigEntryNotReady`.
- Other statuses (403, unexpected code, empty/invalid body) → plain `UpdateFailed`, surfaced immediately.

### Two-zone detection (wine coolers only)

A wine cooler may have one or two cooling zones. Zone 2 entities are only created if `coordinator.data["temperature2"] is not None`. This check happens in each platform's `async_setup_entry` via `is_two_zone()` from `entity.py`. BBQ coolers skip this entirely (they branch on `coordinator.is_bbq` first).

### Light zones

For wine coolers, `light.py` creates a "Light" entity using `zone=0` (controls all zones in one API call). On two-zone devices it additionally creates "Light Zone 1" and "Light Zone 2" entities. `CasoAllZonesLightEntity` subclasses `CasoLightEntity` and overrides `is_on` to return `True` if any zone is on. A BBQ cooler gets a single "Light" entity (`data_key="light"`, zone ignored — the coordinator sends the BBQ payload).

### Entities

**Wine cooler:**

| Entity | Platform | `data_key` | Notes |
|---|---|---|---|
| Temperature Zone 1/2 | sensor | `temperature1/2` | Unit follows `temperatureUnit` field (°C/°F) |
| Target Temperature Zone 1/2 | sensor | `targetTemperature1/2` | Read-only, no SetTemperature API |
| Last Updated | sensor | `logTimestampUtc` | Timestamp of last device report; parsed as UTC-aware datetime |
| Power Zone 1/2 | binary_sensor | `power1/2` | — |
| Light / Light Zone 1/2 | light | `light1/2` | zone=0 controls all zones |

**BBQ cooler** (single zone, no target temperature):

| Entity | Platform | `data_key` | Notes |
|---|---|---|---|
| Temperature | sensor | `temperature` | Reported as a **string** — parsed to float via `_parse_float` |
| Last Updated | sensor | `logTimestampUtc` | Same as wine |
| Power | binary_sensor | `power` | — |
| Light | light | `light` | `POST BbqCooler/SetLight {light}` |
