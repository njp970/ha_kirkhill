"""Sensor platform for Kirk Hill Wind Farm."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfSpeed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .api import Turbine
from .const import CURRENCY_GBP, TURBINE_IDS
from .coordinator import KirkhillCoordinator, KirkhillData
from .entity import KirkhillEntity, site_device_info, turbine_device_info
from .revenue import monthly_breakdown_from_series, revenue_gbp, ytd_total_gbp

# IMPORTANT — generation modelling.
# Generation values are WINDOWED AGGREGATES (kWh summed over the selected range),
# NOT a monotonic meter reading. They rise AND fall as the window slides, so the
# generation sensors use state_class MEASUREMENT (never TOTAL_INCREASING) and must
# NOT be added to the Energy Dashboard, which assumes an ever-increasing total and
# would mis-compute deltas. (The dedicated revenue sensors in Phase 2b are the
# correct, separately-windowed earnings figures.)
_GENERATION_STATE_CLASS = SensorStateClass.MEASUREMENT


def _parse_ts(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


@dataclass(frozen=True, kw_only=True)
class KirkhillSiteSensorDescription(SensorEntityDescription):
    """Site-level sensor description."""

    value_fn: Callable[[KirkhillData], StateType | datetime]


@dataclass(frozen=True, kw_only=True)
class KirkhillTurbineSensorDescription(SensorEntityDescription):
    """Per-turbine sensor description."""

    value_fn: Callable[[Turbine], StateType]


SITE_SENSORS: tuple[KirkhillSiteSensorDescription, ...] = (
    KirkhillSiteSensorDescription(
        key="generation_owner",
        translation_key="generation_owner",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=_GENERATION_STATE_CLASS,  # windowed aggregate — see note above
        value_fn=lambda d: d.summary_owner.total_generation_kwh,
    ),
    KirkhillSiteSensorDescription(
        key="generation_site",
        translation_key="generation_site",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=_GENERATION_STATE_CLASS,  # windowed aggregate — see note above
        value_fn=lambda d: d.summary_site.total_generation_kwh,
    ),
    KirkhillSiteSensorDescription(
        key="capacity_factor",
        translation_key="capacity_factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.summary_site.capacity_factor_percent,
    ),
    KirkhillSiteSensorDescription(
        key="active_turbines",
        translation_key="active_turbines",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.summary_site.active_turbines,
    ),
    KirkhillSiteSensorDescription(
        key="site_capacity",
        translation_key="site_capacity",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.summary_site.site_capacity_watts,
    ),
    KirkhillSiteSensorDescription(
        key="import_status",
        translation_key="import_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.summary_site.latest_import_status,
    ),
    KirkhillSiteSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.wind_speed_mps,
    ),
    KirkhillSiteSensorDescription(
        key="latest_interval",
        translation_key="latest_interval",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _parse_ts(d.summary_owner.latest_generation_interval_end),
    ),
)


TURBINE_SENSORS: tuple[KirkhillTurbineSensorDescription, ...] = (
    KirkhillTurbineSensorDescription(
        key="generation",
        translation_key="turbine_generation",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=_GENERATION_STATE_CLASS,  # windowed aggregate — see note above
        value_fn=lambda t: t.generation_kwh,
    ),
    KirkhillTurbineSensorDescription(
        key="share",
        translation_key="turbine_share",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda t: t.generation_share_percent,
    ),
    KirkhillTurbineSensorDescription(
        key="capacity_factor",
        translation_key="turbine_capacity_factor",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda t: t.capacity_factor_percent,
    ),
    KirkhillTurbineSensorDescription(
        key="rotor_speed",
        translation_key="turbine_rotor_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda t: t.latest_rotor_speed_rpm,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Kirk Hill sensors."""
    coordinator: KirkhillCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        KirkhillSiteSensor(coordinator, entry.entry_id, description)
        for description in SITE_SENSORS
    ]
    entities.append(KirkhillRevenueMonthToDateSensor(coordinator, entry.entry_id))
    entities.append(KirkhillRevenueYearToDateSensor(coordinator, entry.entry_id))
    for turbine_id in TURBINE_IDS:
        entities.extend(
            KirkhillTurbineSensor(coordinator, entry.entry_id, turbine_id, description)
            for description in TURBINE_SENSORS
        )
    async_add_entities(entities)


class KirkhillSiteSensor(KirkhillEntity, SensorEntity):
    """A site-level sensor."""

    entity_description: KirkhillSiteSensorDescription

    def __init__(
        self,
        coordinator: KirkhillCoordinator,
        entry_id: str,
        description: KirkhillSiteSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = site_device_info(entry_id)

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)


class KirkhillTurbineSensor(KirkhillEntity, SensorEntity):
    """A per-turbine sensor."""

    entity_description: KirkhillTurbineSensorDescription

    def __init__(
        self,
        coordinator: KirkhillCoordinator,
        entry_id: str,
        turbine_id: str,
        description: KirkhillTurbineSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._turbine_id = turbine_id
        self._attr_unique_id = f"{entry_id}_{turbine_id}_{description.key}"
        self._attr_device_info = turbine_device_info(entry_id, turbine_id)

    @property
    def available(self) -> bool:
        return super().available and self._turbine_id in self.coordinator.data.turbines

    @property
    def native_value(self) -> StateType:
        turbine = self.coordinator.data.turbines.get(self._turbine_id)
        if turbine is None:
            return None
        return self.entity_description.value_fn(turbine)


class KirkhillRevenueSensorBase(KirkhillEntity, SensorEntity):
    """Common config for the monetary revenue sensors (on the site device)."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = CURRENCY_GBP
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: KirkhillCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_device_info = site_device_info(entry_id)


class KirkhillRevenueMonthToDateSensor(KirkhillRevenueSensorBase):
    """Earnings so far this calendar month (owner share × £/MWh)."""

    _attr_translation_key = "revenue_month_to_date"

    def __init__(self, coordinator: KirkhillCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_revenue_month_to_date"

    @property
    def native_value(self) -> StateType:
        data = self.coordinator.data
        if data.price_gbp_per_mwh is None or data.mtd_kwh is None:
            return None
        return round(revenue_gbp(data.mtd_kwh, data.price_gbp_per_mwh), 2)


class KirkhillRevenueYearToDateSensor(KirkhillRevenueSensorBase):
    """Earnings year-to-date, plus a per-month breakdown attribute for the card."""

    _attr_translation_key = "revenue_year_to_date"

    def __init__(self, coordinator: KirkhillCoordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_revenue_year_to_date"

    @property
    def native_value(self) -> StateType:
        data = self.coordinator.data
        if data.price_gbp_per_mwh is None or data.ytd_series is None:
            return None
        breakdown = monthly_breakdown_from_series(
            data.ytd_series, data.price_gbp_per_mwh
        )
        return ytd_total_gbp(breakdown)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data
        if data.price_gbp_per_mwh is None or data.ytd_series is None:
            return None
        breakdown = monthly_breakdown_from_series(
            data.ytd_series, data.price_gbp_per_mwh
        )
        return {
            "monthly": [
                {
                    "month": item.month,
                    "generation_kwh": item.generation_kwh,
                    "revenue_gbp": item.revenue_gbp,
                }
                for item in breakdown
            ]
        }
