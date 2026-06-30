#!/usr/bin/env python3
"""Phase 0 smoke test for the Kirk Hill Wind Farm API.

Reads the token from the KIRKHILL_TOKEN environment variable, calls all four
endpoints, and prints a compact summary so you can confirm shapes before any
integration code is written.

    export KIRKHILL_TOKEN="your-key"
    python scripts/probe_api.py
"""
from __future__ import annotations

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
ENDPOINTS = {
    "summary": "/api/v1/summary",
    "generation": "/api/v1/generation",
    "wind-speed": "/api/v1/wind-speed",
    "turbines": "/api/v1/turbines",
}


def call(path: str, token: str, **params: str) -> tuple[int, dict | str]:
    qs = urllib.parse.urlencode({"range": "7d", "scope": "owner", **params})
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
        return err.code, body


def main() -> int:
    token = os.environ.get("KIRKHILL_TOKEN")
    if not token:
        print("ERROR: set KIRKHILL_TOKEN first.", file=sys.stderr)
        return 1

    for name, path in ENDPOINTS.items():
        status, payload = call(path, token)
        print(f"\n=== {name}  [{path}]  HTTP {status} ===")
        if status != 200:
            print(json.dumps(payload, indent=2)[:500])
            continue

        data = payload.get("data", {})
        window = data.get("window", {})
        print(f"window: range={window.get('range')} bucket={window.get('bucket')} "
              f"scope={window.get('scope')} tz={window.get('timezone')}")

        if name == "summary":
            print("summary keys:", sorted(data.get("summary", {})))
        elif name in ("generation", "wind-speed"):
            series = data.get("series", [])
            print(f"series points: {len(series)}; first: {series[0] if series else '—'}")
        elif name == "turbines":
            turbines = data.get("turbines", [])
            print(f"turbines: {len(turbines)} -> ids {[t['id'] for t in turbines]}")
            if turbines:
                print("sample turbine keys:", sorted(turbines[0]))

    print("\nDone. Confirm all four returned HTTP 200 and shapes look right.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
