"""Shared entity base + device-info helpers for Kirk Hill entities."""

from __future__ import annotations

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


def site_device_info(entry_id: str) -> DeviceInfo:
    """Device representing the whole wind farm."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_site")},
        name=NAME,
        manufacturer=MANUFACTURER,
        model=MODEL_SITE,
    )


def turbine_device_info(entry_id: str, turbine_id: str) -> DeviceInfo:
    """Device for a single turbine, nested under the site device."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{turbine_id}")},
        name=f"Turbine {turbine_id}",
        manufacturer=MANUFACTURER,
        model=MODEL_TURBINE,
        via_device=(DOMAIN, f"{entry_id}_site"),
    )


class KirkhillEntity(CoordinatorEntity[KirkhillCoordinator]):
    """Base for all Kirk Hill entities."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
