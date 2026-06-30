"""Setup / entity / unload / error-handling tests."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.kirkhill.api import KirkhillAuthError

# 8 site sensors + 2 revenue sensors + (4 sensors * 8 turbines) + 8 binary_sensors
EXPECTED_ENTITIES = 8 + 2 + 32 + 8
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
    assert float(owner_gen.state) == 7.041
    # CRITICAL: must be a measurement, never total_increasing.
    assert owner_gen.attributes["state_class"] == "measurement"
    assert owner_gen.attributes["device_class"] == "energy"

    # T1 is running (rpm 16.14 > 0) and exposes coordinates for the card.
    t1 = hass.states.get("binary_sensor.turbine_t1_running")
    assert t1 is not None
    assert t1.state == STATE_ON
    assert t1.attributes["openstreetmap_node_id"] == 12134002376
    assert t1.attributes["latitude"] is not None


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
