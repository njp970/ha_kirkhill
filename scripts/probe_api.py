#!/usr/bin/env python3
"""Drift check for the Kirk Hill Wind Farm API.

Calls the API with your own key and compares what comes back against the shapes
this integration knows about, so you can spot API changes *before* they either
break a poll or leave a new feature unused.

    export KIRKHILL_TOKEN="your-key"
    python scripts/probe_api.py

It reports four things:

* ``NEW``      — fields/endpoints the API returns that the integration ignores.
                 These are the candidate features worth wiring up.
* ``MISSING``  — fields the integration expects that the API no longer sends.
                 Tolerant parsing means these degrade to ``unknown`` rather than
                 crashing (see v0.2.2), but the affected entities are dead.
* ``buckets``  — the bucket each range resolves to. ``coordinator._BUCKET_MINUTES``
                 must know every one of these or the power sensors silently
                 scale wrong.
* extras       — ranges/scopes that used to be rejected and now work.

Exits non-zero if any drift is found, so it can be run on a schedule.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://dashboard.kirkhillcoop.org"
# Cloudflare in front of the dashboard blocks the default "Python-urllib/x"
# User-Agent with a 403 (error code 1010). Send an explicit UA so requests pass.
USER_AGENT = "ha-kirkhill/0.1 (+https://github.com/neilparkes/ha_kirkhill)"
API_PREFIX = "/api/v1"

ENDPOINTS = {
    "summary": f"{API_PREFIX}/summary",
    "generation": f"{API_PREFIX}/generation",
    "wind-speed": f"{API_PREFIX}/wind-speed",
    "turbines": f"{API_PREFIX}/turbines",
}

# --- What the integration currently understands -----------------------------
# Keep these in step with the dataclasses in custom_components/kirkhill/api.py;
# tests/test_probe_contract.py fails if they drift apart.

ENVELOPE_KEYS = {"data"}
WINDOW_KEYS = {"range", "from", "to", "bucket", "scope", "timezone"}
SUMMARY_KEYS = {
    "total_generation_kwh",
    "capacity_factor_percent",
    "active_turbines",
    "site_capacity_watts",
    "latest_generation_interval_end",
    "latest_import_status",
}
TURBINE_KEYS = {
    "id",
    "generation_kwh",
    "generation_share_percent",
    "capacity_factor_percent",
    "latest_generation_interval_end",
    "latest_rotor_speed_rpm",
    "latest_rotor_speed_at",
    "coordinates",
}
COORDINATES_KEYS = {"latitude", "longitude", "source", "openstreetmap_node_id"}
GENERATION_POINT_KEYS = {"timestamp", "generation_kwh"}
WIND_SPEED_POINT_KEYS = {"timestamp", "wind_speed_mps"}

# Top-level keys inside `data` for each endpoint.
DATA_KEYS = {
    "summary": {"window", "summary"},
    "generation": {"window", "summary", "series"},
    "wind-speed": {"window", "series"},
    "turbines": {"window", "turbines"},
}

# Buckets coordinator._BUCKET_MINUTES can convert to an average power.
KNOWN_BUCKETS = {"1m", "10m", "1h", "day"}

# Ranges/scopes the integration uses, plus ones previously rejected — a
# previously-invalid value that now returns 200 is a new API capability.
KNOWN_RANGES = ["today", "7d", "30d"]
CANDIDATE_RANGES = ["1h", "24h", "yesterday", "mtd", "ytd", "12m", "all"]
KNOWN_SCOPES = ["owner", "site"]
CANDIDATE_SCOPES = ["turbine", "all", "member"]

# Endpoint names worth probing for; a non-404 means something new exists.
CANDIDATE_ENDPOINTS = [
    "status",
    "health",
    "meta",
    "me",
    "account",
    "availability",
    "alerts",
    "events",
    "outages",
    "curtailment",
    "forecast",
    "prices",
    "tariff",
    "revenue",
    "earnings",
    "payments",
    "shares",
    "members",
    "documents",
    "weather",
    "wind-direction",
    "power",
]


def call(path: str, token: str, **params: str) -> tuple[int, dict | str]:
    """GET a path, returning (status, decoded body). Redirects are NOT followed.

    An invalid `range` is answered with a 302 to the dashboard HTML rather than
    a 4xx, so following redirects would turn a rejection into a bogus 200.
    """
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        with contextlib.suppress(json.JSONDecodeError):
            body = json.loads(body)
        return err.code, body
    except (urllib.error.URLError, json.JSONDecodeError) as err:
        return 0, f"{type(err).__name__}: {err}"


def diff(label: str, seen: set[str], known: set[str], findings: list[str]) -> None:
    """Record NEW/MISSING keys for one object against what we understand."""
    for key in sorted(seen - known):
        findings.append(f"NEW      {label}.{key} — not read by the integration")
    for key in sorted(known - seen):
        findings.append(f"MISSING  {label}.{key} — API no longer returns it")


def check_shapes(token: str, findings: list[str]) -> None:
    """Compare each endpoint's live response against the known shapes."""
    print("== response shapes ==")
    for name, path in ENDPOINTS.items():
        status, payload = call(path, token, range="today", scope="owner")
        if status != 200 or not isinstance(payload, dict):
            print(f"  {name}: HTTP {status} — {json.dumps(payload)[:200]}")
            findings.append(f"ERROR    {name} returned HTTP {status}")
            continue

        diff("<envelope>", set(payload), ENVELOPE_KEYS, findings)
        data = payload.get("data", {})
        diff(f"{name}.data", set(data), DATA_KEYS[name], findings)

        window = data.get("window", {})
        diff(f"{name}.window", set(window), WINDOW_KEYS, findings)

        if "summary" in data:
            diff(f"{name}.summary", set(data["summary"]), SUMMARY_KEYS, findings)

        if "series" in data and data["series"]:
            expected = (
                GENERATION_POINT_KEYS if name == "generation" else WIND_SPEED_POINT_KEYS
            )
            diff(f"{name}.series[]", set(data["series"][0]), expected, findings)

        if "turbines" in data and data["turbines"]:
            first = data["turbines"][0]
            diff(f"{name}.turbines[]", set(first), TURBINE_KEYS, findings)
            diff(
                f"{name}.turbines[].coordinates",
                set(first.get("coordinates") or {}),
                COORDINATES_KEYS,
                findings,
            )
            ids = [t.get("id") for t in data["turbines"]]
            print(f"  {name}: HTTP 200, {len(ids)} turbines {ids}")
            continue

        print(f"  {name}: HTTP 200")


