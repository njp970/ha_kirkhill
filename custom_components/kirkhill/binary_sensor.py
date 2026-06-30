"""Binary sensor platform: per-turbine running status (derived from rotor rpm)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import TURBINE_IDS
from .coordinator import KirkhillCoordinator
from .entity import KirkhillEntity, turbine_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kirk Hill binary sensors (one running sensor per turbine)."""
    coordinator: KirkhillCoordinator = entry.runtime_data
    async_add_entities(
        KirkhillTurbineRunningSensor(coordinator, entry.entry_id, turbine_id)
        for turbine_id in TURBINE_IDS
    )


class KirkhillTurbineRunningSensor(KirkhillEntity, BinarySensorEntity):
    """Running/stopped for a turbine, derived from `latest_rotor_speed_rpm`.

    There is no explicit status field in the API: on if rpm > 0, off if 0,
    unknown if rpm is null.
    """

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "turbine_running"

    def __init__(
        self,
        coordinator: KirkhillCoordinator,
        entry_id: str,
        turbine_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._turbine_id = turbine_id
        self._attr_unique_id = f"{entry_id}_{turbine_id}_running"
        self._attr_device_info = turbine_device_info(entry_id, turbine_id)

    @property
    def available(self) -> bool:
        return super().available and self._turbine_id in self.coordinator.data.turbines

    @property
    def is_on(self) -> bool | None:
        turbine = self.coordinator.data.turbines.get(self._turbine_id)
        return turbine.is_running if turbine else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose location + rotor detail for the map card to consume."""
        turbine = self.coordinator.data.turbines.get(self._turbine_id)
        if turbine is None:
            return None
        coords = turbine.coordinates
        return {
            "turbine_id": turbine.id,
            "latitude": coords.latitude,
            "longitude": coords.longitude,
            "openstreetmap_node_id": coords.openstreetmap_node_id,
            "rotor_speed_rpm": turbine.latest_rotor_speed_rpm,
            "rotor_speed_at": turbine.latest_rotor_speed_at,
            "latest_generation_interval_end": turbine.latest_generation_interval_end,
        }
