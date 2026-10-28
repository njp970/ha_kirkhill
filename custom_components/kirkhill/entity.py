"""Shared entity base + device-info helpers for Kirk Hill entities."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTRIBUTION,
    DOMAIN,
    MANUFACTURER,
    MODEL_SITE,
    MODEL_TURBINE,
    NAME,
)
from .coordinator import KirkhillCoordinator


def _site_device_fields(entry_id: str) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, f"{entry_id}_site")},
        "name": NAME,
        "manufacturer": MANUFACTURER,
        "model": MODEL_SITE,
    }


def site_device_info(entry_id: str) -> DeviceInfo:
    """Device representing the whole wind farm."""
    return DeviceInfo(**_site_device_fields(entry_id))


def async_register_site_device(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Register the site device up front and return its device registry id.

    Turbine devices link to it through `via_device_id`, which needs the
    registry id rather than the identifier tuple the old `via_device` took.
    """
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **_site_device_fields(entry.entry_id)
    )
    return device.id


def turbine_device_info(
    entry_id: str, turbine_id: str, site_device_id: str
) -> DeviceInfo:
    """Device for a single turbine, nested under the site device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{turbine_id}")},
        name=f"Turbine {turbine_id}",
        manufacturer=MANUFACTURER,
        model=MODEL_TURBINE,
        via_device_id=site_device_id,
    )


class KirkhillEntity(CoordinatorEntity[KirkhillCoordinator]):
    """Base for all Kirk Hill entities."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
