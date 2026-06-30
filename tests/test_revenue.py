"""Unit tests for the revenue helpers (no Home Assistant needed)."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.kirkhill.revenue import (
    month_to_date_bounds,
    monthly_breakdown_from_series,
    revenue_gbp,
    ytd_total_gbp,
)


def test_revenue_gbp():
    assert revenue_gbp(1000, 50) == 50.0
    assert revenue_gbp(0, 50) == 0.0
    assert revenue_gbp(500, 80) == 40.0


def test_month_to_date_bounds():
    now = datetime(2026, 6, 30, 10, 19, 0, tzinfo=UTC)
    date_from, date_to = month_to_date_bounds(now)
    assert date_from == "2026-06-01T00:00:00Z"
    assert date_to == "2026-06-30T10:19:00Z"


def test_monthly_breakdown_sums_and_filters():
    series = [
        {"timestamp": "2026-01-15T00:00:00Z", "generation_kwh": 100.0},
        {"timestamp": "2026-02-10T00:00:00Z", "generation_kwh": 200.0},
        {"timestamp": "2026-02-20T00:00:00Z", "generation_kwh": 50.0},
        {"timestamp": "2025-12-31T00:00:00Z", "generation_kwh": 999.0},  # other year
        {"timestamp": None, "generation_kwh": 5.0},  # malformed, skipped
    ]
    breakdown = monthly_breakdown_from_series(series, 50, year=2026)

    assert len(breakdown) == 12
    assert breakdown[0].month == 1
    assert breakdown[0].generation_kwh == 100.0
    assert breakdown[0].revenue_gbp == 5.0  # 100 kWh / 1000 * 50
    assert breakdown[1].generation_kwh == 250.0  # Feb summed
    assert breakdown[11].generation_kwh == 0.0  # Dec (other-year point excluded)


def test_ytd_total_is_sum_of_months():
    series = [
        {"timestamp": "2026-03-01T00:00:00Z", "generation_kwh": 1000.0},
        {"timestamp": "2026-04-01T00:00:00Z", "generation_kwh": 2000.0},
    ]
    breakdown = monthly_breakdown_from_series(series, 50, year=2026)
    assert ytd_total_gbp(breakdown) == 150.0  # (1000+2000)/1000*50
