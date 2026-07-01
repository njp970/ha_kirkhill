"""Async client for the Kirk Hill Wind Farm API.

The API is read-only. Auth is `Authorization: Bearer <key>`; keys only work on
`/api/v1/*`. All response timestamps are UTC ISO-8601. Generation values are
WINDOWED AGGREGATES (kWh over the requested range), NOT a live meter — see the
sensor modelling notes in the integration.

Notes learned against the live API (Phase 0):
- Cloudflare fronts the dashboard and returns 403 "error code: 1010" for the
  default aiohttp/urllib User-Agent. We always send an explicit `User-Agent`.
- Valid `range` values are `today`, `7d`, `30d`, a 4-digit year, or `custom`
  (with `from`/`to`). An invalid range (e.g. a sub-day `24h`) is answered with a
  302 redirect to the dashboard, not a 422 — we disable redirects and surface
  that as a validation error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

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

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=30)


class KirkhillError(Exception):
    """Base error."""


class KirkhillAuthError(KirkhillError):
    """401 — missing, invalid, or revoked API key."""


class KirkhillPasswordChangeRequired(KirkhillError):
    """423 — dashboard user must change password before API keys work."""


class KirkhillValidationError(KirkhillError):
    """422 (or an invalid-range 3xx redirect) — bad range/timestamp params."""


class KirkhillApiError(KirkhillError):
    """Other non-2xx response or a transport/decode error."""


# --- Typed response models -------------------------------------------------


class GenerationPoint(TypedDict):
    """One point in a `/generation` series."""

    timestamp: str
    generation_kwh: float


class WindSpeedPoint(TypedDict):
    """One point in a `/wind-speed` series."""

    timestamp: str
    wind_speed_mps: float


@dataclass(slots=True)
class Window:
    """The resolved query window echoed by every endpoint.

    All fields use ``.get`` — the API has removed fields before (e.g. dropped
    ``timezone`` in mid-2026), and a missing field must never crash a poll.
    """

    range: str | None
    from_: str | None
    to: str | None
    bucket: str | None
    scope: str | None
    timezone: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Window:
        return cls(
            range=d.get("range"),
            from_=d.get("from"),
            to=d.get("to"),
            bucket=d.get("bucket"),
            scope=d.get("scope"),
            timezone=d.get("timezone"),
        )


@dataclass(slots=True)
class Summary:
    """Scoped totals block (shared by `/summary` and `/generation`)."""

    total_generation_kwh: float | None
    capacity_factor_percent: float | None
    active_turbines: int | None
    site_capacity_watts: int | None
    latest_generation_interval_end: str | None
    latest_import_status: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Summary:
        # Tolerant parsing: a missing field surfaces as None (entity unavailable)
        # rather than crashing the whole coordinator refresh.
        return cls(
            total_generation_kwh=d.get("total_generation_kwh"),
            capacity_factor_percent=d.get("capacity_factor_percent"),
            active_turbines=d.get("active_turbines"),
            site_capacity_watts=d.get("site_capacity_watts"),
            latest_generation_interval_end=d.get("latest_generation_interval_end"),
            latest_import_status=d.get("latest_import_status"),
        )


@dataclass(slots=True)
class Coordinates:
    """Turbine location; every field is nullable in the API."""

    latitude: float | None
    longitude: float | None
    source: str | None
    openstreetmap_node_id: int | None

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> Coordinates:
        d = d or {}
        return cls(
            latitude=d.get("latitude"),
            longitude=d.get("longitude"),
            source=d.get("source"),
            openstreetmap_node_id=d.get("openstreetmap_node_id"),
        )


@dataclass(slots=True)
class Turbine:
    """A single turbine (ids are server-constrained to ^T[1-8]$)."""

    id: str
    generation_kwh: float | None
    generation_share_percent: float | None
    capacity_factor_percent: float | None
    latest_generation_interval_end: str | None
    latest_rotor_speed_rpm: float | None
    latest_rotor_speed_at: str | None
    coordinates: Coordinates

    @property
    def is_running(self) -> bool | None:
        """Derived status — there is NO explicit status field in the API.

        running if rotor speed > 0; stopped if 0; unknown (None) if rpm is null.
        """
        if self.latest_rotor_speed_rpm is None:
            return None
        return self.latest_rotor_speed_rpm > 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Turbine:
        return cls(
            id=d.get("id", ""),
            generation_kwh=d.get("generation_kwh"),
            generation_share_percent=d.get("generation_share_percent"),
            capacity_factor_percent=d.get("capacity_factor_percent"),
            latest_generation_interval_end=d.get("latest_generation_interval_end"),
            latest_rotor_speed_rpm=d.get("latest_rotor_speed_rpm"),
            latest_rotor_speed_at=d.get("latest_rotor_speed_at"),
            coordinates=Coordinates.from_dict(d.get("coordinates")),
        )


@dataclass(slots=True)
class SummaryResult:
    window: Window
    summary: Summary


@dataclass(slots=True)
class GenerationResult:
    window: Window
    summary: Summary
    series: list[GenerationPoint]


@dataclass(slots=True)
class WindSpeedResult:
    window: Window
    series: list[WindSpeedPoint]


@dataclass(slots=True)
class TurbinesResult:
    window: Window
    turbines: list[Turbine]


# --- Client ----------------------------------------------------------------


class KirkhillClient:
    """Thin async wrapper over the read-only `/api/v1` endpoints."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        *,
        base_url: str = BASE_URL,
        default_range: str = DEFAULT_RANGE,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._default_range = default_range
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        # User-Agent is required: Cloudflare 403s the default aiohttp UA.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": USER_AGENT,
        }

    async def _get(
        self,
        path: str,
        *,
        scope: str | None = None,
        range_: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, Any]:
        """GET an endpoint and return its `data` object, raising typed errors."""
        params: dict[str, str] = {"range": range_ or self._default_range}
        if scope is not None:
            params["scope"] = scope
        if date_from is not None:
            params["from"] = date_from
        if date_to is not None:
            params["to"] = date_to

        url = f"{self._base_url}{path}"
        try:
            # allow_redirects=False: an invalid range 302-redirects to the
            # dashboard HTML instead of returning a 4xx; we treat that as a
            # validation error rather than letting it resolve to junk HTML.
            async with self._session.get(
                url,
                headers=self._headers,
                params=params,
                timeout=self._timeout,
                allow_redirects=False,
            ) as resp:
                status = resp.status
                if status == 401:
                    raise KirkhillAuthError(
                        await _message(resp, "Missing, invalid, or revoked API key.")
                    )
                if status == 423:
                    raise KirkhillPasswordChangeRequired(
                        await _message(
                            resp,
                            "Change your dashboard password before using API keys.",
                        )
                    )
                if status == 422:
                    raise KirkhillValidationError(
                        await _message(resp, "Invalid range or timestamp parameters.")
                    )
                if 300 <= status < 400:
                    raise KirkhillValidationError(
                        f"Unexpected redirect (HTTP {status}) — usually an "
                        f"invalid 'range' value: {params['range']!r}."
                    )
                if status != 200:
                    raise KirkhillApiError(
                        await _message(resp, f"Unexpected HTTP {status}.")
                    )
                try:
                    body = await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise KirkhillApiError(f"Malformed JSON response: {err}") from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise KirkhillApiError(f"Request to {path} failed: {err}") from err

        if not isinstance(body, dict) or "data" not in body:
            raise KirkhillApiError("Malformed response: missing 'data'.")
        return body["data"]

    async def async_get_summary(
        self,
        scope: str = SCOPE_OWNER,
        *,
        range_: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> SummaryResult:
        data = await self._get(
            ENDPOINT_SUMMARY,
            scope=scope,
            range_=range_,
            date_from=date_from,
            date_to=date_to,
        )
        return SummaryResult(
            window=Window.from_dict(data.get("window", {})),
            summary=Summary.from_dict(data.get("summary", {})),
        )

    async def async_get_generation(
        self,
        scope: str = SCOPE_OWNER,
        *,
        range_: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> GenerationResult:
        data = await self._get(
            ENDPOINT_GENERATION,
            scope=scope,
            range_=range_,
            date_from=date_from,
            date_to=date_to,
        )
        return GenerationResult(
            window=Window.from_dict(data.get("window", {})),
            summary=Summary.from_dict(data.get("summary", {})),
            series=data.get("series", []),
        )

    async def async_get_wind_speed(
        self, *, range_: str | None = None
    ) -> WindSpeedResult:
        # scope does not affect wind speed; omit it.
        data = await self._get(ENDPOINT_WIND_SPEED, range_=range_)
        return WindSpeedResult(
            window=Window.from_dict(data.get("window", {})),
            series=data.get("series", []),
        )

    async def async_get_turbines(
        self, scope: str = SCOPE_OWNER, *, range_: str | None = None
    ) -> TurbinesResult:
        data = await self._get(ENDPOINT_TURBINES, scope=scope, range_=range_)
        return TurbinesResult(
            window=Window.from_dict(data.get("window", {})),
            turbines=[Turbine.from_dict(t) for t in data.get("turbines", [])],
        )


async def _message(resp: aiohttp.ClientResponse, fallback: str) -> str:
    """Best-effort extraction of the API's `{"message": ...}` error text."""
    try:
        body = await resp.json()
    except (aiohttp.ClientError, ValueError):
        return fallback
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, str) and msg:
            return msg
    return fallback
