"""Reserve-adjusted mining overlay model (sibling to ``CompanyComp``).

A ``MiningOverlay`` holds a miner's *production / reserve* figures (the tonnage
that ``CompanyComp``'s ``enterprise_value`` is divided by to produce EV/tonne
metrics). The EV/tonne ratio itself is computed at the engine/screener layer,
because ``enterprise_value`` lives on ``CompanyComp`` — this model carries only
the mining-extension inputs, consistent with the architecture's "sibling model,
joined by ticker/slug" design (see ``architectureOverview.md``).

Key data-source reality (discovered empirically against the live v2 API):
- ``/v2/mining/companies/performance/{slug}/`` returns per-commodity entries, but
  ``resources_reserves.total_reserves_Mt`` is repeated identically across every
  commodity (it is a *company-level* reserve total, not per-commodity).
- ``total_reserves_Mt`` / ``total_resources_Mt`` may be ``None`` for holding
  companies (e.g. MDKA reports a company-level figure only on the performance
  endpoint; its financials/sales-destination endpoints 404 — no data).
- ``measurement_year`` is the **reserve price-deck vintage** — the year the
  reserve statement's commodity-price assumptions were struck against. This is
  surfaced explicitly (rather than assumed) as a defensibility flag.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CommodityStat(BaseModel):
    """One commodity's production/reserve line within a performance payload."""

    model_config = ConfigDict(extra="ignore")

    commodity_type: str = Field(..., min_length=1)
    unit: Optional[str] = None
    mining_operation_status: Optional[str] = None
    production_volume: Optional[Decimal] = Field(None, ge=0)
    sales_volume: Optional[Decimal] = Field(None, ge=0)
    # Company-level (not per-commodity) reserve/resource figures; repeated across
    # commodities by the API, so they're identical for every entry.
    total_reserves_Mt: Optional[Decimal] = Field(None, ge=0)
    total_resources_Mt: Optional[Decimal] = Field(None, ge=0)
    measurement_year: Optional[int] = None


class MiningOverlay(BaseModel):
    """Reserve/production snapshot for one mining company.

    ``financials`` and ``sales_destination`` are optional because many miners
    (including the MDKA seed, a holding) expose *performance* data but 404 on the
    other two endpoints. Their absence is recorded via flags, not silently.
    """

    model_config = ConfigDict(extra="ignore")

    ticker: str = Field(..., min_length=1)
    slug: Optional[str] = None
    company_name: Optional[str] = None

    # Performance (per-commodity) -------------------------------------------
    commodities: list[CommodityStat] = Field(default_factory=list)
    has_performance_data: bool = False

    # Financials (USD, optional) --------------------------------------------
    revenue_usd: Optional[Decimal] = None
    net_profit_usd: Optional[Decimal] = None
    assets_usd: Optional[Decimal] = None
    has_financials_data: bool = False

    # Sales destination (optional) ------------------------------------------
    # country -> volume (Mt) where reported. Inconsistent across countries:
    # some report volume, some report % of sales volume, some report revenue —
    # so we keep only the raw country->volume map and defer concentration math.
    sales_destination_volume: dict[str, Optional[Decimal]] = Field(default_factory=dict)
    has_sales_destination_data: bool = False

    @computed_field
    @property
    def total_reserves_Mt(self) -> Optional[Decimal]:
        """Company-level reserve total (repeated identically across commodities)."""
        for c in self.commodities:
            if c.total_reserves_Mt is not None:
                return c.total_reserves_Mt
        return None

    @computed_field
    @property
    def total_resources_Mt(self) -> Optional[Decimal]:
        for c in self.commodities:
            if c.total_resources_Mt is not None:
                return c.total_resources_Mt
        return None

    @computed_field
    @property
    def reserve_vintage_year(self) -> Optional[int]:
        """The measurement_year the reserve statement was struck against."""
        for c in self.commodities:
            if c.measurement_year is not None:
                return c.measurement_year
        return None

    @computed_field
    @property
    def commodity_types(self) -> list[str]:
        return [c.commodity_type for c in self.commodities]

    @computed_field
    @property
    def is_self_reported(self) -> bool:
        """Reserve figures are company self-reported (Sectors aggregates filings).

        Always True for this source: the mining extension is built from company
        disclosures, which are not independently audited the way financial
        statements are. Surfaced as a defensibility flag per the product brief.
        """
        return True

