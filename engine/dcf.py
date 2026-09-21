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
        intrinsic_equity: Optional[Decimal] = None,
        intrinsic_price_per_share: Optional[Decimal] = None,
        assumptions: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> None:
        self.intrinsic_ev = intrinsic_ev
        self.intrinsic_equity = intrinsic_equity
        self.intrinsic_price_per_share = intrinsic_price_per_share
        self.assumptions = assumptions or {}
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.intrinsic_ev is not None


def _discount(series_values: list[Decimal], r: Decimal) -> Decimal:
    """Sum a list of period-end cash flows discounted to present.

    ``series_values[t-1]`` is the cash flow generated at the end of year ``t``.
    """
    total = Decimal(0)
    for t, cf in enumerate(series_values, start=1):
        total += cf / ((Decimal(1) + r) ** t)
    return total


def working_capital_days_to_margin(
    ar_days: Decimal,
    inventory_days: Decimal,
    ap_days: Decimal,
) -> Decimal:
    """Net working capital as a fraction of revenue, from activity days.

    ``NWC / revenue = (AR days + Inventory days - AP days) / 365``. This is the
    working-capital loading applied to each projected year's revenue; the *change*
    in NWC between consecutive years is the FCF hit, computed inside ``run_dcf``.

    AR/AP days are labelled as approximations at the call site (Sectors does not
    expose trade receivables/payables directly; they are derived as residual
    current-asset / current-liability balances).
    """
    return (ar_days + inventory_days - ap_days) / Decimal(365)


def nwc_change_margin_from_days(
    ar_days: Decimal,
    inventory_days: Decimal,
    ap_days: Decimal,
    growth_rate: Decimal,
) -> Decimal:
    """ΔNWC / revenue for a growing firm, from activity days.

    With NWC = loading × revenue, the year-over-year change is
    ``loading × Δrevenue = loading × revenue_prev × g``, so as a fraction of the
    *current* year's revenue it is ``loading × g / (1 + g)``. This is the exact
    ``nwc_change_margin`` that ``run_dcf`` expects for a growing revenue line.
    """
    loading = working_capital_days_to_margin(ar_days, inventory_days, ap_days)
    if growth_rate == Decimal(0):
        return Decimal(0)
    return loading * growth_rate / (Decimal(1) + growth_rate)


def run_dcf(
    revenue: Optional[Decimal],
    growth_rate: Decimal,
    cash_flow_margin: Decimal,
    discount_rate: Decimal,
    terminal_growth: Decimal,
    years: int = 5,
    # --- FCFF build-up (optional; default None collapses to sales-margin model) ---
    ebitda_margin: Optional[Decimal] = None,
    depreciation_margin: Optional[Decimal] = None,  # D&A as a fraction of revenue
    tax_rate: Optional[Decimal] = None,
    capex_margin: Optional[Decimal] = None,  # capital expenditure as a fraction of revenue
    nwc_change_margin: Optional[Decimal] = None,  # change in net working capital / revenue
    # --- Equity / FCFE (optional) -------------------------------------------
    shares_outstanding: Optional[Decimal] = None,
    net_debt: Optional[Decimal] = None,  # interest-bearing debt minus cash (FCFE bridge)
) -> DCFResult:
    """Run a 2-stage DCF (explicit projection + terminal value).

    Projects ``revenue`` forward ``years`` periods at ``growth_rate``, then builds
    free cash flow. Two build-up paths are supported:

    1. **Sales-margin (simple)**: FCF = revenue x ``cash_flow_margin`` (the original
       model).
    2. **FCFF build-up**: when EBITDA-margin/capex/nwc components are supplied, FCF
       is built bottom-up as EBITDA - D&A - tax - capex - change in NWC (the true
       free-cash-flow-to-firm construct).

    ``cash_flow_margin`` always acts as the fallback when the FCFF build-up inputs
    are absent. Terminal value is a Gordon perpetuity on final-year FCF. When
    ``shares_outstanding`` and ``net_debt`` are supplied, a FCFE-style
    ``intrinsic_equity`` (intrinsic EV - net debt) and an
    ``intrinsic_price_per_share`` are also returned.
    """
    if revenue is None or revenue <= 0:
        return DCFResult(None, reason="missing or non-positive current revenue")
    if not (0 < discount_rate < 1):
        return DCFResult(None, reason="discount rate must be in (0, 1)")
    if not (0 <= terminal_growth < discount_rate):
        return DCFResult(None, reason="terminal growth must be 0 <= g < discount rate")
    if years < 1:
        return DCFResult(None, reason="projection window must be >= 1 year")

    g = growth_rate
    r = discount_rate
    tv = terminal_growth
    m = cash_flow_margin

    use_fcff_buildup = all(
        v is not None
        for v in (
            ebitda_margin,
            depreciation_margin,
            tax_rate,
            capex_margin,
            nwc_change_margin,
        )
    )

    def fcf_for(rev: Decimal) -> Decimal:
        """Free cash flow to firm for a given year's revenue."""
        if use_fcff_buildup:
            ebitda = rev * ebitda_margin  # type: ignore[operator]
            da = rev * depreciation_margin  # type: ignore[operator]
            ebit = ebitda - da
            nopat = ebit * (Decimal(1) - tax_rate)  # type: ignore[operator]
            capex = rev * capex_margin  # type: ignore[operator]
            nwc = rev * nwc_change_margin  # type: ignore[operator]
            return nopat + da - capex - nwc
        return rev * m

    def fcf_series() -> list[Decimal]:
        flows = []
        for t in range(1, years + 1):
            rev = revenue * ((Decimal(1) + g) ** t)
            flows.append(fcf_for(rev))
        return flows

    flows = fcf_series()
    pv_series = _discount(flows, r)

    final_fcf = fcf_for(revenue * ((Decimal(1) + g) ** years))
    terminal_value = final_fcf * (Decimal(1) + tv) / (r - tv)
    pv_terminal = terminal_value / ((Decimal(1) + r) ** years)

    intrinsic_ev = pv_series + pv_terminal

    assumptions = {
        "growth_rate": g,
        "cash_flow_margin": m,
        "discount_rate": r,
        "terminal_growth": tv,
        "years": years,
        "fcff_buildup": use_fcff_buildup,
    }
    if use_fcff_buildup:
        assumptions.update(
            {
                "ebitda_margin": ebitda_margin,
                "depreciation_margin": depreciation_margin,
                "tax_rate": tax_rate,
                "capex_margin": capex_margin,
                "nwc_change_margin": nwc_change_margin,
            }
        )

    intrinsic_equity = None
    intrinsic_price = None
    if net_debt is not None:
        intrinsic_equity = intrinsic_ev - net_debt
        if shares_outstanding and shares_outstanding > 0:
            intrinsic_price = intrinsic_equity / shares_outstanding

    return DCFResult(
        intrinsic_ev,
        intrinsic_equity=intrinsic_equity,
        intrinsic_price_per_share=intrinsic_price,
        assumptions=assumptions,
    )
