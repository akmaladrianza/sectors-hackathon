"""Presentation-layer transforms: turn a ``ScreenerResult`` into table rows.

Separated from the Streamlit UI so the data-transformation logic is unit-testable
without a running Streamlit process (Streamlit apps aren't trivially testable).

Everything here is pure: ``ScreenerResult`` -> list-of-dicts (or a pandas DataFrame)
for the comps table, the mining overlay table, and the exclusion list.
"""

from __future__ import annotations

from typing import Optional

from screener.screener import ScreenerResult


def _fmt_multiple(v: Optional[float]) -> Optional[float]:
    """Round a multiple to a presentation-friendly 2 decimals; None stays None."""
    if v is None:
        return None
    return round(v, 2)


def comps_rows(result: ScreenerResult) -> list[dict]:
    """Rows for the main comps table (screenable non-mining peers)."""
    rows = []
    for c in result.screenable:
        rows.append(
            {
                "Ticker": c.ticker,
                "Company": c.company_name,
                "Sector": c.sector,
                "EV/EBITDA": _fmt_multiple(c.ev_to_ebitda),
                "EV/Revenue": _fmt_multiple(c.ev_to_revenue),
                "P/E": _fmt_multiple(c.pe_ratio),
                "P/B": _fmt_multiple(c.price_to_book),
            }
        )
    return rows


def mining_rows(result: ScreenerResult) -> list[dict]:
    """Rows for the mining overlay table (with reserve/vintage defensibility flags)."""
    rows = []
    for m in result.miners:
        ev_res = m.ev_per_tonne_reserves
        ev_resources = m.ev_per_tonne_resources
        rows.append(
            {
                "Ticker": m.comp.ticker,
                "Company": m.overlay.company_name or m.comp.company_name,
                "Commodities": ", ".join(m.overlay.commodity_types),
                "Reserves (Mt)": float(m.overlay.total_reserves_Mt)
                if m.overlay.total_reserves_Mt is not None
                else None,
                "Resources (Mt)": float(m.overlay.total_resources_Mt)
                if m.overlay.total_resources_Mt is not None
                else None,
                "EV/tonne (reserves)": round(float(ev_res.value), 2)
                if ev_res.value is not None
                else None,
                "EV/tonne (resources)": round(float(ev_resources.value), 2)
                if ev_resources.value is not None
                else None,
                "Reserve vintage": m.overlay.reserve_vintage_year,
                "Self-reported": m.overlay.is_self_reported,
            }
        )
    return rows


def exclusion_rows(result: ScreenerResult) -> list[dict]:
    """Rows for the excluded-peers panel (ticker + reason, never silently dropped)."""
    return [
        {"Ticker": e.ticker, "Reason": e.reason}
        for e in result.excluded
    ]


def to_dataframe(result: ScreenerResult):
    """Build a pandas DataFrame for the comps table (returns empty DF if none)."""
    import pandas as pd

    rows = comps_rows(result)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def to_mining_dataframe(result: ScreenerResult):
    import pandas as pd

    rows = mining_rows(result)
    return pd.DataFrame(rows) if rows else pd.DataFrame()
