"""Discounted cash-flow (DCF) engine — Advanced mode.

A deliberately simplified corporate DCF: project revenue N years at a growth rate,
apply an operating-cash-flow margin, discount at an "expected rate of return" (a
stand-in for textbook WACC, per the project's settled decision), add a terminal value
via a Gordon-growth perpetuity, and sum to an intrinsic enterprise value.

The output is an *estimate* scaffolding, not a forecast to be trusted as truth. The
assumption inputs (growth, margin, discount rate, terminal growth) are explicit and
documented; the projection window ``years`` is a function argument (default 5) that the
UI does not currently expose. The "defensible by design" rule holds: every number is a
documented input, nothing is silently fabricated.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


class DCFResult:
    """Intrinsic-value output, with the assumptions used to produce it."""

    def __init__(
        self,
        intrinsic_ev: Optional[Decimal],
        assumptions: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.intrinsic_ev = intrinsic_ev
        self.assumptions = assumptions or {}
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.intrinsic_ev is not None


def run_dcf(
    revenue: Optional[Decimal],
    growth_rate: Decimal,
    cash_flow_margin: Decimal,
    discount_rate: Decimal,
    terminal_growth: Decimal,
    years: int = 5,
) -> DCFResult:
    """Run a 2-stage DCF (explicit projection + terminal value).

    ``cash_flow_margin`` is free-cash-flow as a fraction of revenue (default can come
    from a net-margin proxy). Discount rate is the "expected rate of return". All the
    free-cash-flow in each year is discounted to present, plus a Gordon terminal value
    at the end of the projection window.
    """
    if revenue is None or revenue <= 0:
        return DCFResult(None, reason="missing or non-positive current revenue")
    if not (0 < discount_rate < 1):
        return DCFResult(None, reason="discount rate must be in (0, 1)")
    if not (0 <= terminal_growth < discount_rate):
        return DCFResult(None, reason="terminal growth must be 0 <= g < discount rate")
    if years < 1:
        return DCFResult(None, reason="projection window must be >= 1 year")

    # Convert rates-as-fraction inputs to Decimal for exact arithmetic.
    g = growth_rate
    m = cash_flow_margin
    r = discount_rate
    tv = terminal_growth

    pv_series = Decimal(0)
    year_rev = revenue
    for t in range(1, years + 1):
        year_rev = revenue * ((Decimal(1) + g) ** t)
        fcf = year_rev * m
        pv_series += fcf / ((Decimal(1) + r) ** t)

    # Terminal value = final-year FCF * (1 + g_terminal) / (r - g_terminal),
    # discounted back to present.
    final_fcf = revenue * ((Decimal(1) + g) ** years) * m
    terminal_value = final_fcf * (Decimal(1) + tv) / (r - tv)
    pv_terminal = terminal_value / ((Decimal(1) + r) ** years)

    intrinsic_ev = pv_series + pv_terminal
    return DCFResult(
        intrinsic_ev,
        assumptions={
            "growth_rate": g,
            "cash_flow_margin": m,
            "discount_rate": r,
            "terminal_growth": tv,
            "years": years,
        },
    )
