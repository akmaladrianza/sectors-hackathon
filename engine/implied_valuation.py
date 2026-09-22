"""Implied-valuation engine: turn multiples into an implied share price.

Two independent sources of a "what should this be worth" number, kept explicitly
separate so they can be compared rather than blended into one opaque figure:

1. **Comps-implied** — the *peer-median* multiple (excluding the subject company)
   inverted to an implied equity value / share price. E.g. peer-median EV/EBITDA
   x subject EBITDA = implied EV, minus net debt = implied equity, / shares = price.

2. **Sectors-native** — Sectors' own disclosed ``intrinsic_value`` (their fair-value
   figure) compared against the last-close price.

The engine never substitutes a number when inputs are missing/zero: a peer median
that can't be computed yields ``None`` with a stated reason, mirroring
``CompanyComp.exclusion_reasons``. A minimum of two screenable peers is required for
a defensible peer median (one peer is not a "peer group").

These outputs are informational (Undervalued / Fairly valued / Overvalued flags),
never a buy/sell recommendation — consistent with the project's hackathon-rule
constraint that the product must not read as financial advice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median
from typing import Optional

from models.company_comp import CompanyComp


@dataclass
class ImpliedPrice:
    """One implied share price, with the multiple/source that produced it."""

    multiple: str
    price: Optional[Decimal]
    source: str
    reason: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.price is not None


@dataclass
class ImpliedValuation:
    """The full implied-valuation result for a single subject company."""

    ticker: str
    current_price: Optional[Decimal]
    comps_implied: list[ImpliedPrice] = field(default_factory=list)
    sectors_intrinsic: Optional[Decimal] = None

    @property
    def comps_prices(self) -> list[Decimal]:
        """Available comps-derived implied prices only (excludes Sectors IV)."""
        out: list[Decimal] = []
        for imp in self.comps_implied:
            if imp.available:
                out.append(imp.price)  # type: ignore[arg-type]
        return out

    @property
    def implied_prices(self) -> list[Decimal]:
        """All available implied prices (comps + Sectors), in absolute currency.

        Kept for backward-compatible callers; the verdict/band use ``comps_prices``
        only, so Sectors' own (often optimistic) fair value never biases the
        peer-relative range edge (see `implied_low`/`implied_high` docstring).
        """
        prices = self.comps_prices
        if self.sectors_intrinsic is not None:
            prices = prices + [self.sectors_intrinsic]
        return prices

    @property
    def implied_low(self) -> Optional[Decimal]:
        """Low end of the *comps-derived* band (Sectors IV excluded).

        Sectors' own fair value is a separate estimate, not a peer-relative multiple,
        so blending it into the min/max would skew the range (e.g. a premium name like
        BBCA whose Sectors IV is much higher than its peers' implied multiples would
        get an artificially wide band and always read "fairly valued"). It stays
        exposed via `sectors_intrinsic` for display, never as a band edge.
        """
        prices = self.comps_prices
        return min(prices) if prices else None

    @property
    def implied_high(self) -> Optional[Decimal]:
        """High end of the *comps-derived* band (Sectors IV excluded)."""
        prices = self.comps_prices
        return max(prices) if prices else None

    @property
    def verdict(self) -> Optional[str]:
        """A coarse informational flag, never a recommendation."""
        if self.current_price is None:
            return None
        low, high = self.implied_low, self.implied_high
        if low is None or high is None:
            return None
        price = self.current_price
        if price < low:
            return "Undervalued"
        if price > high:
            return "Overvalued"
        return "Fairly valued"


def _median(values: list[float]) -> Optional[Decimal]:
    """Safe median of non-None floats; None if the list is empty."""
    if not values:
        return None
    return Decimal(str(median(values)))


def _normalized_median(
    multiples: list[float],
    normalizers: list[float],
) -> Optional[Decimal]:
    """Quality-normalized peer median: ``median(multiple / normalizer)``.

    A raw peer-median multiple misprices a market leader whose quality driver
    (ROE / growth / margin) sits well above its peer average: the peer median
    reflects *average* quality, not the subject's own. Normalizing each peer's
    multiple by its own driver (`P/B / ROE`, `P/E / growth`, `EV/EBITDA / growth`,
    `EV/Revenue / margin`) — the PEG / justified-P/B approach — collapses quality
    differences to a per-unit-of-quality ratio, whose median is then re-applied at
    the *subject's* own quality. Pairs with an unusable normalizer (missing, zero,
    or negative) are dropped, mirroring the existing ill-conditioned-input rule.
    Returns the median ratio, or None when fewer than one usable pair remains.
    """
    ratios: list[float] = []
    for multiple, norm in zip(multiples, normalizers):
        if norm is None or norm <= 0:
            continue
        ratios.append(multiple / norm)
    if not ratios:
        return None
    return Decimal(str(median(ratios)))


def _ev_to_price(
    multiple: str, implied_ev: Decimal, subject: CompanyComp, source: str
) -> ImpliedPrice:
    """Convert an implied enterprise value into an implied equity price per share."""
    debt = subject.total_debt or Decimal(0)
    cash = subject.cash_and_equivalents or Decimal(0)
    implied_equity = implied_ev - debt + cash
    if subject.shares_outstanding and subject.shares_outstanding > 0:
        price = implied_equity / subject.shares_outstanding
        return ImpliedPrice(multiple, price, source)
    return ImpliedPrice(
        multiple, None, source, reason="missing shares_outstanding to derive price"
    )


def comps_implied_prices(
    subject: CompanyComp, peers: list[CompanyComp]
) -> list[ImpliedPrice]:
    """Invert peer-median multiples into implied share prices for ``subject``.

    Excludes the subject from its own peer set (a company can't benchmark against
    itself). Produces up to four implied prices: EV/EBITDA, EV/Revenue (via
    EV -> equity -> price), P/E and P/B (direct). Each carries which multiple
    produced it, for auditability.

    Each multiple is **quality-normalized** before taking the peer median, so a
    market leader whose quality driver (growth / ROE / margin) sits above its peer
    average is priced against its *own* quality rather than the average peer's:

    - P/E        → normalized by ``revenue_growth_yoy``  (PEG, Farina / Lynch)
    - P/B        → normalized by ``roe``                  (justified P/B, Gordon growth)
    - EV/EBITDA  → normalized by ``revenue_growth_yoy``   (growth-adjusted EV/EBITDA)
    - EV/Revenue → normalized by ``ebitda_margin``        (revenue-multiple decomposition)

    When the normalizer is unavailable for the subject or for too few peers, that leg
    falls back to the raw peer median (never a hard failure), and the ``source`` string
    records which mode produced the number.
    """
    others = [p for p in peers if p.ticker != subject.ticker]
    out: list[ImpliedPrice] = []

    # --- EV/EBITDA (growth-normalized) -------------------------------------
    ev_eb_peers = [p for p in others if p.ev_to_ebitda is not None]
    raw_eb = _median([p.ev_to_ebitda for p in ev_eb_peers])
    eb_norm = _normalized_median(
        [p.ev_to_ebitda for p in ev_eb_peers],
        [p.revenue_growth_yoy for p in ev_eb_peers],
    )
    if eb_norm is not None and subject.revenue_growth_yoy is not None and subject.revenue_growth_yoy > 0:
        eb = eb_norm * Decimal(str(subject.revenue_growth_yoy))
        eb_source = (
            f"growth-normalized peer-median EV/EBITDA (PEG-style) x {subject.ticker} EBITDA"
        )
    elif raw_eb is not None:
        eb = raw_eb
        eb_source = f"peer-median EV/EBITDA x {subject.ticker} EBITDA"
    else:
        eb = None
    if eb is not None and subject.ebitda and subject.ebitda > 0:
        out.append(_ev_to_price("EV/EBITDA", eb * subject.ebitda, subject, eb_source))

    # --- EV/Revenue (margin-normalized) ------------------------------------
    ev_rev_peers = [p for p in others if p.ev_to_revenue is not None]
    raw_er = _median([p.ev_to_revenue for p in ev_rev_peers])

    def _margin(c: CompanyComp):
        if c.ebitda is None or not c.revenue or c.revenue == 0:
            return None
        return float(c.ebitda / c.revenue)

    subject_margin = _margin(subject)
    er_norm = _normalized_median(
        [p.ev_to_revenue for p in ev_rev_peers],
        [_margin(p) for p in ev_rev_peers],
    )
    if er_norm is not None and subject_margin is not None and subject_margin > 0:
        er = er_norm * Decimal(str(subject_margin))
        er_source = (
            f"margin-normalized peer-median EV/Revenue x {subject.ticker} revenue"
        )
    elif raw_er is not None:
        er = raw_er
        er_source = f"peer-median EV/Revenue x {subject.ticker} revenue"
    else:
        er = None
    if er is not None and subject.revenue and subject.revenue > 0:
        out.append(_ev_to_price("EV/Revenue", er * subject.revenue, subject, er_source))

    # --- P/E (growth-normalized, PEG-style) --------------------------------
    pe_peers = [p for p in others if p.pe_ratio is not None]
    raw_pe = _median([p.pe_ratio for p in pe_peers])
    pe_norm = _normalized_median(
        [p.pe_ratio for p in pe_peers],
        [p.revenue_growth_yoy for p in pe_peers],
    )
    if pe_norm is not None and subject.revenue_growth_yoy is not None and subject.revenue_growth_yoy > 0:
        pe = pe_norm * Decimal(str(subject.revenue_growth_yoy))
        pe_source = f"growth-normalized peer-median P/E (PEG) x {subject.ticker} EPS"
    elif raw_pe is not None:
        pe = raw_pe
        pe_source = f"peer-median P/E x {subject.ticker} EPS"
    else:
        pe = None
    if pe is not None and subject.eps and subject.eps > 0:
        out.append(ImpliedPrice("P/E", pe * subject.eps, pe_source))

    # --- P/B (ROE-normalized, justified P/B) -------------------------------
    pb_peers = [p for p in others if p.price_to_book is not None]
    raw_pb = _median([p.price_to_book for p in pb_peers])
    pb_norm = _normalized_median(
        [p.price_to_book for p in pb_peers],
        [p.roe for p in pb_peers],
    )
    if pb_norm is not None and subject.roe is not None and subject.roe > 0:
        pb = pb_norm * Decimal(str(subject.roe))
        pb_source = (
            f"ROE-normalized peer-median P/B (justified P/B) x {subject.ticker} book value/share"
        )
    elif raw_pb is not None:
        pb = raw_pb
        pb_source = f"peer-median P/B x {subject.ticker} book value per share"
    else:
        pb = None
    if (
        pb is not None
        and subject.total_equity
        and subject.total_equity > 0
        and subject.shares_outstanding
        and subject.shares_outstanding > 0
    ):
        bvps = subject.total_equity / subject.shares_outstanding
        out.append(ImpliedPrice("P/B", pb * bvps, pb_source))

    return out


def build_implied_valuation(
    subject: CompanyComp, peers: list[CompanyComp]
) -> ImpliedValuation:
    """Assemble the full implied-valuation view for one subject company.

    A negative ``intrinsic_value`` (Sectors signalling distress/over-leverage) is not a
    usable fair-value benchmark, so ``sectors_intrinsic`` degrades to ``None`` rather
    than leaking a nonsensical negative "fair price" into the panel or band.
    """
    comps = comps_implied_prices(subject, peers)
    iv = subject.intrinsic_value
    if iv is not None and iv <= 0:
        iv = None
    return ImpliedValuation(
        ticker=subject.ticker,
        current_price=subject.price,
        comps_implied=comps,
        sectors_intrinsic=iv,
    )
