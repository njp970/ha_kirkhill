# Kirk Hill Wind Farm

Read-only Home Assistant integration for the Kirk Hill Community Wind Farm
dashboard API.

- Site + 8 turbine devices: generation (your share and whole-site), capacity
  factor, rotor speed, wind speed, and derived per-turbine running status.
- Optional revenue sensors (month-to-date + year-to-date) once you set a £/MWh
  price.
- Single cloud-polling coordinator, configurable interval and range, with
  reauthentication support.

Add your dashboard API key when prompted. Generation values are windowed
aggregates, so the generation sensors are intentionally **not** Energy-Dashboard
sources — see the README for details.
