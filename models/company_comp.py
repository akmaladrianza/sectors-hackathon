"""Comparable-companies (comps) screener data model.

Defines the :class:`CompanyComp` Pydantic model representing a single row of
comparable-company data, plus the :class:`Currency` enum used for
cross-market normalization.

Key design goals
----------------
1. ``Decimal`` for monetary magnitudes (``market_cap``, ``ebitda``, ``revenue``,
   ...) to avoid floating-point precision errors on large financial figures.
2. ``Optional`` on every field except stable identifiers (``ticker``, ``sector``)
   because real-world data feeds frequently have missing values.
3. All valuation multiples are *derived* via :meth:`pydantic.computed_field`,
   so they cannot go stale or inconsistent with their underlying raw numbers,
   and a missing ``market_cap`` degrades gracefully to ``None`` instead of
   raising while computing downstream multiples.
4. An ``is_screenable`` flag lets the screener distinguish "peer with no data"
   from "peer that failed a range filter", and report exclusions explicitly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_serializer,
    model_validator,
)


class Currency(str, Enum):
    """Base currency used for reporting this company's financials."""

    USD = "USD"
    EUR = "EUR"
    IDR = "IDR"
    SGD = "SGD"
    GBP = "GBP"
    JPY = "JPY"


class CompanyComp(BaseModel):
    """A single company's data row for comparable-company analysis."""

    model_config = ConfigDict(
        # No json_encoders: deprecated since Pydantic V2.0 and slated for removal
        # in V3.0. Pydantic v2 serializes Decimal to a JSON string by default;
        # the per-field serializer below instead emits JSON numbers (floats) for
        # the monetary fields so clients get numeric values.
    )

    # --- Identification ---------------------------------------------------
    ticker: str = Field(..., min_length=1, description="Exchange ticker symbol, e.g. 'BBCA.JK'")
    company_name: str = Field(..., min_length=1, description="Full legal / common company name")
    sector: str = Field(..., min_length=1, description="Top-level GICS-style sector for grouping")
    sub_sector: Optional[str] = Field(None, description="Finer grouping within sector")
    industry: Optional[str] = Field(None, description="Narrowest industry classification")
    country: Optional[str] = Field(None, description="ISO 3166-1 alpha-3 country code")
    exchange: Optional[str] = Field(None, description="e.g. 'IDX', 'NASDAQ', 'SGX'")
    currency: Currency = Field(default=Currency.USD, description="Reporting currency")

    # --- Market data (raw) ------------------------------------------------
    price: Optional[Decimal] = Field(None, ge=0, description="Latest share price")
    shares_outstanding: Optional[Decimal] = Field(None, ge=0, description="Fully diluted shares")
    market_cap: Optional[Decimal] = Field(
        None, ge=0, description="Market capitalization. Backfilled from price * shares if omitted."
    )

    # --- Balance sheet (raw) ---------------------------------------------
    total_debt: Optional[Decimal] = Field(None, description="Total interest-bearing debt")
    cash_and_equivalents: Optional[Decimal] = Field(None, ge=0, description="Cash + short-term investments")
    total_assets: Optional[Decimal] = Field(None, ge=0, description="Total assets")
    total_liabilities: Optional[Decimal] = Field(None, ge=0, description="Total liabilities")
    total_equity: Optional[Decimal] = Field(
        None, ge=0, description="Book value of equity (total_assets - total_liabilities). "
        "Used for a true price-to-book ratio instead of the total_assets approximation."
    )

    # --- Working-capital inputs (raw, latest fiscal-year row) ----------------
    # Exposed so the DCF can derive AR/Inventory/AP days from *real* balance-sheet
    # fields (residual receivables/payables) rather than a flat placeholder. Sectors
    # does not surface trade receivables/payables directly; these are the closest
    # disclosures. All optional; banks typically leave cost_of_revenue/inventories absent.
    current_assets: Optional[Decimal] = Field(None, ge=0, description="Current assets")
    current_liabilities: Optional[Decimal] = Field(None, ge=0, description="Current liabilities")
    inventories: Optional[Decimal] = Field(None, ge=0, description="Inventories")
    cost_of_revenue: Optional[Decimal] = Field(None, ge=0, description="Cost of revenue")
    prepaid_assets: Optional[Decimal] = Field(None, ge=0, description="Prepaid assets")
    short_term_debt: Optional[Decimal] = Field(None, ge=0, description="Short-term interest-bearing debt")

    # --- Income statement / profitability (raw, TTM) ----------------------
    revenue: Optional[Decimal] = Field(None, ge=0, description="Trailing-twelve-month revenue")
    ebitda: Optional[Decimal] = Field(None, description="TTM EBITDA")
    ebit: Optional[Decimal] = Field(None, description="TTM operating income")
    net_income: Optional[Decimal] = Field(None, description="TTM net income")
    eps: Optional[Decimal] = Field(None, description="TTM earnings per share")

    # --- Cash-flow / reinvestment (raw, latest FY) --------------------------
    # Exposed so the DCF builder can ground capex on the company's *own* audited
    # reinvestment behaviour (capex/EBITDA, capex/D&A, reinvestment rate, fixed-asset
    # turnover) instead of a flat %-of-revenue assumption. Sectors supplies these in
    # ``historical_financials`` for most non-bank large caps.
    # NOTE: no ``ge=0`` here. Sectors reports ``capital_expenditure`` net of asset
    # disposals, so a company that sold more fixed assets than it bought in a given
    # FY legitimately shows a *negative* capex (e.g. PIPA: -483,092,039 while EBITDA
    # is positive). Rejecting it would hard-crash the whole ticker at the model
    # layer. A negative capex is instead surfaced as a non-fatal ``data_quality_flags``
    # warning (mirroring the negative-intrinsic_value pattern) and skipped by the
    # capex-based benchmark anchors — it never silently flows into a ratio.
    capital_expenditure: Optional[Decimal] = Field(None, description="Capital expenditure (latest FY, net of disposals — can be negative)")
    depreciation_amortization: Optional[Decimal] = Field(None, description="Depreciation & amortization (latest FY)")
    fixed_assets: Optional[Decimal] = Field(None, ge=0, description="Net fixed assets (latest FY)")
    operating_cash_flow: Optional[Decimal] = Field(None, description="Operating cash flow (latest FY)")
    free_cash_flow: Optional[Decimal] = Field(None, description="Free cash flow (latest FY)")
    tax_expense: Optional[Decimal] = Field(None, description="Tax expense (latest FY)")
    retained_earnings: Optional[Decimal] = Field(None, description="Retained earnings (latest FY)")

    # --- Growth (raw, YoY) ------------------------------------------------
    revenue_growth_yoy: Optional[float] = Field(None, description="e.g. 0.15 for +15%")
    ebitda_growth_yoy: Optional[float] = Field(None, description="e.g. 0.15 for +15%")

    # --- Margins (raw) ----------------------------------------------------
    gross_margin: Optional[float] = Field(None, description="Gross margin, fraction of revenue")
    ebitda_margin: Optional[float] = Field(None, description="EBITDA margin, fraction of revenue")
    net_margin: Optional[float] = Field(None, description="Net margin, fraction of revenue")

    # --- Metadata ---------------------------------------------------------
    as_of_date: Optional[date] = Field(None, description="Date financials are reported as of")
    fiscal_period: Optional[str] = Field(None, description="e.g. 'FY2024', 'Q3 2025 TTM'")

    # --- Sectors-native valuation (fair-value benchmark) -------------------
    # These come from the Sectors API's own ``valuation`` report section, NOT our
    # own re-derivation: ``intrinsic_value`` is Sectors' disclosed fair-value/share
    # figure and ``forward_pe`` / peer-average multiples are Sectors' server-side
    # comps benchmark. They are load-bearing, defensible inputs (Sectors-native),
    # distinct from the ``computed_field`` multiples below which we derive locally.
    intrinsic_value: Optional[Decimal] = Field(
        None, description="Sectors' own fair-value / intrinsic share price"
    )
    forward_pe: Optional[float] = Field(None, description="Sectors' forward P/E")
    pe_peer_avg: Optional[float] = Field(None, description="Sectors' P/E peer average")
    pb_peer_avg: Optional[float] = Field(None, description="Sectors' P/B peer average")
    ps_peer_avg: Optional[float] = Field(None, description="Sectors' P/S peer average")

    # --- Validation: backfill market_cap when possible --------------------
    @model_validator(mode="after")
    def _fill_market_cap(self) -> "CompanyComp":
        """Derive ``market_cap`` from ``price * shares_outstanding`` if omitted."""
        if (
            self.market_cap is None
            and self.price is not None
            and self.shares_outstanding is not None
        ):
            self.market_cap = self.price * self.shares_outstanding
        return self

    # --- Validation: backfill total_equity when possible ------------------
    @model_validator(mode="after")
    def _fill_total_equity(self) -> "CompanyComp":
        """Derive ``total_equity = total_assets - total_liabilities`` if omitted.

        Both raw balance-sheet figures are disclosed for IDX banks/industrials,
        so this lets the mapper supply them without storing a redundant derived
        value, and enables a true (non-approximate) price-to-book ratio.
        """
        if (
            self.total_equity is None
            and self.total_assets is not None
            and self.total_liabilities is not None
        ):
            equity = self.total_assets - self.total_liabilities
            if equity >= 0:
                self.total_equity = equity
        return self

    # --- Derived: valuation multiples ------------------------------------
    # These are computed (not stored) so a missing raw input propagates to
    # ``None`` cleanly instead of raising, and so the multiples can never
    # diverge from their underlying figures.

    @computed_field
    @property
    def enterprise_value(self) -> Optional[Decimal]:
        """EV = market cap + total debt - cash. ``None`` if market cap is missing."""
        if self.market_cap is None:
            return None
        debt = self.total_debt or Decimal(0)
        cash = self.cash_and_equivalents or Decimal(0)
        return self.market_cap + debt - cash

    @computed_field
    @property
    def ev_to_ebitda(self) -> Optional[float]:
        """Enterprise value / EBITDA. ``None`` if EV or EBITDA is unusable."""
        ev = self.enterprise_value
        if ev is None or not self.ebitda or self.ebitda == 0:
            return None
        return float(ev / self.ebitda)

    @computed_field
    @property
    def ev_to_revenue(self) -> Optional[float]:
        """Enterprise value / revenue. ``None`` if EV or revenue is unusable."""
        ev = self.enterprise_value
        if ev is None or not self.revenue or self.revenue == 0:
            return None
        return float(ev / self.revenue)

    @computed_field
    @property
    def pe_ratio(self) -> Optional[float]:
        """Price / EPS (independently computable even without market cap)."""
        if self.price is None or not self.eps or self.eps == 0:
            return None
        return float(self.price / self.eps)

    @computed_field
    @property
    def roe(self) -> Optional[float]:
        """Return on equity = net_income / total_equity (book value of equity).

        The quality driver behind P/B: per the Gordon-growth-derived "justified P/B"
        relationship (``P/B = (ROE - g) / (r - g)``), a company's fair P/B is a
        function of its *own* ROE, not a peer-group average. Used by
        ``engine.implied_valuation`` to normalize peer P/B multiples by ROE before
        applying them to a subject with a different (often higher, for a market
        leader) ROE. ``None`` if net income or a usable (positive) book equity is
        missing — never a fabricated ratio.
        """
        if self.net_income is None or not self.total_equity or self.total_equity <= 0:
            return None
        return float(self.net_income / self.total_equity)

    @computed_field
    @property
    def price_to_book(self) -> Optional[float]:
        """Market cap / book value of equity (true P/B).

        Uses ``total_equity`` (book value of equity), not ``total_assets`` — the
        textbook definition. ``total_equity`` is either supplied directly or
        backfilled as ``total_assets - total_liabilities`` by ``_fill_total_equity``.
        ``None`` if market cap or equity is missing/zero.
        """
        equity = self.total_equity
        if self.market_cap is None or not equity or equity == 0:
            return None
        return float(self.market_cap / equity)

    @computed_field
    @property
    def intrinsic_upside(self) -> Optional[float]:
        """Upside/downside of the current price vs Sectors' own intrinsic value.

        ``(intrinsic_value / price) - 1`` as a signed fraction (e.g. ``0.12`` for
        +12%). ``None`` if either the price or the disclosed intrinsic value is
        missing/non-positive. This is a Sectors-native comparison (their own fair-value
        figure against their own last-close price), not our forecast.

        A **negative** ``intrinsic_value`` (Sectors occasionally returns one, e.g. for
        distressed/over-levered names whose own model yields a negative fair-value) is
        treated as unusable — it is not a meaningful "fair price" to compute upside
        against, so it degrades to ``None`` rather than producing a nonsensical gain.
        """
        if (
            self.price is None
            or self.intrinsic_value is None
            or self.intrinsic_value <= 0
        ):
            return None
        return float(self.intrinsic_value / self.price - 1)

    @computed_field
    @property
    def is_screenable(self) -> bool:
        """True if enough data exists to compute the core valuation multiples.

        A company missing ``market_cap``, a non-positive ``ebitda``, or a
        missing/non-positive ``revenue`` cannot produce a meaningful EV-based
        multiple, so the screener should treat it as "excluded for data reasons"
        rather than silently skipping it (see ``exclusion_reasons`` for the full
        set of reasons).
        """
        return not self.exclusion_reasons

    @computed_field
    @property
    def exclusion_reasons(self) -> list[str]:
        """Human-readable reasons this company cannot be screened on EV multiples.

        Empty list means the company is screenable. Partnered with
        ``is_screenable`` so downstream code / UIs can report *why* a peer was
        excluded rather than just that it was skipped.
        """
        reasons: list[str] = []
        if self.market_cap is None:
            reasons.append("missing market_cap")
        if self.ebitda is None:
            reasons.append("missing ebitda")
        elif self.ebitda <= 0:
            reasons.append("non-positive ebitda")
        # Symmetry with ev_to_revenue: a missing/zero revenue means EV/Revenue is
        # None with no way to surface *why* — so record it here too.
        if self.revenue is None:
            reasons.append("missing revenue")
        elif self.revenue <= 0:
            reasons.append("non-positive revenue")
        return reasons

    @computed_field
    @property
    def data_quality_flags(self) -> list[str]:
        """Non-fatal data-quality warnings (do NOT make the company unscreenable).

        Distinct from ``exclusion_reasons`` (hard exclusions that gate
        ``is_screenable``). These are soft warnings surfaced in the UI so a user knows
        *why* a specific Sectors-native field (most notably ``intrinsic_value``) was
        treated as unusable, without dropping an otherwise screenable company. A
        negative ``intrinsic_value`` — typically Sectors signalling distress or a
        heavy leverage burden — falls here: we exclude that number from the
        implied-valuation/Sectors-IV path, but the company's comps multiples remain
        valid.
        """
        flags: list[str] = []
        if self.intrinsic_value is not None and self.intrinsic_value < 0:
            flags.append("negative Sectors intrinsic value (excluded from Sectors-intrinsic-value comparison)")
        if self.capital_expenditure is not None and self.capital_expenditure < 0:
            flags.append("negative capital expenditure (net of disposals) — capex-based benchmarks skipped")
        return flags

    # --- Serialization: float semantics for Decimal monetary fields -------
    @field_serializer("market_cap", "price", "shares_outstanding", "total_debt",
                      "cash_and_equivalents", "total_assets", "revenue", "ebitda",
                      "ebit", "net_income", "eps", "enterprise_value",
                      "intrinsic_value", when_used="json")
    def _serialize_decimal(self, value: Optional[Decimal]) -> Optional[float]:
        if value is None:
            return None
        return float(value)
