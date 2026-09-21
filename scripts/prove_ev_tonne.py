"""Prove the EV/tonne-of-reserves engine on live data.

For each seed miner, pulls the comps data (→ ``CompanyComp`` enterprise value) and
the mining overlay (→ reserve/resource tonnage), then joins them into EV/tonne.

Usage:
    python scripts/prove_ev_tonne.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sectors_client.client import SectorsClient
from mapper.mapper import report_to_company_comp
from mapper.mining_overlay import map_mining_overlay
from engine.mining_valuation import ev_to_tonne_of_reserves, ev_to_tonne_of_resources


def _fmt(d):
    if d is None:
        return "n/a"
    return f"{d:,.0f}"


def main() -> None:
    client = SectorsClient()

    for ticker, slug in [
        ("MDKA", "pt-merdeka-copper-gold-tbk"),
        ("ADRO", "pt-alamtri-resources-indonesia-tbk"),
    ]:
        print(f"=== {ticker} ===")
        # Comps side: enterprise value
        payload = client.get_company_report(ticker, sections=["overview", "financials"])
        comp, template = report_to_company_comp(payload)

        # Mining side: tonnage
        perf = client.get_mining_performance(slug)
        overlay = map_mining_overlay(ticker=f"{ticker}.JK", slug=slug, performance=perf)

        print(f"  enterprise_value (IDR) = {_fmt(comp.enterprise_value)}")
        print(f"  total_reserves  = {overlay.total_reserves_Mt} Mt")
        print(f"  total_resources = {overlay.total_resources_Mt} Mt")

        r = ev_to_tonne_of_reserves(comp, overlay)
        res = ev_to_tonne_of_resources(comp, overlay)
        print(f"  EV/tonne reserves  = {_fmt(r.value)} IDR/tonne ({r.reason or 'ok'})")
        print(f"  EV/tonne resources = {_fmt(res.value)} IDR/tonne ({res.reason or 'ok'})")
        print()


if __name__ == "__main__":
    main()
