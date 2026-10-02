"""DataUpdateCoordinator for the Kirk Hill Wind Farm integration.

One refresh fans out to a small set of cheap GETs (owner + site summary, owner
turbines, wind-speed, owner + site live readings) and exposes a single merged
snapshot to the entities. When
a £/MWh price is configured it also fetches the owner-scoped month-to-date and
year-to-date generation used by the revenue sensors (YTD is cached ~hourly).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GenerationPoint,
    GenerationResult,
    KirkhillAuthError,
    KirkhillClient,
    KirkhillError,
    KirkhillPasswordChangeRequired,
    KirkhillRateLimitError,
    Summary,
    Turbine,
    Window,
)
from .const import (
    CONF_PRICE,
    CONF_RANGE,
    CONF_SCAN_MINUTES,
    DEFAULT_RANGE,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    SCOPE_OWNER,
    SCOPE_SITE,
    SITE_TIME_ZONE,
)
from .revenue import month_to_date_bounds

_LOGGER = logging.getLogger(__name__)

# The YTD year-series changes slowly; refetch at most this often.
YTD_REFRESH_INTERVAL = timedelta(hours=1)

# Map a window bucket to its length in minutes, for turning the latest interval's
# energy (kWh) into an average power (W). Only the fallback path uses this; live
# power normally comes straight from `/current`.
_BUCKET_MINUTES = {"1m": 1, "10m": 10, "30m": 30, "1h": 60, "day": 1440}


def _retry_hint(err: KirkhillRateLimitError) -> str:
    """Render the server's Retry-After for a log line, or nothing if absent."""
    if err.retry_after is None:
        return ""
    return f" (retry after {err.retry_after}s)"


def _interval_power_w(result: GenerationResult) -> float | None:
    """Average power (W) over the most recent interval of a generation series."""
    if not result.series:
        return None
    kwh = result.series[-1].get("generation_kwh")
    if kwh is None:
        return None
    # An unknown or missing bucket must not be guessed: assuming 1 minute would
    # report a plausible but 10-1440x inflated power. Unknown beats wrong.
    minutes = _BUCKET_MINUTES.get(result.window.bucket)
    if minutes is None:
        return None
    return round(kwh * 60000 / minutes, 1)


def _site_day_start(timestamp: str | None) -> datetime | None:
    """Midnight (site time) of the day containing an API timestamp."""
    parsed = dt_util.parse_datetime(timestamp) if timestamp else None
    if parsed is None:
        return None
    tz = dt_util.get_time_zone(SITE_TIME_ZONE)
    local = parsed.astimezone(tz)
    return datetime.combine(local.date(), time.min, tzinfo=tz)


@dataclass(slots=True)
class KirkhillData:
    """Merged snapshot returned by one coordinator refresh."""

    summary_owner: Summary
    summary_site: Summary
    turbines: dict[str, Turbine]
    window: Window
    wind_speed_mps: float | None
    wind_speed_at: str | None
    # Live power (W) plus the owner's total generation so far today (kWh), from
    # `/current`. None on a transient failure.
    owner_power_w: float | None
    site_power_w: float | None
    owner_today_kwh: float | None
    # Start of the day `owner_today_kwh` covers, taken from the API's own clock
    # so the daily reset can't race the data across midnight.
    owner_today_since: datetime | None
    # Revenue inputs (price-independent; sensors apply the £/MWh price). None
    # when no price is configured or a revenue fetch failed transiently.
    price_gbp_per_mwh: float | None
    mtd_kwh: float | None
    ytd_series: list[GenerationPoint] | None


