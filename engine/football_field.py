"""Football-field chart data assembly.

Builds the per-multiple valuation ranges that feed a horizontal chart for one subject
company. Each row is a valuation method whose ``low``/``high`` span is the
**interquartile range (25th–75th percentile)** of the quality-normalized peer-implied
prices — NOT a raw min/max, which a single outlier peer (e.g. a nano-cap trading at
200x EV/EBITDA) would otherwise blow up (the TKIM/ALKA failure mode).

Normalization mirrors ``engine.implied_valuation``: each peer's multiple is divided by
its own quality driver (growth for P/E + EV/EBITDA, margin for EV/Revenue, ROE for P/B)
before the median is taken, and the per-unit-quality value is re-applied at the
*subject's* own driver — so a market leader whose quality sits above its peer average
isn't priced against the average peer.

The peer set comes from ``engine.peer_lookup`` (industry-matched first), NOT from the
raw ticker list the user typed — fixing the "can't compare BBCA with BUMI" problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Optional

from models.company_comp import CompanyComp


@dataclass
class FootballFieldRow:
    """One valuation method's price range for the chart."""

    method: str
    low: Optional[float]
    high: Optional[float]
    currency: str = "IDR"


def _percentile(sorted_values: list[float], q: float) -> Optional[float]:
    """Linear-interpolated percentile over a sorted, non-empty list."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _iqr_range(values: list[float]) -> tuple[Optional[float], Optional[float]]:
    """25th–75th percentile range; (None, None) if empty."""
    if not values:
        return None, None
    s = sorted(values)
    return _percentile(s, 0.25), _percentile(s, 0.75)


def _subject_margin(c: CompanyComp) -> Optional[float]:
    if c.ebitda is None or not c.revenue or c.revenue == 0:
        return None
    return float(c.ebitda / c.revenue)


def _normalized_prices(
    multiples: list[float],
    normalizers: list[Optional[float]],
    subject_normalizer: Optional[float],
) -> list[float]:
    """Return peer-normalized values re-applied at the subject's driver.

    Falls back to the raw multiples (no normalization) when the subject's driver is
    missing/non-positive — mirroring ``implied_valuation``, never a hard failure.
    """
    if subject_normalizer is None or subject_normalizer <= 0:
        return multiples
    ratios = [m / n for m, n in zip(multiples, normalizers) if n is not None and n > 0]
    if not ratios:
        return multiples
    k = median(ratios)
    return [k * subject_normalizer]


def peer_price_ranges(peers: list[CompanyComp], subject: CompanyComp) -> list[FootballFieldRow]:
    """Invert peer multiples into implied share-price ranges for ``subject``.

    ``peers`` are fully-mapped ``CompanyComp`` instances from ``engine.peer_lookup``.
    For EV-based multiples we invert via EV -> equity -> price using the subject's own
    EBITDA / revenue / net debt / shares; for price multiples (P/E, P/B) we invert
    directly against the subject's EPS / book value per share. Each method's ``low`` /
    ``high`` is the IQR of the (growth/ROE/margin-normalized) implied prices, so a
    single outlier peer can no longer set the chart's edge.
    """
    out: list[FootballFieldRow] = []

    # --- EV/EBITDA (growth-normalized, PEG-style) ---------------------------
    if subject.ebitda and subject.ebitda > 0:
        ev_eb_peers = [p for p in peers if p.ev_to_ebitda is not None]
        if ev_eb_peers:
            normalized = _normalized_prices(
                [float(p.ev_to_ebitda) for p in ev_eb_peers],
                [p.revenue_growth_yoy for p in ev_eb_peers],
                subject.revenue_growth_yoy,
            )
            evs = [m * float(subject.ebitda) for m in normalized]
            row = _range_from_ev("EV/EBITDA (peers)", evs, subject)
            if row.low is not None:
                out.append(row)

    # --- EV/Revenue (margin-normalized) -------------------------------------
    if subject.revenue and subject.revenue > 0:
        ev_rev_peers = [p for p in peers if p.ev_to_revenue is not None]
        if ev_rev_peers:
            normalized = _normalized_prices(
                [float(p.ev_to_revenue) for p in ev_rev_peers],
                [_subject_margin(p) for p in ev_rev_peers],
                _subject_margin(subject),
            )
            evs = [m * float(subject.revenue) for m in normalized]
            row = _range_from_ev("EV/Revenue (peers)", evs, subject)
            if row.low is not None:
                out.append(row)

    # --- P/E (growth-normalized, PEG-style) ---------------------------------
    if subject.eps and subject.eps > 0:
        pe_peers = [p for p in peers if p.pe_ratio is not None]
        if pe_peers:
            normalized = _normalized_prices(
                [float(p.pe_ratio) for p in pe_peers],
                [p.revenue_growth_yoy for p in pe_peers],
                subject.revenue_growth_yoy,
            )
            prices = [pe * float(subject.eps) for pe in normalized]
            lo, hi = _iqr_range(prices)
            out.append(FootballFieldRow("P/E (peers)", lo, hi))

    # --- P/B (ROE-normalized, justified P/B) --------------------------------
    if subject.total_equity and subject.total_equity > 0 and subject.shares_outstanding:
        bvps = float(subject.total_equity / subject.shares_outstanding)
        pb_peers = [p for p in peers if p.price_to_book is not None]
        if pb_peers and bvps > 0:
            normalized = _normalized_prices(
                [float(p.price_to_book) for p in pb_peers],
                [p.roe for p in pb_peers],
                subject.roe,
            )
            prices = [pb * bvps for pb in normalized]
            lo, hi = _iqr_range(prices)
            out.append(FootballFieldRow("P/B (peers)", lo, hi))

    return out


def _range_from_ev(
    method: str, implied_evs: list[float], subject: CompanyComp
) -> FootballFieldRow:
    debt = float(subject.total_debt or 0)
    cash = float(subject.cash_and_equivalents or 0)
    shares = float(subject.shares_outstanding or 0)
    if shares <= 0:
        return FootballFieldRow(method, None, None)
    # A share price cannot be negative. When net debt exceeds a peer-implied EV (a
    # heavily-levered subject like TKIM), the residual-equity value is negative; we
    # floor at 0 rather than chart a nonsensical negative "price" — the subject's high
    # leverage is instead visible via its low implied equity value.
    prices = [max(0.0, (ev - debt + cash) / shares) for ev in implied_evs]
    lo, hi = _iqr_range(prices)
    return FootballFieldRow(method, lo, hi)


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
    if subject.intrinsic_value is not None and subject.intrinsic_value > 0:
        iv = float(subject.intrinsic_value)
        rows.append(FootballFieldRow("Sectors IV", iv, iv))

    current = float(subject.price) if subject.price is not None else None
    _iv = (
        float(subject.intrinsic_value)
        if subject.intrinsic_value is not None and subject.intrinsic_value > 0
        else None
    )
    return rows, current, _iv
