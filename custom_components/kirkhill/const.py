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
CONF_PRICE = "price_gbp_per_mwh"

CURRENCY_GBP = "GBP"

DEFAULT_RANGE = "7d"
DEFAULT_SCAN_MINUTES = 5
DEFAULT_SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_MINUTES)
MIN_SCAN_MINUTES = 1
MAX_SCAN_MINUTES = 60

# Ranges offered in the options flow for the live (summary/turbine/wind) window.
# Sub-day ranges are rejected by the API (302), so they are intentionally absent.
ALLOWED_RANGES = ["today", "7d", "30d"]

# Turbine ids are constrained server-side to ^T[1-8]$
TURBINE_IDS = [f"T{i}" for i in range(1, 9)]

NAME = "Kirk Hill Wind Farm"
MANUFACTURER = "Kirk Hill Community Wind Farm"
MODEL_SITE = "Community Wind Farm"
MODEL_TURBINE = "Wind Turbine"
ATTRIBUTION = "Data provided by Kirk Hill Community Wind Farm"
