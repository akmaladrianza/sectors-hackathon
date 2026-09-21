"""Valuation engine package.

Pure functions that join the sibling models (`CompanyComp`, `MiningOverlay`) to
produce cross-model ratios (EV/tonne, and later the comps screener/ranking).
"""

from engine.mining_valuation import (
    EVPerTonne,
    ev_to_tonne_of_reserves,
    ev_to_tonne_of_resources,
)
from engine.implied_valuation import (
    ImpliedPrice,
    ImpliedValuation,
    build_implied_valuation,
    comps_implied_prices,
)
from engine.dcf import (
    working_capital_days_to_margin,
    nwc_change_margin_from_days,
)
from engine.football_field import build_football_field, FootballFieldRow
from engine.peer_lookup import lookup_peers, PeerLookupResult

__all__ = [
    "EVPerTonne",
    "ev_to_tonne_of_reserves",
    "ev_to_tonne_of_resources",
    "ImpliedPrice",
    "ImpliedValuation",
    "build_implied_valuation",
    "comps_implied_prices",
    "working_capital_days_to_margin",
    "nwc_change_margin_from_days",
    "build_football_field",
    "FootballFieldRow",
    "lookup_peers",
    "PeerLookupResult",
]
