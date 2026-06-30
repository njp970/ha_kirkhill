"""DataUpdateCoordinator for the Kirk Hill Wind Farm integration.

One refresh fans out to a small set of cheap GETs (owner + site summary, owner
turbines, wind-speed) and exposes a single merged snapshot to the entities.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    KirkhillAuthError,
    KirkhillClient,
    KirkhillError,
    KirkhillPasswordChangeRequired,
    Summary,
    Turbine,
    Window,
)
from .const import (
    CONF_RANGE,
    CONF_SCAN_MINUTES,
    DEFAULT_RANGE,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    SCOPE_OWNER,
    SCOPE_SITE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class KirkhillData:
    """Merged snapshot returned by one coordinator refresh."""

    summary_owner: Summary
    summary_site: Summary
    turbines: dict[str, Turbine]
    window: Window
    wind_speed_mps: float | None
    wind_speed_at: str | None


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

    @property
    def _range(self) -> str:
        return self.config_entry.options.get(CONF_RANGE, DEFAULT_RANGE)

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
        except KirkhillError as err:
            # Validation / transport / unexpected status — retry next interval.
            raise UpdateFailed(str(err)) from err

        latest = wind.series[-1] if wind.series else None
        return KirkhillData(
            summary_owner=summary_owner.summary,
            summary_site=summary_site.summary,
            turbines={t.id: t for t in turbines.turbines},
            window=summary_owner.window,
            wind_speed_mps=latest.get("wind_speed_mps") if latest else None,
            wind_speed_at=latest.get("timestamp") if latest else None,
        )
