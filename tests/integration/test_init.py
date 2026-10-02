"""Setup / entity / unload / error-handling tests."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.kirkhill.api import KirkhillApiError, KirkhillAuthError

# 13 site sensors (incl. 2 power, today, 2 CO2) + 2 revenue + (4*8 turbine) + 8 binary
EXPECTED_ENTITIES = 13 + 2 + 32 + 8
# 1 site device + 8 turbine devices
EXPECTED_DEVICES = 9


async def test_setup_creates_entities_and_devices(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.LOADED

    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(ent_reg, mock_entry.entry_id)
    assert len(entities) == EXPECTED_ENTITIES

    dev_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, mock_entry.entry_id)
    assert len(devices) == EXPECTED_DEVICES


async def test_entity_values_and_modelling(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    # Owner generation value comes from the owner-scoped summary fixture.
    owner_gen = hass.states.get("sensor.kirk_hill_wind_farm_owner_generation")
    assert owner_gen is not None
    assert float(owner_gen.state) == 30.283
    # CRITICAL: must be a measurement, never total_increasing.
    # Windowed aggregate: measurement, and no energy device class (HA rejects
    # energy + measurement, and a sliding window is not a total).
    assert owner_gen.attributes["state_class"] == "measurement"
    assert "device_class" not in owner_gen.attributes
    assert owner_gen.attributes["unit_of_measurement"] == "kWh"

    # T1 is running (rpm 16.14 > 0) and exposes coordinates for the card.
    t1 = hass.states.get("binary_sensor.turbine_t1_running")
    assert t1 is not None
    assert t1.state == STATE_ON
    assert t1.attributes["openstreetmap_node_id"] == 12134002376
    assert t1.attributes["latitude"] is not None

    # Live power comes straight from /current, in W.
    power = hass.states.get("sensor.kirk_hill_wind_farm_owner_power")
    assert power is not None
    assert power.attributes["device_class"] == "power"
    assert power.attributes["unit_of_measurement"] == "W"
    assert float(power.state) == 1910.525
    site_power = hass.states.get("sensor.kirk_hill_wind_farm_site_power")
    assert float(site_power.state) == 15072000
    # Generation today is a daily meter: energy / total, reset at site midnight
    # of the day the API computed it in (generated_at 2026-10-02T20:23:48Z).
    today = hass.states.get("sensor.kirk_hill_wind_farm_owner_generation_today")
    assert float(today.state) == 30.283
    assert today.attributes["device_class"] == "energy"
    assert today.attributes["state_class"] == "total"
    assert today.attributes["last_reset"] == "2026-10-02T00:00:00+01:00"

    co2 = hass.states.get("sensor.kirk_hill_wind_farm_owner_co2_avoided")
    assert float(co2.state) == 3.196
    assert co2.attributes["unit_of_measurement"] == "kg"
    assert co2.attributes["state_class"] == "measurement"
    site_co2 = hass.states.get("sensor.kirk_hill_wind_farm_site_co2_avoided")
    assert float(site_co2.state) == 25209.85


async def test_power_falls_back_to_today_series(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    """If /current fails transiently, power is derived from today's series."""
    mock_client.async_get_current.side_effect = KirkhillApiError("503")
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.LOADED
    power = hass.states.get("sensor.kirk_hill_wind_farm_owner_power")
    assert power.state not in ("unknown", "unavailable")
    assert float(power.state) >= 0


async def test_unload(hass: HomeAssistant, mock_client, mock_entry) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED


async def test_auth_error_triggers_reauth(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    mock_client.async_get_summary.side_effect = KirkhillAuthError("401")
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
    flows = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == "reauth"
    ]
    assert len(flows) == 1


async def test_no_invalid_state_class_warnings(
    hass: HomeAssistant, mock_client, mock_entry, caplog
) -> None:
    """HA warns when a device class is paired with an impossible state class."""
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert "is using state class" not in caplog.text
