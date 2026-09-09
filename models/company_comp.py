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

    # --- Income statement / profitability (raw, TTM) ----------------------
    revenue: Optional[Decimal] = Field(None, ge=0, description="Trailing-twelve-month revenue")
    ebitda: Optional[Decimal] = Field(None, description="TTM EBITDA")
    ebit: Optional[Decimal] = Field(None, description="TTM operating income")
    net_income: Optional[Decimal] = Field(None, description="TTM net income")
    eps: Optional[Decimal] = Field(None, description="TTM earnings per share")

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
    def price_to_book(self) -> Optional[float]:
        """Market cap / book value of equity.

        Note: this is an approximation using ``market_cap / total_assets``;
        true P/B requires ``total_equity = total_assets - total_liabilities``.
        ``None`` if either is unusable.
        """
        if self.market_cap is None or not self.total_assets or self.total_assets == 0:
            return None
        return float(self.market_cap / self.total_assets)

    @computed_field
    @property
    def is_screenable(self) -> bool:
        """True if enough data exists to compute the core valuation multiples.

        A company missing ``market_cap`` or a non-positive ``ebitda`` cannot
        produce a meaningful EV-based multiple, so the screener should treat it
        as "excluded for data reasons" rather than silently skipping it.
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
        return reasons

    # --- Serialization: float semantics for Decimal monetary fields -------
    @field_serializer("market_cap", "price", "shares_outstanding", "total_debt",
                      "cash_and_equivalents", "total_assets", "revenue", "ebitda",
                      "ebit", "net_income", "eps", "enterprise_value", when_used="json")
    def _serialize_decimal(self, value: Optional[Decimal]) -> Optional[float]:
        if value is None:
            return None
        return float(value)
