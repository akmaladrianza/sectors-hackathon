"""Football-field chart data assembly.

Builds the per-multiple valuation ranges that feed a horizontal min–max bar chart for
one subject company. Each row in the chart is a valuation method; its ``low``/``high``
span is the min–max across *same-sub-sector peers* (from Sectors' own precomputed
multiples), inverted to a share price where possible, with the subject's current price
and Sectors' disclosed intrinsic value overlaid as markers.

The peer set comes from ``engine.peer_lookup`` (industry-matched), NOT from the raw
ticker list the user typed — fixing the "can't compare BBCA with BUMI" problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from models.company_comp import CompanyComp


@dataclass
class FootballFieldRow:
    """One valuation method's price range for the chart."""

    method: str
    low: Optional[float]
    high: Optional[float]
    currency: str = "IDR"


def peer_price_ranges(peers: list[CompanyComp], subject: CompanyComp) -> list[FootballFieldRow]:
    """Invert peer multiples into implied share-price ranges for ``subject``.

    ``peers`` are fully-mapped ``CompanyComp`` instances (from ``engine.peer_lookup``)
    whose multiples are already-computed derived fields. For EV-based multiples we
    invert via EV -> equity -> price using the subject's own EBITDA / revenue / net
    debt / shares; for price multiples (P/E, P/B) we invert directly against the
    subject's EPS / book value per share. The low/high are the min/max of the
    resulting implied prices across peers.
    """
    out: list[FootballFieldRow] = []

    if subject.ebitda and subject.ebitda > 0:
        evs = [float(p.ev_to_ebitda) * float(subject.ebitda)
               for p in peers if p.ev_to_ebitda is not None]
        if evs:
            row = _range_from_ev("EV/EBITDA (peers)", evs, subject)
            if row.low is not None:
                out.append(row)

    if subject.revenue and subject.revenue > 0:
        evs = [float(p.ev_to_revenue) * float(subject.revenue)
               for p in peers if p.ev_to_revenue is not None]
        if evs:
            row = _range_from_ev("EV/Revenue (peers)", evs, subject)
            if row.low is not None:
                out.append(row)

    if subject.eps and subject.eps > 0:
        pes = [float(p.pe_ratio) for p in peers if p.pe_ratio is not None]
        if pes:
            prices = [pe * float(subject.eps) for pe in pes]
            out.append(FootballFieldRow("P/E (peers)", min(prices), max(prices)))

    if subject.total_equity and subject.total_equity > 0 and subject.shares_outstanding:
        bvps = float(subject.total_equity / subject.shares_outstanding)
        pbs = [float(p.price_to_book) for p in peers if p.price_to_book is not None]
        if pbs and bvps > 0:
            prices = [pb * bvps for pb in pbs]
            out.append(FootballFieldRow("P/B (peers)", min(prices), max(prices)))

    return out


def _range_from_ev(
    method: str, implied_evs: list[float], subject: CompanyComp
) -> FootballFieldRow:
    debt = float(subject.total_debt or 0)
    cash = float(subject.cash_and_equivalents or 0)
    shares = float(subject.shares_outstanding or 0)
    if shares <= 0:
        return FootballFieldRow(method, None, None)
    prices = [(ev - debt + cash) / shares for ev in implied_evs]
    return FootballFieldRow(method, min(prices), max(prices))


def build_football_field(
    subject: CompanyComp,
    peers: list[CompanyComp],
    dcf_price: Optional[Decimal] = None,
) -> tuple[list[FootballFieldRow], Optional[float], Optional[float]]:
    """Assemble chart rows for ``subject``.

    Returns ``(rows, current_price, sectors_iv)``. ``rows`` are the peer-multiple
    ranges plus (optionally) the DCF-implied price as a single-point method and
    Sectors IV as a single-point method. ``current_price`` / ``sectors_iv`` are the
    marker values to overlay.
    """
    rows = peer_price_ranges(peers, subject)

    if dcf_price is not None:
        fp = float(dcf_price)
        rows.append(FootballFieldRow("DCF (FCFF)", fp, fp))
    if subject.intrinsic_value is not None:
        iv = float(subject.intrinsic_value)
        rows.append(FootballFieldRow("Sectors IV", iv, iv))

    current = float(subject.price) if subject.price is not None else None
    return rows, current, (
        float(subject.intrinsic_value) if subject.intrinsic_value is not None else None
    )
