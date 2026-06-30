# Kirk Hill Wind Farm — Home Assistant integration

[![hacs][hacs-badge]][hacs] [![CI][ci-badge]][ci]

A read-only Home Assistant integration for the [Kirk Hill Community Wind
Farm][kirkhill] dashboard API. It exposes your-share and whole-site generation,
per-turbine status, wind speed, and optional revenue estimates — all from a
single cloud-polling coordinator.

> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public `/api/v1` endpoints with your personal API key.

## Features

- **Site device** with: owner generation, whole-site generation, capacity
  factor, active turbines, site capacity, data-import status, wind speed, and a
  "latest data interval" timestamp.
- **8 turbine devices**, each with generation, generation share, capacity factor
  and rotor-speed sensors, plus a **Running** binary sensor derived from rotor
  rpm (the API has no explicit status field). Each turbine's running sensor also
  carries its coordinates and OpenStreetMap node id as attributes.
- **Optional revenue sensors** — month-to-date and year-to-date earnings (with a
  12-month breakdown attribute), once you set your £/MWh price.
- A configurable poll interval and data range, and full reauthentication support.

### ⚠️ A note on the generation sensors

Generation figures from this API are **windowed aggregates** (kWh summed over the
selected range), not a monotonic meter. The value rises *and* falls as the window
slides, so the generation sensors are modelled as `state_class: measurement` and
**should not be added to the Energy Dashboard** (which assumes an ever-increasing
total). Use the revenue sensors for earnings figures.

## Installation

### HACS (recommended)

1. In HACS → **Integrations** → ⋮ → **Custom repositories**, add
   `https://github.com/njp970/ha_kirkhill` with category **Integration**.
2. Install **Kirk Hill Wind Farm**, then restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Kirk Hill Wind Farm**.

### Manual

Copy `custom_components/kirkhill` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

You'll need an API key from your Kirk Hill dashboard (it works only against the
`/api/v1/*` endpoints and is used read-only).

After adding the integration, open its **Configure** dialog to set:

| Option | Default | Notes |
| --- | --- | --- |
| Polling interval | 5 min | 1–60 minutes |
| Default range | `7d` | `today`, `7d`, or `30d` for the live figures |
| Price (GBP per MWh) | _unset_ | Your negotiated price. Leave blank to disable revenue sensors. |

## Revenue sensors

Your owner-scoped generation is already scaled to your share, so earnings are
simply `kWh ÷ 1000 × £/MWh`. Set a price in the options to enable:

- `sensor.kirk_hill_wind_farm_revenue_month_to_date`
- `sensor.kirk_hill_wind_farm_revenue_year_to_date` — its `monthly` attribute
  holds a 12-element `{month, generation_kwh, revenue_gbp}` breakdown.

With no price set, these report `unknown` (not an error), and the year-series
call is skipped entirely.

## Companion card

A dedicated Lovelace card (`kirkhill-card`) renders the turbine map, status
table, spinning rotor icons, and the revenue bar chart. See its repository for
install steps.

## Brands / logo

To show an icon and logo in Home Assistant, the `kirkhill` domain needs to be
submitted to [home-assistant/brands][brands]. This is optional and can be done
after the first release; until then the integration uses a default icon.

## Development

```bash
uv venv --python 3.13 .venv
VIRTUAL_ENV=.venv uv pip install -r requirements-test.txt
.venv/bin/python -m pytest -q      # 37 tests
uvx ruff check . && uvx ruff format --check .
```

[kirkhill]: https://dashboard.kirkhillcoop.org
[brands]: https://github.com/home-assistant/brands
[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[ci]: https://github.com/njp970/ha_kirkhill/actions/workflows/ci.yml
[ci-badge]: https://github.com/njp970/ha_kirkhill/actions/workflows/ci.yml/badge.svg
