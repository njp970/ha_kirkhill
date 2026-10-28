"""Shared test helpers: load the real captured API payloads from fixtures/."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import aioresponses.core
import pytest
from aiohttp import ClientResponse

FIXTURES = Path(__file__).parent / "fixtures"


_NEEDS_STREAM_WRITER = (
    "stream_writer" in inspect.signature(ClientResponse.__init__).parameters
)


class _CompatClientResponse(ClientResponse):
    """aioresponses 0.7.9 doesn't pass `stream_writer`, which aiohttp 3.14
    made a required argument. Supply a stub so the mocked responses build."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if _NEEDS_STREAM_WRITER:
            kwargs.setdefault("stream_writer", Mock(output_size=0))
        super().__init__(*args, **kwargs)


aioresponses.core.ClientResponse = _CompatClientResponse


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by filename (e.g. 'summary_owner.json')."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def fixture():
    """Return the load_fixture helper for use in tests."""
    return load_fixture
