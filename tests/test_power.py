"""Tests for deriving average power from a generation series (fallback path)."""

from __future__ import annotations

import pytest

from custom_components.kirkhill.api import GenerationResult, Summary, Window
from custom_components.kirkhill.coordinator import _interval_power_w, _site_day_start


def _result(bucket: str | None, kwh: float | None) -> GenerationResult:
    return GenerationResult(
        window=Window.from_dict({"bucket": bucket} if bucket else {}),
        summary=Summary.from_dict({}),
        series=[{"timestamp": "2026-10-02T20:00:00Z", "generation_kwh": kwh}],
    )


@pytest.mark.parametrize(
    ("bucket", "kwh", "watts"),
    [
        ("1m", 0.03, 1800.0),
        ("10m", 0.3, 1800.0),
        ("30m", 0.9, 1800.0),
        ("1h", 1.8, 1800.0),
    ],
)
def test_known_buckets_scale_to_the_same_power(bucket, kwh, watts):
    assert _interval_power_w(_result(bucket, kwh)) == watts


@pytest.mark.parametrize("bucket", ["5m", "month", None])
def test_unknown_or_missing_bucket_is_unknown_not_guessed(bucket):
    # Regression: an unrecognised bucket used to fall back to 1 minute, so a
    # 1-hour interval read 60x too high with nothing to show it was wrong.
    assert _interval_power_w(_result(bucket, 1.8)) is None


def test_empty_series_or_null_value():
    assert _interval_power_w(_result("1m", None)) is None
    empty = _result("1m", 1.0)
    empty.series.clear()
    assert _interval_power_w(empty) is None


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        # 23:59 BST on 2 Oct is still 2 Oct on site, though 22:59 UTC.
        ("2026-10-02T22:59:00Z", "2026-10-02T00:00:00+01:00"),
        # 00:01 BST on 3 Oct is 23:01 UTC on 2 Oct: a new site day.
        ("2026-10-02T23:01:00Z", "2026-10-03T00:00:00+01:00"),
        # In winter (GMT) site midnight is UTC midnight.
        ("2026-12-10T08:00:00Z", "2026-12-10T00:00:00+00:00"),
        (None, None),
    ],
)
def test_site_day_start(timestamp, expected):
    result = _site_day_start(timestamp)
    assert (result.isoformat() if result else None) == expected
