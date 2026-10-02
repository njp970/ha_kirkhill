"""Tests for deriving average power from a generation series (fallback path)."""

from __future__ import annotations

import pytest

from custom_components.kirkhill.api import GenerationResult, Summary, Window
from custom_components.kirkhill.coordinator import _interval_power_w


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
