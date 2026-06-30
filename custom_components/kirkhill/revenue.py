"""Revenue estimation helpers for the Kirk Hill integration.

Earnings = your-share generation (kWh) / 1000 * negotiated price (GBP/MWh).

The API key holder's owner-scoped generation is ALREADY scaled to their share,
so we use scope=owner totals directly — no extra share maths.

All API timestamps are UTC ISO-8601. Month/year boundaries below are computed in
UTC for simplicity; if you later want them aligned to Europe/London calendar
days (matching the dashboard's named ranges), swap in a tz-aware "now".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

KWH_PER_MWH = 1000.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime) -> str:
    """ISO-8601 with a trailing Z, as the API expects for custom ranges."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_to_date_bounds(now: datetime | None = None) -> tuple[str, str]:
    """(from, to) for the current calendar month so far, as API timestamps."""
    now = now or _utc_now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return iso_z(start), iso_z(now)


def revenue_gbp(generation_kwh: float, price_gbp_per_mwh: float) -> float:
    """Convert a kWh figure + £/MWh price into £ earnings."""
    return (generation_kwh / KWH_PER_MWH) * price_gbp_per_mwh


@dataclass(slots=True)
class MonthlyRevenue:
    """One bar in the year-to-date chart."""

    month: int          # 1-12
    generation_kwh: float
    revenue_gbp: float


def monthly_breakdown_from_series(
    series: list[dict],
    price_gbp_per_mwh: float,
    *,
    year: int | None = None,
) -> list[MonthlyRevenue]:
    """Sum a generation time series into 12 monthly revenue bars.

    `series` is the `/generation` `series[]` for a full-year range, where each
    item is {"timestamp": ISO-8601, "generation_kwh": float}. With a year-long
    range the API buckets to "day"; summing days into months happens here.

    Only months up to the current month are populated for the current year;
    future months come back as zero so the card can render a full 12-bar axis.
    """
    year = year or _utc_now().year
    kwh_by_month: dict[int, float] = {m: 0.0 for m in range(1, 13)}

    for point in series:
        ts = point.get("timestamp")
        kwh = point.get("generation_kwh")
        if ts is None or kwh is None:
            continue
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.year != year:
            continue
        kwh_by_month[dt.month] += kwh

    return [
        MonthlyRevenue(
            month=m,
            generation_kwh=round(kwh_by_month[m], 3),
            revenue_gbp=round(revenue_gbp(kwh_by_month[m], price_gbp_per_mwh), 2),
        )
        for m in range(1, 13)
    ]


def ytd_total_gbp(breakdown: list[MonthlyRevenue]) -> float:
    return round(sum(b.revenue_gbp for b in breakdown), 2)
