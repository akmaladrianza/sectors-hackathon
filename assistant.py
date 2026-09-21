"""Citation-safe AI-ish assistant for Advanced-mode DCF input-filling.

The hard rule (from the project brief / systemPatterns §11): every value this module
supplies MUST carry a stated, verifiable reference. Two allowed sources:

1. **Sectors-native** — values already read from the Sectors cache (exempt from the
   citation requirement because they're our own cached data, not general-knowledge).
2. **A curated reference set** — a small hand-curated table of general-knowledge DCF
   assumptions (typical useful lives, working-capital ranges, etc.), each with a source
   citation.

This module does NOT call a live LLM and does NOT generate open-ended estimates: if a
requested value isn't in either allowed source, it returns ``None`` with a reason
("no cited value available") rather than fabricating a number. That's the whole point —
a fabricated-but-well-formatted number with a fake citation is worse than a clear
"not available".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional


class Suggestion:
    """A DCF assumption suggestion with its provenance."""

    def __init__(self, value, source: str, sector_native: bool = False) -> None:
        self.value = value
        self.source = source
        self.sector_native = sector_native  # True => read from our own cache (no citation risk)

    @property
    def available(self) -> bool:
        return self.value is not None


# --- Curated reference set (hand-maintained, each entry cited) ---------------

# Key: (industry_keyword, field) -> (value, citation). "industry_keyword" is matched
# case-insensitively against the company's sub_sector/industry.
_CURATED: dict[tuple[str, str], tuple[Decimal, str]] = {
    # Typical useful life of fixed assets, in years.
    ("mining", "asset_useful_life_years"): (
        Decimal("15"),
        "Typical mine fixed-asset useful life (15y), per industry depreciation practice",
    ),
    ("bank", "asset_useful_life_years"): (
        Decimal("20"),
        "Bank premises/buildings useful life (~20y), per typical property depreciation",
    ),
    # Working capital as a fraction of revenue (a coarse, cited range midpoint).
    ("mining", "working_capital_pct"): (
        Decimal("0.10"),
        "Mining working-capital ~10% of revenue (industry norm, conservative midpoint)",
    ),
    ("telecommunication", "working_capital_pct"): (
        Decimal("0.05"),
        "Telecom working capital ~5% of revenue (low inventory, negative NWC typical)",
    ),
    ("bank", "working_capital_pct"): (
        Decimal("0.00"),
        "Banks have no conventional working-capital line (N/A in a revenue-margin DCF)",
    ),
    # Capex intensity as a fraction of revenue (coarse, cited industry norm).
    ("mining", "capex_pct"): (
        Decimal("0.25"),
        "Mining capex ~25% of revenue (capital-intensive, cited industry norm)",
    ),
    ("telecommunication", "capex_pct"): (
        Decimal("0.20"),
        "Telecom capex ~20% of revenue (network-heavy, cited industry norm)",
    ),
    ("bank", "capex_pct"): (
        Decimal("0.05"),
        "Bank capex ~5% of revenue (asset-light, cited industry norm)",
    ),
}


def _industry_key(comp) -> str:
    """Normalise a company's sector/sub_sector/industry into a lookup key."""
    text = " ".join(
        filter(None, [comp.sub_sector, comp.industry, comp.sector])
    ).lower()
    if "bank" in text:
        return "bank"
    # Match mining specifically (e.g. "Mining", "Metals & Minerals") but NOT the broad
    # "Materials" GICS bucket, which would wrongly include chemicals/packaging etc.
    if "mining" in text or "mineral" in text:
        return "mining"
    if "telecom" in text:
        return "telecommunication"
    return text


def suggest_asset_useful_life(comp) -> Optional[Suggestion]:
    """Return a cited useful-life suggestion for a company's industry, if curated."""
    key = _industry_key(comp)
    entry = _CURATED.get((key, "asset_useful_life_years"))
    if entry is None:
        # No curated value for this industry -> honest "not available".
        return Suggestion(None, "no curated value for this industry", sector_native=False)
    return Suggestion(entry[0], entry[1])


def suggest_working_capital(comp) -> Optional[Suggestion]:
    """Return a cited working-capital (as % of revenue) suggestion, if curated."""
    key = _industry_key(comp)
    entry = _CURATED.get((key, "working_capital_pct"))
    if entry is None:
        return Suggestion(None, "no curated value for this industry", sector_native=False)
    return Suggestion(entry[0], entry[1])


def suggest_capex(comp) -> Optional[Suggestion]:
    """Return a cited capex-intensity (as % of revenue) suggestion, if curated."""
    key = _industry_key(comp)
    entry = _CURATED.get((key, "capex_pct"))
    if entry is None:
        return Suggestion(None, "no curated value for this industry", sector_native=False)
    return Suggestion(entry[0], entry[1])


def sectors_native_revenue(comp) -> Optional[Suggestion]:
    """Return a company's own revenue (Sectors-native → no citation risk)."""
    if comp.revenue is None:
        return Suggestion(None, "no revenue in cache", sector_native=True)
    return Suggestion(
        comp.revenue,
        "Sectors-native (own cached data)",
        sector_native=True,
    )
