# Kirk Hill Wind Farm — Home Assistant integration

[![hacs][hacs-badge]][hacs] [![CI][ci-badge]][ci]

A read-only Home Assistant integration for the [Kirk Hill Community Wind
Farm][kirkhill] dashboard API. It exposes your-share and whole-site generation,
per-turbine status, wind speed, and optional revenue estimates — all from a
single cloud-polling coordinator.

> **Not affiliated with Kirk Hill Co-op.** This is a community integration that
> reads the dashboard's public `/api/v1` endpoints with your personal API key.

## Features

- **Site device** with: owner generation, whole-site generation, live owner and
  site power, owner generation today, CO₂ avoided (your share and whole-site),
  capacity factor, active turbines, site capacity, data-import status, wind
  speed, and a "latest data interval" timestamp.
- **8 turbine devices**, each with generation, generation share, capacity factor
  and rotor-speed sensors, plus a **Running** binary sensor derived from rotor
  rpm (the API has no explicit status field). Each turbine's running sensor also
  carries its coordinates and OpenStreetMap node id as attributes.
- **Optional revenue sensors** — month-to-date and year-to-date earnings (with a
  12-month breakdown attribute), once you set your £/MWh price.
- A configurable poll interval and data range, and full reauthentication support.

### ⚠️ A note on the generation sensors

Most generation figures from this API are **windowed aggregates** (kWh summed
over the selected range), not a meter. The value rises *and* falls as the window
slides, so the owner, site and per-turbine generation sensors are
`state_class: measurement` with no energy device class, and **should not be
added to the Energy Dashboard**. Use the revenue sensors for earnings figures.

**Owner generation today** is different: it is a daily meter (an energy sensor
with `state_class: total` that resets at midnight UK time), so it **can** be
added to the Energy Dashboard as a source of your share of the farm's output.

Upgrading from v0.3.0 or earlier: "Owner generation today" used to be a
`measurement`. Home Assistant converts its long-term statistics to a running
total at the next statistics run, with no repair needed; history before the
upgrade keeps its old min/mean/max form.

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
| Polling interval | 5 min | 1–60 minutes. Each refresh makes 6–8 requests; the API allows 120/min **per account**, shared across every key on it. |
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

## Example dashboard

A ready-made dashboard lives in [`examples/dashboard.yaml`](examples/dashboard.yaml)
— turbine map, your-share and whole-site figures, gauges, per-turbine status, and
a year-to-date revenue chart. It uses [Mushroom](https://github.com/piitaya/lovelace-mushroom),
[ApexCharts](https://github.com/RomRider/apexcharts-card) and the
[kirkhill-card](https://github.com/njp970/kirkhill-card) (all installable via HACS).

To use it: **Settings → Dashboards → Add dashboard → New dashboard from scratch**,
open it, then **⋮ → Edit dashboard → ⋮ → Raw configuration editor**, and paste the
file. Entity IDs assume the integration's default names.

## Icon

The integration ships its own brand icon in [`custom_components/kirkhill/brand/`](custom_components/kirkhill/brand/)
(`icon.png` / `icon@2x.png`). Since Home Assistant 2026.3, custom integrations
provide brand images this way and they take priority over the brands CDN — no
[home-assistant/brands][brands] submission is needed.

## Development

```bash
uv venv --python 3.13 .venv
VIRTUAL_ENV=.venv uv pip install -r requirements-test.txt
.venv/bin/python -m pytest -q      # 76 tests
uvx ruff check . && uvx ruff format --check .
```

### Checking the API for drift

The API is undocumented and has changed under us before — it silently dropped
`window.timezone` in mid-2026, which broke every entity until v0.2.2. To check
whether it has gained or lost anything since:

```bash
export KIRKHILL_TOKEN="your-api-key"
python scripts/probe_api.py
```

It compares the live responses against the shapes in `api.py` and reports:

- **NEW** fields, ranges, scopes or endpoints the integration doesn't use yet —
  these are the candidate features to wire up.
- **UNUSED** endpoints that [the API docs](https://dashboard.kirkhillcoop.org/api-docs)
  document but the integration never calls, printed with their field shapes so
  they can be modelled without guessing (currently none: `/current` drives the
  power sensors, and `/carbon-avoided` duplicates the CO₂ figure `/summary`
  already returns).
- **MISSING** fields the API no longer returns. Parsing is tolerant so these
  degrade to `unknown` rather than crashing, but the affected entities are dead.
- The **bucket** each range resolves to. Power comes from `/current`; if that
  fails, it is derived from the today series, and a bucket missing from
  `coordinator._BUCKET_MINUTES` then leaves power `unknown` rather than wrong.

Fields the integration deliberately doesn't read (duplicates in other units,
or detail with no sensor) are listed in `IGNORED_KEYS` so they don't report as
NEW on every run.

It exits non-zero when it finds drift, so it can be run on a schedule.
`tests/test_probe_contract.py` keeps the script's expectations tied to the real
dataclasses, so the checker can't quietly go stale.

[kirkhill]: https://dashboard.kirkhillcoop.org
[brands]: https://github.com/home-assistant/brands
[hacs]: https://github.com/hacs/integration
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[ci]: https://github.com/njp970/ha_kirkhill/actions/workflows/ci.yml
[ci-badge]: https://github.com/njp970/ha_kirkhill/actions/workflows/ci.yml/badge.svg
