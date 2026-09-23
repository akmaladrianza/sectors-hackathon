"""Presentation-layer transforms: turn a ``ScreenerResult`` into table rows.

Separated from the Streamlit UI so the data-transformation logic is unit-testable
without a running Streamlit process (Streamlit apps aren't trivially testable).

Everything here is pure: ``ScreenerResult`` -> list-of-dicts (or a pandas DataFrame)
for the comps table, the mining overlay table, and the exclusion list.
"""

from __future__ import annotations

from typing import Optional

from screener.screener import ScreenerResult
from engine.implied_valuation import build_implied_valuation


def _fmt_multiple(v: Optional[float]) -> Optional[float]:
    """Round a multiple to a presentation-friendly 2 decimals; None stays None."""
    if v is None:
        return None
    return round(v, 2)


def _fmt_price(v) -> Optional[float]:
    """Round a monetary/price value to 2 decimals; None stays None."""
    if v is None:
        return None
    return round(float(v), 2)


def _fmt_pct(v: Optional[float]) -> Optional[float]:
    """Round a fractional upside to 2 decimals (e.g. 0.1234 -> 0.12); None stays None."""
    if v is None:
        return None
    return round(v, 4)


def _fmt_intrinsic(v) -> Optional[float]:
    """Format a Sectors intrinsic value; a negative (distress/DCF <= 0) value becomes
    ``None`` (blank) so it is never shown as a bogus negative "fair price". The
    non-fatal ``data_quality_flags`` warning surfaces the reason instead."""
    if v is None or float(v) < 0:
        return None
    return round(float(v), 2)


def comps_rows(result: ScreenerResult) -> list[dict]:
    """Rows for the main comps table (screenable non-mining peers)."""
    rows = []
    for c in result.screenable:
        rows.append(
            {
                "Ticker": c.ticker,
                "Company": c.company_name,
                "Sector": c.sector,
                "Period": c.fiscal_period or "—",
                "As of": c.as_of_date.isoformat() if c.as_of_date else "—",
                "EV/EBITDA": _fmt_multiple(c.ev_to_ebitda),
                "EV/Revenue": _fmt_multiple(c.ev_to_revenue),
                "P/E": _fmt_multiple(c.pe_ratio),
                "P/B": _fmt_multiple(c.price_to_book),
                "Sectors IV": _fmt_intrinsic(c.intrinsic_value),
                "Upside": _fmt_pct(c.intrinsic_upside),
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
                "Period": m.comp.fiscal_period or "—",
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


def implied_valuation_rows(result: ScreenerResult) -> list[dict]:
    """Rows for the implied-valuation panel (comps-implied price + Sectors IV).

    One row per screenable peer, showing current price, the implied-price range from
    peer-median multiples, Sectors' own intrinsic value, and a coarse verdict.
    """
    rows = []
    all_peers = result.screenable + [m.comp for m in result.miners]
    for c in result.screenable:
        iv = build_implied_valuation(c, all_peers)
        low = float(iv.implied_low) if iv.implied_low is not None else None
        high = float(iv.implied_high) if iv.implied_high is not None else None
        current = float(iv.current_price) if iv.current_price is not None else None
        rows.append(
            {
                "Ticker": c.ticker,
                "Period": c.fiscal_period or "—",
                "As of": c.as_of_date.isoformat() if c.as_of_date else "—",
                "Current price": _fmt_price(current),
                "Implied low": _fmt_price(low),
                "Implied high": _fmt_price(high),
                "Sectors IV": _fmt_price(c.intrinsic_value),
                "Verdict": iv.verdict,
            }
        )
    return rows


def to_implied_dataframe(result: ScreenerResult):
    import pandas as pd

    rows = implied_valuation_rows(result)
    return pd.DataFrame(rows) if rows else pd.DataFrame()
