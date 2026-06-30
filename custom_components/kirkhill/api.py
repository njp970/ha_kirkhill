"""Async client for the Kirk Hill Wind Farm API.

First draft against the real OpenAPI schema. Claude Code will add tests and
refine error handling in Phase 1.

The API is read-only. Auth is `Authorization: Bearer <key>`; keys only work on
`/api/v1/*`. All response timestamps are UTC ISO-8601. Generation values are
WINDOWED AGGREGATES (kWh over the requested range), NOT a live meter — see
sensor modelling notes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    DEFAULT_RANGE,
    ENDPOINT_GENERATION,
    ENDPOINT_SUMMARY,
    ENDPOINT_TURBINES,
    ENDPOINT_WIND_SPEED,
    SCOPE_OWNER,
    USER_AGENT,
)


class KirkhillError(Exception):
    """Base error."""


class KirkhillAuthError(KirkhillError):
    """401 — missing, invalid, or revoked API key."""


class KirkhillPasswordChangeRequired(KirkhillError):
    """423 — dashboard user must change password before API keys work."""


class KirkhillValidationError(KirkhillError):
    """422 — invalid range or timestamp parameters."""


class KirkhillApiError(KirkhillError):
    """Other non-2xx or transport error."""


@dataclass(slots=True)
class Window:
    range: str
    from_: str
    to: str
    bucket: str
    scope: str
    timezone: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Window":
        return cls(
            range=d["range"],
            from_=d["from"],
            to=d["to"],
            bucket=d["bucket"],
            scope=d["scope"],
            timezone=d["timezone"],
        )


@dataclass(slots=True)
class Summary:
    total_generation_kwh: float
    capacity_factor_percent: float | None
    active_turbines: int
    site_capacity_watts: int
    latest_generation_interval_end: str | None
    latest_import_status: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Summary":
        return cls(
            total_generation_kwh=d["total_generation_kwh"],
            capacity_factor_percent=d.get("capacity_factor_percent"),
            active_turbines=d["active_turbines"],
            site_capacity_watts=d["site_capacity_watts"],
            latest_generation_interval_end=d.get("latest_generation_interval_end"),
            latest_import_status=d.get("latest_import_status"),
        )


@dataclass(slots=True)
class Coordinates:
    latitude: float | None
    longitude: float | None
    source: str | None
    openstreetmap_node_id: int | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Coordinates":
        return cls(
            latitude=d.get("latitude"),
            longitude=d.get("longitude"),
            source=d.get("source"),
            openstreetmap_node_id=d.get("openstreetmap_node_id"),
        )


@dataclass(slots=True)
class Turbine:
    id: str
    generation_kwh: float
    generation_share_percent: float | None
    capacity_factor_percent: float | None
    latest_generation_interval_end: str | None
    latest_rotor_speed_rpm: float | None
    latest_rotor_speed_at: str | None
    coordinates: Coordinates

    @property
    def is_running(self) -> bool | None:
        """Derived status: no explicit field exists in the API.

        running if rotor speed > 0; stopped if 0; unknown if null.
        """
        if self.latest_rotor_speed_rpm is None:
            return None
        return self.latest_rotor_speed_rpm > 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Turbine":
        return cls(
            id=d["id"],
            generation_kwh=d["generation_kwh"],
            generation_share_percent=d.get("generation_share_percent"),
            capacity_factor_percent=d.get("capacity_factor_percent"),
            latest_generation_interval_end=d.get("latest_generation_interval_end"),
            latest_rotor_speed_rpm=d.get("latest_rotor_speed_rpm"),
            latest_rotor_speed_at=d.get("latest_rotor_speed_at"),
            coordinates=Coordinates.from_dict(d.get("coordinates", {})),
        )


class KirkhillClient:
    """Thin async wrapper over the read-only endpoints."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        base_url: str = BASE_URL,
        default_range: str = DEFAULT_RANGE,
    ) -> None:
        self._api_key = api_key
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._default_range = default_range

    @property
    def _headers(self) -> dict[str, str]:
        # User-Agent is required: Cloudflare 403s the default aiohttp UA.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": USER_AGENT,
        }

    async def _get(self, path: str, **params: str) -> dict[str, Any]:
        query = {"range": self._default_range, **params}
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url, headers=self._headers, params=query
            ) as resp:
                if resp.status == 401:
                    raise KirkhillAuthError("Missing, invalid, or revoked API key.")
                if resp.status == 423:
                    raise KirkhillPasswordChangeRequired(
                        "Change your dashboard password before using API keys."
                    )
                if resp.status == 422:
                    raise KirkhillValidationError(
                        "Invalid range or timestamp parameters."
                    )
                if resp.status != 200:
                    text = await resp.text()
                    raise KirkhillApiError(f"HTTP {resp.status}: {text[:200]}")
                body = await resp.json()
        except aiohttp.ClientError as err:
            raise KirkhillApiError(str(err)) from err

        if "data" not in body:
            raise KirkhillApiError("Malformed response: missing 'data'.")
        return body["data"]

    async def async_get_summary(self, scope: str = SCOPE_OWNER) -> tuple[Window, Summary]:
        data = await self._get(ENDPOINT_SUMMARY, scope=scope)
        return Window.from_dict(data["window"]), Summary.from_dict(data["summary"])

    async def async_get_generation(
        self, scope: str = SCOPE_OWNER
    ) -> tuple[Window, Summary, list[dict[str, Any]]]:
        data = await self._get(ENDPOINT_GENERATION, scope=scope)
        return (
            Window.from_dict(data["window"]),
            Summary.from_dict(data["summary"]),
            data.get("series", []),
        )

    async def async_get_wind_speed(self) -> tuple[Window, list[dict[str, Any]]]:
        # scope does not affect wind speed; omit it.
        data = await self._get(ENDPOINT_WIND_SPEED)
        return Window.from_dict(data["window"]), data.get("series", [])

    async def async_get_turbines(self, scope: str = SCOPE_OWNER) -> tuple[Window, list[Turbine]]:
        data = await self._get(ENDPOINT_TURBINES, scope=scope)
        turbines = [Turbine.from_dict(t) for t in data.get("turbines", [])]
        return Window.from_dict(data["window"]), turbines
