"""Reserve-adjusted valuation engine: EV / tonne of reserves (and resources).

Joins two sibling models that deliberately do NOT know about each other:

- ``CompanyComp.enterprise_value`` — market cap + total debt - cash (local currency).
- ``MiningOverlay.total_reserves_Mt`` / ``total_resources_Mt`` — ore-body tonnage.

The engine reads both and produces the ratios a mining analyst uses to compare a
miner's market value against what's in the ground. It never silently substitutes a
number: a missing input yields ``None`` with a stated reason, mirroring
``CompanyComp.exclusion_reasons``.

Unit note
---------
``enterprise_value`` is in the company's reporting currency (IDR for our IDX
seeds). ``total_reserves_Mt`` is in **megatonnes of ore** (rock mined), NOT metal
content — for MDKA the ore body is 430.8 Mt, shared across its Copper and Gold
operations. So the output unit is "(currency) EV per tonne of ore", a recognised
but coarse metric; it is NOT "EV per ounce of gold" or "EV per tonne of copper".
This is a real limitation surfaced in docstrings/UI rather than silently
misleading the reader.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from models.company_comp import CompanyComp
from models.mining_overlay import MiningOverlay


class EVPerTonne:
    """Result of an EV/tonne join, carrying the reason when it is unavailable."""

    def __init__(
        self,
        value: Optional[Decimal],
        reason: Optional[str] = None,
        unit: str = "EV/tonne (ore)",
    ) -> None:
        self.value = value
        self.reason = reason
        self.unit = unit

    @property
    def available(self) -> bool:
        return self.value is not None


def _divide(ev: Optional[Decimal], tonnes_Mt: Optional[Decimal]) -> EVPerTonne:
    if ev is None:
        return EVPerTonne(None, reason="missing enterprise_value (peer not screenable)")
    if tonnes_Mt is None or tonnes_Mt <= 0:
        return EVPerTonne(None, reason="missing or non-positive tonnage")
    # `tonnes_Mt` is in MEGATONNES (Mt = 1e6 tonnes). Convert to tonnes before
    # dividing so the result is a true EV-per-tonne, not EV-per-megatonne.
    tonnes = tonnes_Mt * Decimal(1_000_000)
    # EV per tonne — keep full Decimal precision; callers format as needed.
    return EVPerTonne(ev / tonnes)


def ev_to_tonne_of_reserves(comp: CompanyComp, overlay: MiningOverlay) -> EVPerTonne:
    """Enterprise value per tonne of *reserves* (proven + probable)."""
    return _divide(comp.enterprise_value, overlay.total_reserves_Mt)


def ev_to_tonne_of_resources(comp: CompanyComp, overlay: MiningOverlay) -> EVPerTonne:
    """Enterprise value per tonne of *resources* (broader than reserves)."""
    return _divide(comp.enterprise_value, overlay.total_resources_Mt)
