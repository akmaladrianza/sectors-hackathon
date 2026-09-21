"""Lightweight back-test: proxy-predicted growth vs realised historical growth.

This is a SANITY CHECK, not a statistical validation: for a few real tickers we
already have full data for, compare the proxy library's default growth rate against
the company's own realized historical revenue CAGR, to confirm each proxy is in the
right ballpark (not off by an order of magnitude).

Run: python scripts/backtest_proxies.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from mapper.mapper import report_to_company_comp
from engine.proxy_library import default_growth, classify_proxy, _revenue_series, _cagr

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "fixtures")


def _load(name: str) -> dict:
    import json
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    cases = [
        ("BBCA.json", "bank", None),
        ("MDKA.json", "miner", "MDKA_performance.json"),
        ("TLKM.json", "generic", None),
    ]

    print(f"{'Ticker':<8} {'Kind':<8} {'Proxy':>10} {'Real CAGR':>10} {'Ratio':>8}")
    print("-" * 50)

    from mapper.mining_overlay import map_mining_overlay

    for fixture, _expected_kind, mining_fixture in cases:
        payload = _load(fixture)
        comp, _template = report_to_company_comp(payload)
        raw_hist = payload.get("financials", {}).get("historical_financials", [])

        overlay = None
        if mining_fixture:
            mining_payload = _load_mining(mining_fixture)
            overlay = map_mining_overlay(
                ticker=comp.ticker,
                slug="pt-merdeka-copper-gold-tbk",
                performance=mining_payload,
            )

        kind = classify_proxy(comp, overlay)
        proxy = default_growth(comp, overlay=overlay, raw_hist=raw_hist)
        real_cagr = _cagr(_revenue_series(raw_hist))

        pv = proxy.value
        disp_proxy = f"{float(pv)*100:.1f}%" if pv is not None else "n/a"
        disp_cagr = f"{float(real_cagr)*100:.1f}%" if real_cagr is not None else "n/a"

        ratio = ""
        if pv is not None and real_cagr is not None and real_cagr != 0:
            ratio = f"{float(pv / real_cagr):.2f}x"

        print(f"{comp.ticker.replace('.JK',''):<8} {kind:<8} {disp_proxy:>10} {disp_cagr:>10} {ratio:>8}")

    print("\nNote: 'Ratio' near 1.0x means proxy ~ realised growth (good ballpark);")
    print("      a ratio >3x or <0.3x would flag a proxy that is far off the mark.")


def _load_mining(name: str) -> dict:
    import json
    path = os.path.join(FIXTURES, "mining", name)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
