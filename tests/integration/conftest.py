"""Fixtures for the Home Assistant integration tests (mocked API client)."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kirkhill.api import (
    GenerationResult,
    Summary,
    SummaryResult,
    Turbine,
    TurbinesResult,
    Window,
    WindSpeedResult,
)
from custom_components.kirkhill.const import (
    CONF_API_KEY,
    DOMAIN,
    NAME,
    SCOPE_SITE,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _summary_result(name: str) -> SummaryResult:
    data = _load(name)["data"]
    return SummaryResult(
        window=Window.from_dict(data["window"]),
        summary=Summary.from_dict(data["summary"]),
    )


def _turbines_result(name: str) -> TurbinesResult:
    data = _load(name)["data"]
    return TurbinesResult(
        window=Window.from_dict(data["window"]),
        turbines=[Turbine.from_dict(t) for t in data["turbines"]],
    )


def _wind_result(name: str) -> WindSpeedResult:
    data = _load(name)["data"]
    return WindSpeedResult(
        window=Window.from_dict(data["window"]),
        series=data.get("series", []),
    )


def _generation_result(name: str) -> GenerationResult:
    data = _load(name)["data"]
    return GenerationResult(
        window=Window.from_dict(data["window"]),
        summary=Summary.from_dict(data["summary"]),
        series=data.get("series", []),
    )


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Allow loading the kirkhill custom component in tests."""
    yield


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """A mocked KirkhillClient returning the captured fixtures."""
    client = MagicMock()
    owner = _summary_result("summary_owner.json")
    site = _summary_result("summary_site.json")

    async def _get_summary(scope: str = "owner", **_: Any) -> SummaryResult:
        return site if scope == SCOPE_SITE else owner

    client.async_get_summary = AsyncMock(side_effect=_get_summary)
    client.async_get_turbines = AsyncMock(
        return_value=_turbines_result("turbines_owner.json")
    )
    client.async_get_wind_speed = AsyncMock(
        return_value=_wind_result("wind_speed.json")
    )
    client.async_get_generation = AsyncMock(
        return_value=_generation_result("generation_owner.json")
    )

    with (
        patch("custom_components.kirkhill.KirkhillClient", return_value=client),
        patch(
            "custom_components.kirkhill.config_flow.KirkhillClient",
            return_value=client,
        ),
    ):
        yield client


@pytest.fixture
def mock_entry(hass) -> MockConfigEntry:
    """A config entry already attached to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        data={CONF_API_KEY: "kh_test_key"},
        options={},
    )
    entry.add_to_hass(hass)
    return entry