def check_buckets(token: str, findings: list[str]) -> None:
    """Every bucket the API can return must be known to the power conversion."""
    print("\n== buckets per range ==")
    for rng in KNOWN_RANGES:
        status, payload = call(ENDPOINTS["generation"], token, range=rng, scope="owner")
        if status != 200 or not isinstance(payload, dict):
            print(f"  range={rng}: HTTP {status}")
            continue
        bucket = payload.get("data", {}).get("window", {}).get("bucket")
        flag = "" if bucket in KNOWN_BUCKETS else "   <-- UNKNOWN"
        print(f"  range={rng}: bucket={bucket}{flag}")
        if bucket not in KNOWN_BUCKETS:
            findings.append(
                f"NEW      bucket {bucket!r} (range={rng}) — add it to "
                f"coordinator._BUCKET_MINUTES or the power sensors scale wrong"
            )


def _verdict(status: int) -> str:
    """Describe a probe result, keeping 'unreachable' distinct from 'rejected'.

    `call` reports transport failures as status 0. Printing those as "rejected"
    would read like the API answered, so a firewalled run would look like a
    clean sweep of negatives rather than a run that never happened.
    """
    if status == 0:
        return "unreachable (no response)"
    if status == 200:
        return "accepted"
    return f"rejected (HTTP {status})"


def check_extras(token: str, findings: list[str]) -> None:
    """Look for ranges, scopes and endpoints that did not previously exist."""
    print("\n== candidate ranges ==")
    for rng in CANDIDATE_RANGES:
        status, _ = call(ENDPOINTS["summary"], token, range=rng, scope="owner")
        print(f"  range={rng}: {_verdict(status)}")
        if status == 200:
            findings.append(f"NEW      range={rng!r} is now accepted")

    print("\n== candidate scopes ==")
    for scope in CANDIDATE_SCOPES:
        status, _ = call(ENDPOINTS["summary"], token, range="today", scope=scope)
        print(f"  scope={scope}: {_verdict(status)}")
        if status == 200:
            findings.append(f"NEW      scope={scope!r} is now accepted")

    print("\n== candidate endpoints ==")
    for name in CANDIDATE_ENDPOINTS:
        path = f"{API_PREFIX}/{name}"
        status, _ = call(path, token, range="today", scope="owner")
        # 404 = absent. 401/423 are key problems, not evidence of an endpoint.
        if status in (0, 404, 401, 423):
            continue
        print(f"  {path}: HTTP {status}")
        if status == 200:
            findings.append(f"NEW      endpoint {path} exists and returns 200")


def main() -> int:
    token = os.environ.get("KIRKHILL_TOKEN")
    if not token:
        print("ERROR: set KIRKHILL_TOKEN first.", file=sys.stderr)
        return 1

    findings: list[str] = []
    check_shapes(token, findings)
    check_buckets(token, findings)
    check_extras(token, findings)

    print("\n== drift ==")
    if not findings:
        print("  none — the API matches what the integration understands.")
        return 0
    for line in findings:
        print(f"  {line}")
    print(f"\n{len(findings)} finding(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
