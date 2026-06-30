"""Shared test helpers: load the real captured API payloads from fixtures/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by filename (e.g. 'summary_owner.json')."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixture():
    """Return the load_fixture helper for use in tests."""
    return load_fixture
