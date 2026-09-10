"""The drift checker only works if it knows what the integration knows.

scripts/probe_api.py hard-codes the field sets it compares live responses
against. If a field is added to a dataclass in api.py but not to the probe, the
probe would report that field as NEW forever; if one is removed from api.py but
left in the probe, it would report it MISSING forever. Either way the checker
stops being trustworthy, which is exactly when it matters. These tests tie the
two together.
"""

from __future__ import annotations

import importlib.util
from dataclasses import fields
from pathlib import Path

import pytest

from custom_components.kirkhill.api import (
    Coordinates,
    GenerationPoint,
    Summary,
    Turbine,
    Window,
    WindSpeedPoint,
)
from custom_components.kirkhill.coordinator import _BUCKET_MINUTES


def _load_probe():
    """Import scripts/probe_api.py by path (it is a script, not a package)."""
    path = Path(__file__).parent.parent / "scripts" / "probe_api.py"
    spec = importlib.util.spec_from_file_location("probe_api", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def probe():
    return _load_probe()


def _dataclass_keys(cls) -> set[str]:
    """Field names as the API spells them (`from_` is `from` on the wire)."""
    return {"from" if f.name == "from_" else f.name for f in fields(cls)}


@pytest.mark.parametrize(
    ("const_name", "cls"),
    [
        ("WINDOW_KEYS", Window),
        ("SUMMARY_KEYS", Summary),
        ("TURBINE_KEYS", Turbine),
        ("COORDINATES_KEYS", Coordinates),
    ],
)
def test_probe_keys_match_dataclass(probe, const_name, cls):
    assert getattr(probe, const_name) == _dataclass_keys(cls)


@pytest.mark.parametrize(
    ("const_name", "typed_dict"),
    [
        ("GENERATION_POINT_KEYS", GenerationPoint),
        ("WIND_SPEED_POINT_KEYS", WindSpeedPoint),
    ],
)
def test_probe_series_keys_match_typed_dict(probe, const_name, typed_dict):
    assert getattr(probe, const_name) == set(typed_dict.__annotations__)


def test_probe_known_buckets_match_coordinator(probe):
    """A bucket the probe calls known must be one the power maths can convert."""
    assert set(_BUCKET_MINUTES) == probe.KNOWN_BUCKETS


def test_probe_endpoints_match_const(probe):
    """The probe must cover every endpoint the integration actually calls."""
    from custom_components.kirkhill import const

    integration_paths = {
        const.ENDPOINT_SUMMARY,
        const.ENDPOINT_GENERATION,
        const.ENDPOINT_WIND_SPEED,
        const.ENDPOINT_TURBINES,
    }
    assert set(probe.ENDPOINTS.values()) == integration_paths


def test_probe_known_ranges_match_options(probe):
    """Ranges offered in the options flow are the ones treated as known-good."""
    from custom_components.kirkhill import const

    assert probe.KNOWN_RANGES == const.ALLOWED_RANGES


def test_candidate_values_are_not_already_known(probe):
    """A 'candidate' that is already supported would be reported as NEW forever."""
    assert not set(probe.CANDIDATE_RANGES) & set(probe.KNOWN_RANGES)
    assert not set(probe.CANDIDATE_SCOPES) & set(probe.KNOWN_SCOPES)
    known_names = {p.rsplit("/", 1)[-1] for p in probe.ENDPOINTS.values()}
    assert not set(probe.CANDIDATE_ENDPOINTS) & known_names
