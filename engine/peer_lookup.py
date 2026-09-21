"""Same-sub-sector peer lookup for the football-field chart.

The comparables table shows whatever tickers the user typed, but a *fair* multiples
comparison requires peers from the same industry — comparing BBCA (bank) to BUMI
(coal) is meaningless. This module resolves a company's *true* peers from Sectors by
matching on ``sub_sector`` (narrower than ``sector``), so the football-field ranges
reflect the company's actual industry, not an arbitrary ticker list.

Two resolution paths (tried in order):
1. ``GET /v2/companies/?where=sub_sector='<slug>'`` — the Companies Screener, exact
   sub-sector peers.
2. The report's own ``peers`` section (fallback when the screener filter is
   unavailable).

The sub_sector slug is derived from the company's ``sub_sector`` display name by
kebab-casing it (e.g. "Banks" -> "banks", "Basic Materials" -> "basic-materials"),
which matches Sectors' slug convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models.company_comp import CompanyComp
from sectors_client.client import SectorsClient, SectorsAPIError, BASE_URL


def _slugify(name: Optional[str]) -> Optional[str]:
    """Kebab-case a sub_sector display name into a Sectors slug."""
    if not name:
        return None
    return name.strip().lower().replace(" & ", "-").replace(" ", "-")


@dataclass
class PeerLookupResult:
    """Same-sub-sector peers resolved for one subject company.

    ``rows`` are the raw Companies-Screener result dicts, each carrying the peer's
    ``symbol``, ``company_name``, ``sub_sector`` and its precomputed multiples
    (``pe``/``pb``/``ps``/``enterprise_to_ebitda``/``enterprise_to_revenue``) plus
    ``last_close_price`` and ``intrinsic_value``. Retaining raw rows (rather than
    reconstructing ``CompanyComp``) keeps Sectors' own server-computed multiples
    authoritative — we don't re-derive them from balance-sheet gaps.
    """

    subject: CompanyComp
    rows: list[dict] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def has_peers(self) -> bool:
        return bool(self.rows)


def _resolve_peers(
    subject: CompanyComp, client: SectorsClient, limit: int = 12
) -> PeerLookupResult:
    """Resolve same-sub-sector peers via the Companies Screener."""
    slug = _slugify(subject.sub_sector or subject.sector)
    if not slug:
        return PeerLookupResult(subject=subject, reason="no sub_sector/sector to match")

    try:
        payload = client.request(
            f"{BASE_URL}/v2/companies/",
            params={"where": f"sub_sector = '{slug}'", "limit": str(limit)},
        )
    except (SectorsAPIError, Exception):
        return PeerLookupResult(subject=subject, reason="screener peer lookup failed")

    results = payload.get("results") or []
    rows = [
        r
        for r in results
        if r.get("symbol") and r["symbol"] != subject.ticker.split(".")[0]
    ]
    return PeerLookupResult(subject=subject, rows=rows)


def lookup_peers(
    subject: CompanyComp, client: SectorsClient, limit: int = 12
) -> PeerLookupResult:
    """Public entry point: resolve same-sub-sector peers for ``subject``."""
    return _resolve_peers(subject, client, limit=limit)

