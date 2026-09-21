"""Prove the screener end-to-end on a live batch of tickers.

Pulls a mixed batch (banks, generic, a miner) and prints the screenable table
plus any exclusions, demonstrating the partition + mining join + exclusion logic.

Usage:
    python scripts/prove_screener.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener.screener import screen_tickers


def main() -> None:
    # A mixed batch: a bank, generic names, and a miner (MDKA).
    tickers = ["BBCA", "TLKM", "ASII", "UNVR", "MDKA"]

    result = screen_tickers(tickers)

    print("=== SCREENABLE (non-mining) ===")
    for c in result.screenable:
        print(f"  {c.ticker:<10} {c.company_name[:28]:<28} "
              f"EV/EBITDA={c.ev_to_ebitda} P/E={c.pe_ratio} P/B={c.price_to_book}")

    print("\n=== MINERS (with reserve overlay) ===")
    for m in result.miners:
        ev = m.ev_per_tonne_reserves
        print(f"  {m.comp.ticker:<10} reserves={m.overlay.total_reserves_Mt} Mt "
              f"EV/t={ev.value} ({ev.reason or 'ok'})")

    print("\n=== EXCLUDED ===")
    if result.excluded:
        for e in result.excluded:
            print(f"  {e.ticker:<10} {e.reason}")
    else:
        print("  (none)")

    print(f"\nPASS: {len(result.screenable)} screenable, {len(result.miners)} miners, "
          f"{len(result.excluded)} excluded.")


if __name__ == "__main__":
    main()
