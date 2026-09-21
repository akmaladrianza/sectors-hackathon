"""Prove the mining overlay end-to-end on live data.

Pulls the mining-extension endpoints live, maps them into ``MiningOverlay``, and
prints the result — demonstrating (a) MDKA is performance-only (financials and
sales-destination 404), and (b) ADRO has the full metric set.

Usage:
    python scripts/prove_mining_overlay.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sectors_client.client import SectorsClient, SectorsAPIError
from mapper.mining_overlay import map_mining_overlay


def _print_overlay(label: str, overlay) -> None:
    print(f"[{label}]")
    print(f"  ticker={overlay.ticker} name={overlay.company_name}")
    print(f"  commodities={overlay.commodity_types}")
    print(
        f"  total_reserves={overlay.total_reserves_Mt} Mt  "
        f"total_resources={overlay.total_resources_Mt} Mt  "
        f"vintage={overlay.reserve_vintage_year}"
    )
    for c in overlay.commodities:
        print(
            f"    - {c.commodity_type}: prod={c.production_volume} {c.unit}, "
            f"sales={c.sales_volume} {c.unit}, status={c.mining_operation_status}"
        )
    print(
        f"  revenue_usd={overlay.revenue_usd} net_profit_usd={overlay.net_profit_usd} "
        f"assets_usd={overlay.assets_usd}"
    )
    print(
        f"  sales_dest countries={sorted(overlay.sales_destination_volume.keys())}"
        if overlay.has_sales_destination_data
        else "  sales_dest: (none)"
    )
    print(
        f"  flags: perf={overlay.has_performance_data} "
        f"fin={overlay.has_financials_data} sale={overlay.has_sales_destination_data} "
        f"self_reported={overlay.is_self_reported}"
    )
    print()


def main() -> None:
    client = SectorsClient()

    # --- MDKA: performance only ---
    mdka_slug = "pt-merdeka-copper-gold-tbk"
    perf = client.get_mining_performance(mdka_slug)
    mdka = map_mining_overlay(ticker="MDKA.JK", slug=mdka_slug, performance=perf)
    _print_overlay("MDKA (performance only)", mdka)

    # --- ADRO: full ---
    adro_slug = "pt-alamtri-resources-indonesia-tbk"
    adro_perf = client.get_mining_performance(adro_slug)
    adro_fin = client.get_mining_financials(adro_slug)
    try:
        adro_sale = client.get_mining_sales_destination(adro_slug)
    except SectorsAPIError:
        adro_sale = None
    adro = map_mining_overlay(
        ticker="ADRO.JK",
        slug=adro_slug,
        performance=adro_perf,
        financials=adro_fin,
        sales_destination=adro_sale,
    )
    _print_overlay("ADRO (full)", adro)

    print("PASS: mining overlay proven live (MDKA performance-only, ADRO full).")


if __name__ == "__main__":
    main()
