"""Diagnostics for the Kirk Hill Wind Farm integration (API key redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import KirkhillCoordinator

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: KirkhillCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "data": {
            "window": asdict(data.window),
            "summary_owner": asdict(data.summary_owner),
            "summary_site": asdict(data.summary_site),
            "wind_speed_mps": data.wind_speed_mps,
            "wind_speed_at": data.wind_speed_at,
            "owner_power_w": data.owner_power_w,
            "site_power_w": data.site_power_w,
            "price_gbp_per_mwh": data.price_gbp_per_mwh,
            "mtd_kwh": data.mtd_kwh,
            "ytd_series_points": len(data.ytd_series) if data.ytd_series else 0,
            "turbines": {tid: asdict(t) for tid, t in data.turbines.items()},
        },
    }
