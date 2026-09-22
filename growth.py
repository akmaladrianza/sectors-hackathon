"""Shared historical-growth helpers (pure, no model imports).

Extracted so both ``engine.proxy_library`` (DCF default growth) and
``mapper.mapper`` (populating ``CompanyComp.revenue_growth_yoy`` for the
growth-normalized comps in ``engine.implied_valuation``) can compute a revenue
CAGR from ``historical_financials`` without creating an ``engine``-package
import cycle (``mapper`` -> ``engine/__init__`` -> ``peer_lookup`` -> ``mapper``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def revenue_series(raw_hist: Optional[list]) -> list[Decimal]:
    """Extract an ordered revenue series from ``historical_financials``."""
    series = []
    for row in raw_hist or []:
        rev = _dec(row.get("revenue"))
        year = row.get("year")
        if rev is not None and rev > 0 and year is not None:
            series.append((year, rev))
    series.sort(key=lambda t: t[0])
    return [rev for _year, rev in series]


def cagr(series: list[Decimal]) -> Optional[Decimal]:
    """Compound annual growth rate over a series; None if too short/invalid."""
    if len(series) < 2:
        return None
    first, last = series[0], series[-1]
    years = len(series) - 1
    if first <= 0 or last <= 0:
        return None
    ratio = last / first
    return (ratio ** (Decimal(1) / Decimal(years))) - Decimal(1)


def revenue_cagr(raw_hist: Optional[list]) -> Optional[float]:
    """Revenue CAGR over ``historical_financials`` as a float, or None."""
    value = cagr(revenue_series(raw_hist))
    return float(value) if value is not None else None
