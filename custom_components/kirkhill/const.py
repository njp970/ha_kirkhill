"""Constants for the Kirk Hill Wind Farm integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "kirkhill"

BASE_URL = "https://dashboard.kirkhillcoop.org"
API_PREFIX = "/api/v1"

# Cloudflare fronts the dashboard and 403s the default aiohttp/urllib
# User-Agent (error code 1010). Always send an explicit UA on API calls.
USER_AGENT = "ha-kirkhill"

ENDPOINT_SUMMARY = f"{API_PREFIX}/summary"
ENDPOINT_GENERATION = f"{API_PREFIX}/generation"
ENDPOINT_WIND_SPEED = f"{API_PREFIX}/wind-speed"
ENDPOINT_TURBINES = f"{API_PREFIX}/turbines"

SCOPE_OWNER = "owner"
SCOPE_SITE = "site"

CONF_API_KEY = "api_key"
CONF_RANGE = "range"
CONF_SCAN_MINUTES = "scan_minutes"

DEFAULT_RANGE = "7d"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# Turbine ids are constrained server-side to ^T[1-8]$
TURBINE_IDS = [f"T{i}" for i in range(1, 9)]

MANUFACTURER = "Kirk Hill Community Wind Farm"
