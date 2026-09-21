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
    def implied_prices(self) -> list[Decimal]:
        """All available implied prices (comps + Sectors), in absolute currency."""
        out: list[Decimal] = []
        for imp in self.comps_implied:
            if imp.available:
                out.append(imp.price)  # type: ignore[arg-type]
        if self.sectors_intrinsic is not None:
            out.append(self.sectors_intrinsic)
        return out

    @property
    def implied_low(self) -> Optional[Decimal]:
        prices = self.implied_prices
        return min(prices) if prices else None

    @property
    def implied_high(self) -> Optional[Decimal]:
        prices = self.implied_prices
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
    """
    others = [p for p in peers if p.ticker != subject.ticker]
    out: list[ImpliedPrice] = []

    # --- EV/EBITDA --------------------------------------------------------
    eb = _median([p.ev_to_ebitda for p in others if p.ev_to_ebitda is not None])
    if eb is not None and subject.ebitda and subject.ebitda > 0:
        out.append(
            _ev_to_price(
                "EV/EBITDA",
                eb * subject.ebitda,
                subject,
                f"peer-median EV/EBITDA x {subject.ticker} EBITDA",
            )
        )

    # --- EV/Revenue -------------------------------------------------------
    er = _median([p.ev_to_revenue for p in others if p.ev_to_revenue is not None])
    if er is not None and subject.revenue and subject.revenue > 0:
        out.append(
            _ev_to_price(
                "EV/Revenue",
                er * subject.revenue,
                subject,
                f"peer-median EV/Revenue x {subject.ticker} revenue",
            )
        )

    # --- P/E (price = peer P/E x subject EPS) -----------------------------
    pe = _median([p.pe_ratio for p in others if p.pe_ratio is not None])
    if pe is not None and subject.eps and subject.eps > 0:
        out.append(
            ImpliedPrice(
                "P/E",
                pe * subject.eps,
                f"peer-median P/E x {subject.ticker} EPS",
            )
        )

    # --- P/B (price = peer P/B x subject book value / shares) -------------
    pb = _median([p.price_to_book for p in others if p.price_to_book is not None])
    if (
        pb is not None
        and subject.total_equity
        and subject.total_equity > 0
        and subject.shares_outstanding
        and subject.shares_outstanding > 0
    ):
        bvps = subject.total_equity / subject.shares_outstanding
        out.append(
            ImpliedPrice(
                "P/B",
                pb * bvps,
                f"peer-median P/B x {subject.ticker} book value per share",
            )
        )

    return out


def build_implied_valuation(
    subject: CompanyComp, peers: list[CompanyComp]
) -> ImpliedValuation:
    """Assemble the full implied-valuation view for one subject company."""
    comps = comps_implied_prices(subject, peers)
    return ImpliedValuation(
        ticker=subject.ticker,
        current_price=subject.price,
        comps_implied=comps,
        sectors_intrinsic=subject.intrinsic_value,
    )
