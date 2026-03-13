# CASO Wine Cooler — Home Assistant Integration

> **Disclaimer:** This integration was generated with the assistance of AI (Claude by Anthropic). Use at your own risk.

Integrates CASO wine coolers into Home Assistant via the [CASO Smart Kitchen API](https://publickitchenapi.casoapp.com/swagger/index.html).

## Features

- Current temperature per zone (sensor)
- Target temperature per zone (sensor)
- Interior light control — all zones at once or individually (light)
- Power state per zone (binary sensor)
- Automatic single-zone / two-zone detection

> **Note:** The CASO API does not provide a temperature set endpoint. Target temperature is read-only.

## Installation

### Requirements

- [HACS](https://hacs.xyz) installed
- A CASO API key — get one at [casoapp.com/apikey](https://www.casoapp.com/apikey)

### Finding your Device ID

Go to [casoapp.com/devices](https://www.casoapp.com/devices), click the wrench icon next to your device and copy the Technical Device ID shown there.

### Add the repository

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/skolodziej/ha-caso_winecooler`
3. Category: **Integration** → **Add**
4. Install **CASO Wine Cooler** and restart Home Assistant

### Setup

1. **Settings → Integrations → + Add → CASO Wine Cooler**
2. Enter your API key
3. Select your device
4. Optionally adjust the polling interval (default: 600 s / 10 min)

## Rate limiting

The CASO API has an undocumented rate limit. The integration enforces a minimum of 15 seconds between requests and defaults to polling every 10 minutes. Light commands consume one request but update state immediately from the API response without an additional poll.