class KirkhillCoordinator(DataUpdateCoordinator[KirkhillData]):
    """Polls the API and holds the latest snapshot."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: KirkhillClient,
    ) -> None:
        scan_minutes = entry.options.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_minutes),
        )
        self.client = client
        self._ytd_series: list[GenerationPoint] | None = None
        self._ytd_fetched_at: datetime | None = None
        self._ytd_year: int | None = None

    @property
    def _range(self) -> str:
        return self.config_entry.options.get(CONF_RANGE, DEFAULT_RANGE)

    @property
    def _price(self) -> float | None:
        return self.config_entry.options.get(CONF_PRICE)

    async def _async_update_data(self) -> KirkhillData:
        rng = self._range
        try:
            summary_owner, summary_site, turbines, wind = await asyncio.gather(
                self.client.async_get_summary(SCOPE_OWNER, range_=rng),
                self.client.async_get_summary(SCOPE_SITE, range_=rng),
                self.client.async_get_turbines(SCOPE_OWNER, range_=rng),
                self.client.async_get_wind_speed(range_=rng),
            )
        except KirkhillAuthError as err:
            # 401 — trigger reauth so the user can supply a fresh key.
            raise ConfigEntryAuthFailed(str(err)) from err
        except KirkhillPasswordChangeRequired as err:
            # 423 — keys won't work until the dashboard password is changed.
            raise ConfigEntryAuthFailed(
                f"Change your Kirk Hill dashboard password, then reconfigure: {err}"
            ) from err
        except KirkhillRateLimitError as err:
            # 429 — the budget is per account and shared across every key on it,
            # so this can be someone else's traffic. Say so, because the obvious
            # fix (lengthen *this* poll interval) may not be the right one.
            raise UpdateFailed(
                f"Rate limited by the Kirk Hill API{_retry_hint(err)}. The limit "
                f"is per account and shared across all of its API keys."
            ) from err
        except KirkhillError as err:
            # Validation / transport / unexpected status — retry next interval.
            raise UpdateFailed(str(err)) from err

        (
            owner_power_w,
            site_power_w,
            owner_today_kwh,
            owner_today_since,
        ) = await self._async_fetch_power()

        price = self._price
        mtd_kwh, ytd_series = await self._async_fetch_revenue(price)

        latest = wind.series[-1] if wind.series else None
        return KirkhillData(
            summary_owner=summary_owner.summary,
            summary_site=summary_site.summary,
            turbines={t.id: t for t in turbines.turbines},
            window=summary_owner.window,
            wind_speed_mps=latest.get("wind_speed_mps") if latest else None,
            wind_speed_at=latest.get("timestamp") if latest else None,
            owner_power_w=owner_power_w,
            site_power_w=site_power_w,
            owner_today_kwh=owner_today_kwh,
            owner_today_since=owner_today_since
            if owner_today_kwh is not None
            else None,
            price_gbp_per_mwh=price,
            mtd_kwh=mtd_kwh,
            ytd_series=ytd_series,
        )

    async def _async_fetch_power(
        self,
    ) -> tuple[float | None, float | None, float | None, datetime | None]:
        """Live owner + site power (W), owner generation today (kWh) and its day.

        Reads `/current`. If that fails transiently, falls back to deriving the
        figures from the `range=today` generation series. Transient errors
        degrade to None; auth errors propagate to reauth.
        """
        try:
            owner_now, site_now = await asyncio.gather(
                self.client.async_get_current(SCOPE_OWNER),
                self.client.async_get_current(SCOPE_SITE),
            )
        except (KirkhillAuthError, KirkhillPasswordChangeRequired) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KirkhillError as err:
            _LOGGER.debug("Live readings failed, using today's series: %s", err)
        else:
            return (
                owner_now.summary.total_power_watts,
                site_now.summary.total_power_watts,
                owner_now.summary.total_generation_kwh_today,
                _site_day_start(owner_now.generated_at),
            )

        try:
            owner_gen, site_gen = await asyncio.gather(
                self.client.async_get_generation(SCOPE_OWNER, range_="today"),
                self.client.async_get_generation(SCOPE_SITE, range_="today"),
            )
        except (KirkhillAuthError, KirkhillPasswordChangeRequired) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KirkhillError as err:
            _LOGGER.warning("Power fetch failed (power/today sensors unknown): %s", err)
            return None, None, None, None
        return (
            _interval_power_w(owner_gen),
            _interval_power_w(site_gen),
            owner_gen.summary.total_generation_kwh,
            _site_day_start(owner_gen.window.from_),
        )

    async def _async_fetch_revenue(
        self, price: float | None
    ) -> tuple[float | None, list[GenerationPoint] | None]:
        """Fetch month-to-date kWh + the YTD year-series (only when priced).

        Auth failures propagate (key issues are global); other transient errors
        degrade gracefully so the rest of the sensors stay available.
        """
        if price is None:
            return None, None

        try:
            date_from, date_to = month_to_date_bounds()
            mtd = await self.client.async_get_summary(
                SCOPE_OWNER, range_="custom", date_from=date_from, date_to=date_to
            )
            mtd_kwh = mtd.summary.total_generation_kwh

            now = dt_util.utcnow()
            year = now.year
            stale = (
                self._ytd_series is None
                or self._ytd_year != year
                or self._ytd_fetched_at is None
                or (now - self._ytd_fetched_at) >= YTD_REFRESH_INTERVAL
            )
            if stale:
                generation = await self.client.async_get_generation(
                    SCOPE_OWNER, range_=str(year)
                )
                self._ytd_series = generation.series
                self._ytd_fetched_at = now
                self._ytd_year = year
        except (KirkhillAuthError, KirkhillPasswordChangeRequired) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except KirkhillError as err:
            _LOGGER.warning(
                "Revenue data fetch failed (sensors will be unknown): %s", err
            )
            return None, self._ytd_series

        return mtd_kwh, self._ytd_series
