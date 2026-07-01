"""Revenue sensor behaviour: unknown without a price, computed with one."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kirkhill.const import CONF_API_KEY, CONF_PRICE, DOMAIN, NAME

MTD = "sensor.kirk_hill_wind_farm_revenue_month_to_date"
YTD = "sensor.kirk_hill_wind_farm_revenue_year_to_date"


async def test_revenue_unknown_without_price(
    hass: HomeAssistant, mock_client, mock_entry
) -> None:
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(MTD).state == "unknown"
    ytd = hass.states.get(YTD)
    assert ytd.state == "unknown"
    assert "monthly" not in ytd.attributes
    # No price -> the month-to-date summary (range=custom) is never requested.
    assert not any(
        call.kwargs.get("range_") == "custom"
        for call in mock_client.async_get_summary.await_args_list
    )


async def test_revenue_with_price(hass: HomeAssistant, mock_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={CONF_API_KEY: "kh_test_key"},
        options={CONF_PRICE: 50.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Owner MTD generation fixture = 7.041 kWh -> 7.041/1000 * 50 = 0.35.
    mtd = hass.states.get(MTD)
    assert float(mtd.state) == 0.35
    assert mtd.attributes["device_class"] == "monetary"
    assert mtd.attributes["unit_of_measurement"] == "GBP"
    assert mtd.attributes["state_class"] == "total"

    ytd = hass.states.get(YTD)
    assert float(ytd.state) >= 0.0
    monthly = ytd.attributes["monthly"]
    assert len(monthly) == 12
    assert {"month", "generation_kwh", "revenue_gbp"} <= set(monthly[0])
    # The YTD year-series was requested (range_ = the current year).
    year = str(dt_util.utcnow().year)
    assert any(
        call.kwargs.get("range_") == year
        for call in mock_client.async_get_generation.await_args_list
    )
