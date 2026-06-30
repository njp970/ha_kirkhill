"""Unit tests for the Kirk Hill async API client, driven by real fixtures."""

from __future__ import annotations

import re

import aiohttp
import pytest
import pytest_asyncio
from aioresponses import aioresponses

from custom_components.kirkhill.api import (
    KirkhillApiError,
    KirkhillAuthError,
    KirkhillClient,
    KirkhillPasswordChangeRequired,
    KirkhillValidationError,
    Turbine,
)

BASE = "https://dashboard.kirkhillcoop.org"


def url_re(path: str) -> re.Pattern[str]:
    """Match a full endpoint URL regardless of query string."""
    return re.compile(rf"^{re.escape(BASE)}{re.escape(path)}(\?.*)?$")


def only_request(m: aioresponses):
    """Return the single RequestCall recorded by aioresponses."""
    calls = [c for calls in m.requests.values() for c in calls]
    assert len(calls) == 1, f"expected exactly one request, got {len(calls)}"
    return calls[0]


@pytest_asyncio.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield KirkhillClient("kh_test_key", session)


# --- Happy-path parsing ----------------------------------------------------


async def test_summary_owner_parsing(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), payload=fixture("summary_owner.json"))
        result = await client.async_get_summary()

    s = result.summary
    assert s.total_generation_kwh == 7.041
    assert s.capacity_factor_percent == 26.11
    assert s.active_turbines == 8
    assert s.site_capacity_watts == 18800000
    assert s.latest_import_status == "running"
    assert result.window.bucket == "1m"
    assert result.window.scope == "owner"
    assert result.window.timezone == "Europe/London"


async def test_summary_site_parsing(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), payload=fixture("summary_site.json"))
        result = await client.async_get_summary(scope="site")

    assert result.summary.total_generation_kwh == 55544
    assert result.summary.latest_import_status == "success"


async def test_generation_series_parsing(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/generation"), payload=fixture("generation_owner.json"))
        result = await client.async_get_generation()

    assert result.summary.total_generation_kwh > 0
    assert len(result.series) > 0
    point = result.series[0]
    assert "timestamp" in point and "generation_kwh" in point


async def test_wind_speed_parsing(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/wind-speed"), payload=fixture("wind_speed.json"))
        result = await client.async_get_wind_speed()

    assert len(result.series) > 0
    point = result.series[0]
    assert "timestamp" in point and "wind_speed_mps" in point


async def test_turbines_parsing(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/turbines"), payload=fixture("turbines_owner.json"))
        result = await client.async_get_turbines()

    assert [t.id for t in result.turbines] == [f"T{i}" for i in range(1, 9)]
    t1 = result.turbines[0]
    assert t1.is_running is True  # rpm 16.14 > 0
    assert t1.coordinates.openstreetmap_node_id == 12134002376
    assert t1.coordinates.latitude == pytest.approx(55.3047599)
    assert t1.coordinates.source == "OpenStreetMap"


# --- Request wiring (headers / params) -------------------------------------


async def test_sends_user_agent_and_auth(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), payload=fixture("summary_owner.json"))
        await client.async_get_summary()
        call = only_request(m)

    headers = call.kwargs["headers"]
    # Cloudflare blocks the default UA — this header must always be present.
    assert headers["User-Agent"] == "ha-kirkhill"
    assert headers["Authorization"] == "Bearer kh_test_key"


async def test_summary_sends_scope_and_default_range(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), payload=fixture("summary_owner.json"))
        await client.async_get_summary()
        params = only_request(m).kwargs["params"]

    assert params["scope"] == "owner"
    assert params["range"] == "7d"  # client default


async def test_wind_speed_omits_scope(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/wind-speed"), payload=fixture("wind_speed.json"))
        await client.async_get_wind_speed()
        params = only_request(m).kwargs["params"]

    # scope does not affect wind speed; it must not be sent.
    assert "scope" not in params


async def test_custom_range_sends_from_to(client, fixture):
    with aioresponses() as m:
        m.get(url_re("/api/v1/generation"), payload=fixture("generation_owner.json"))
        await client.async_get_generation(
            range_="custom",
            date_from="2026-06-01T00:00:00Z",
            date_to="2026-06-30T00:00:00Z",
        )
        params = only_request(m).kwargs["params"]

    assert params["range"] == "custom"
    assert params["from"] == "2026-06-01T00:00:00Z"
    assert params["to"] == "2026-06-30T00:00:00Z"


# --- Derived turbine status (pure, no network) -----------------------------


@pytest.mark.parametrize(
    ("rpm", "expected"),
    [(16.14, True), (0, False), (0.0, False), (None, None)],
)
def test_is_running_derivation(rpm, expected):
    turbine = Turbine.from_dict(
        {"id": "T1", "generation_kwh": 1.0, "latest_rotor_speed_rpm": rpm}
    )
    assert turbine.is_running is expected


# --- Error mapping ---------------------------------------------------------


async def test_401_maps_to_auth_error(client):
    with aioresponses() as m:
        m.get(
            url_re("/api/v1/summary"),
            status=401,
            payload={"message": "The API key is not valid."},
        )
        with pytest.raises(KirkhillAuthError, match="not valid"):
            await client.async_get_summary()


async def test_422_maps_to_validation_error(client):
    with aioresponses() as m:
        m.get(
            url_re("/api/v1/summary"),
            status=422,
            payload={"message": "Custom ranges require from and to timestamps."},
        )
        with pytest.raises(KirkhillValidationError, match="Custom ranges"):
            await client.async_get_summary(range_="custom")


async def test_423_maps_to_password_change_required(client):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), status=423, payload={"message": "x"})
        with pytest.raises(KirkhillPasswordChangeRequired):
            await client.async_get_summary()


async def test_500_maps_to_api_error(client):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), status=500, body="boom")
        with pytest.raises(KirkhillApiError):
            await client.async_get_summary()


async def test_redirect_maps_to_validation_error(client):
    # An invalid range 302-redirects to the dashboard instead of erroring.
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), status=302, headers={"Location": BASE})
        with pytest.raises(KirkhillValidationError, match="redirect"):
            await client.async_get_summary(range_="24h")


async def test_missing_data_key_maps_to_api_error(client):
    with aioresponses() as m:
        m.get(url_re("/api/v1/summary"), payload={"unexpected": True})
        with pytest.raises(KirkhillApiError, match="missing 'data'"):
            await client.async_get_summary()
