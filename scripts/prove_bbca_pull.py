"""Prove the Sectors API client + SQLite cache on BBCA.

Demonstrates:
  1. First call  -> cache MISS -> one live API pull -> payload cached.
  2. Second call -> cache HIT  -> served from SQLite, zero network traffic.

The "no second API call" claim is verified mechanically: we wrap the client's
``request`` method with a counter and assert it was invoked exactly once across
both calls (not merely asserted by a print statement).

Usage:
    python scripts/prove_bbca_pull.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

# Ensure the repo root is importable when run as a script (see memory-bank
# techContext note: run module-style, or add the root to sys.path here).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cache.sqlite_cache import SQLiteCache
from sectors_client.client import SectorsClient

COMPANY = "BBCA"
ENDPOINT = "company_report"
SECTIONS = ["overview", "financials"]
PERIOD = date.today().isoformat()  # "as-of" key for the company-report endpoint
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "sectors_cache.db",
)


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    cache = SQLiteCache(DB_PATH)
    # Force a deterministic miss on call 1: wipe any prior entry for this key so
    # every run reproduces "miss -> live pull -> hit" exactly. (Persistence across
    # process restarts is separately verifiable by inspecting data/sectors_cache.db
    # or running without clearing.)
    cache.clear(COMPANY, PERIOD, ENDPOINT)
    client = SectorsClient()

    # Instrument the client so we can *prove* the network was hit only once.
    real_request = client.request
    call_count = {"n": 0}

    def counted_request(url, params=None):
        call_count["n"] += 1
        return real_request(url, params=params)

    client.request = counted_request  # type: ignore[method-assign]

    # --- Call 1: cache miss -> live pull --------------------------------
    cached = cache.get(COMPANY, PERIOD, ENDPOINT)
    if cached is None:
        payload = client.get_company_report(COMPANY, sections=SECTIONS)
        cache.set(COMPANY, PERIOD, ENDPOINT, payload)
        print(f"[call 1] CACHE MISS -> live API pull (network_count={call_count['n']})")
        report_summary(payload)
    else:
        print("[call 1] unexpected cache hit on a fresh run")
        report_summary(cached)

    # --- Call 2: cache hit -> no network ---------------------------------
    cached2 = cache.get(COMPANY, PERIOD, ENDPOINT)
    assert cached2 is not None, "expected a cached payload on the second call"
    print(f"[call 2] CACHE HIT  -> served from SQLite (network_count={call_count['n']})")

    # --- The load-bearing assertion -------------------------------------
    assert call_count["n"] == 1, (
        f"expected exactly 1 API call, got {call_count['n']}"
    )
    print(f"\nPASS: exactly 1 live API call across 2 requests "
          f"(second served from cache).")


def report_summary(payload: dict) -> None:
    overview = payload.get("overview", {})
    financials = payload.get("financials", {})
    print(f"    symbol        : {payload.get('symbol')}")
    print(f"    company_name  : {payload.get('company_name')}")
    print(f"    market_cap    : {overview.get('market_cap')}")
    print(f"    last price    : {overview.get('last_close_price')}")
    print(f"    eps (ttm)     : {financials.get('eps')}")
    hist = financials.get("historical_financials")
    latest_year = hist[-1]["year"] if hist else None
    print(f"    latest fin yr : {latest_year}")


if __name__ == "__main__":
    main()
