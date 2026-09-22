"""Sector-conditional proxy library: default DCF growth assumptions by sector.

The DCF needs a revenue-growth assumption; rather than one blanket number for every
company, the proxy library supplies a *default* by sector that the user can override
in Advanced mode:

- **bank**    -> GDP growth + a spread (documented constant, clearly an assumption).
- **miner**   -> historical *revenue* CAGR, scaled by a forward commodity-price
                 assumption (we do NOT store multi-year production history, so true
                 "production x price" is not computeable from the current model).
- **generic** -> historical revenue CAGR from ``historical_financials``.

These are *defaults to seed a DCF*, not validated forecasts. The ``backtest`` module
performs a lightweight sanity check (proxy vs. realised historical growth) — see
``scripts/backtest_proxies.py``. Nothing here fabricates data: if the historical series
is too short/empty, the proxy returns ``None`` with a reason rather than guessing.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from models.company_comp import CompanyComp
from models.mining_overlay import MiningOverlay
from growth import revenue_series as _revenue_series_fn


# --- Documented assumption constants ---------------------------------------

# Indonesia long-run nominal GDP growth, used as the bank proxy's base. This is a
# *stated assumption*, not a Sectors fact — surfaced to the user in Advanced mode.
IDN_GDP_GROWTH = Decimal("0.05")  # 5% nominal

# Spread added on top of GDP for a large, established bank (loan growth tends to
# modestly exceed nominal GDP). Again, a documented assumption.
BANK_GROWTH_SPREAD = Decimal("0.03")  # +3%

# Long-run commodity-price growth assumption for the miner proxy (commodities in USD
# are roughly flat in real terms over a cycle; nominal ~2% inflation).
COMMODITY_PRICE_GROWTH = Decimal("0.02")


class Proxy:
    """A default DCF growth assumption, with provenance (source + reason)."""

    def __init__(self, value: Optional[Decimal], source: str, reason: Optional[str] = None) -> None:
        self.value = value
        self.source = source
        self.reason = reason

    @property
    def available(self) -> bool:
        return self.value is not None


def _dec(v) -> Optional[Decimal]:
    """Local Decimal coercion (kept for the proxy's own value formatting)."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


# Historical-growth helpers are shared with ``mapper.mapper`` via ``growth`` so the
# mapper doesn't trigger an engine-package import cycle. Re-exported below so the
# proxy library keeps a single, documented entry point for DCF-default callers.
def _revenue_series(raw_hist: Optional[list]) -> list[Decimal]:
    return _revenue_series_fn(raw_hist)


def _cagr(series: list[Decimal]) -> Optional[Decimal]:
    from growth import cagr

    return cagr(series)


def classify_proxy(
    comp: CompanyComp, overlay: Optional[MiningOverlay] = None
) -> str:
    """Return one of ``"bank" | "miner" | "generic"`` for a company."""
    sub_sector = (comp.sub_sector or comp.sector or "").strip().lower()
    if sub_sector == "banks":
        return "bank"
    if overlay is not None and overlay.has_performance_data:
        return "miner"
    return "generic"


def default_growth(
    comp: CompanyComp,
    overlay: Optional[MiningOverlay] = None,
    raw_hist: Optional[list] = None,
) -> Proxy:
    """Return the sector-conditional default revenue-growth proxy.

    ``raw_hist`` is the ``financials.historical_financials`` list from the report
    payload (needed for the generic CAGR; banks/miners use documented constants +
    their own data where available).
    """
    kind = classify_proxy(comp, overlay)

    if kind == "bank":
        return Proxy(
            IDN_GDP_GROWTH + BANK_GROWTH_SPREAD,
            source="IDN GDP growth (5%) + bank spread (3%) — stated assumption",
        )

    if kind == "miner":
        # We do NOT hold multi-year production history (CommodityStat keeps only the
        # latest production_volume per commodity), so we fall back to historical
        # *revenue* CAGR scaled by a small forward commodity-price assumption. This is
        # an honest fallback, not "production x price" — documented so it isn't
        # mistaken for the richer methodology.
        series = _revenue_series(raw_hist)
        cagr = _cagr(series)
        if cagr is not None:
            return Proxy(
                cagr * (Decimal(1) + COMMODITY_PRICE_GROWTH),
                source="historical revenue CAGR x forward commodity-price assumption (2%)",
            )
        return Proxy(
            None,
            source="miner",
            reason="insufficient revenue history to derive a growth proxy",
        )

    # generic
    series = _revenue_series(raw_hist)
    cagr = _cagr(series)
    if cagr is not None:
        return Proxy(cagr, source="historical revenue CAGR")
    return Proxy(None, source="generic", reason="insufficient revenue history")
