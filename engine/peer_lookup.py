"""Same-sub-sector peer lookup for the football-field chart.

The comparables table shows whatever tickers the user typed, but a *fair* multiples
comparison requires peers from the same industry — comparing BBCA (bank) to BUMI
(coal) is meaningless. This module resolves a company's *true* peers from Sectors by
matching on ``sub_sector`` (narrower than ``sector``), so the football-field ranges
reflect the company's actual industry, not an arbitrary ticker list.

Resolution path (two steps):
1. ``GET /v2/companies/?where=sub_sector='<slug>'`` — the Companies Screener returns
   the *list of tickers* in the same sub-sector. (Important: the screener's ``results``
   only carry ``symbol``/``company_name`` — it never returns multiples, so step 2 is
   required.)
2. For each peer ticker, pull its ``company_report`` (``overview`` + ``financials``)
   through the shared cache and map it via ``report_to_company_comp`` — the same
   tested pipeline the main screener uses — producing real ``CompanyComp`` objects
   whose ``ev_to_ebitda`` / ``ev_to_revenue`` / ``pe_ratio`` / ``price_to_book`` are
   computed fields (never silently sourced from a nonexistent screener field).

The sub_sector slug is derived from the company's ``sub_sector`` display name by
kebab-casing it (e.g. "Banks" -> "banks", "Basic Materials" -> "basic-materials"),
which matches Sectors' slug convention.

Cost note: each peer costs ~2 credits (``overview`` + ``financials`` reports). Callers
should cap ``limit`` and cache results per session to bound spend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cache.sqlite_cache import SQLiteCache
from mapper.mapper import report_to_company_comp, MapperError
from models.company_comp import CompanyComp
from sectors_client.client import SectorsClient, SectorsAPIError, BASE_URL


def _slugify(name: Optional[str]) -> Optional[str]:
    """Kebab-case a display name into a Sectors slug."""
    if not name:
        return None
    return name.strip().lower().replace(" & ", "-").replace(" ", "-")


# Minimum ticker count for the *narrower* industry-level match before widening back
# to ``sub_sector``. Below this, a "median" is just an average of one or two peers and
# has no outlier resistance — so widen the taxonomy rather than trust a 2-peer median.
_MIN_INDUSTRY_PEERS = 3


@dataclass
class PeerLookupResult:
    """Same-sub-sector peers resolved for one subject company.

    ``peers`` are fully-mapped ``CompanyComp`` instances (real computed multiples),
    not raw screener dicts. ``skipped`` counts peers that were identified by the
    screener but failed to map (e.g. sparse data) — surfaced for auditability rather
    than silently dropped.
    """

    subject: CompanyComp
    peers: list[CompanyComp] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # tickers that failed to map
    reason: Optional[str] = None

    @property
    def has_peers(self) -> bool:
        return bool(self.peers)


def _resolve_peers(
    subject: CompanyComp,
    client: SectorsClient,
    cache: Optional[SQLiteCache] = None,
    limit: int = 5,
) -> PeerLookupResult:
    """Resolve same-industry peers: screener ticker list -> mapped CompanyComps.

    Matches on ``industry`` first (narrower than ``sub_sector`` — see the module
    docs + the confirmed Sectors taxonomy: ``sector`` → ``sub_sector`` → ``industry``
    → ``sub_industry``, e.g. Basic Materials splits into Chemicals, Containers &
    Packaging, Metals & Minerals, Forestry & Paper at the ``industry`` level). Falls
    back to ``sub_sector`` when the industry match returns fewer than
    ``_MIN_INDUSTRY_PEERS`` tickers.
    """
    subject_base = subject.ticker.split(".")[0]
    industry_slug = _slugify(subject.industry)
    sub_sector_slug = _slugify(subject.sub_sector or subject.sector)

    def _fetch(where_field: str, slug: str) -> list[str]:
        payload = client.request(
            f"{BASE_URL}/v2/companies/",
            params={"where": f"{where_field} = '{slug}'", "limit": str(limit + 5)},
        )
        return [
            r["symbol"].replace(".JK", "")
            for r in (payload.get("results") or [])
            if r.get("symbol") and r["symbol"].replace(".JK", "") != subject_base
        ][:limit]

    tickers: list[str] = []
    tried = "industry" if industry_slug else "sub_sector"
    if industry_slug and industry_slug != sub_sector_slug:
        try:
            industry_tickers = _fetch("industry", industry_slug)
        except SectorsAPIError:
            return PeerLookupResult(subject=subject, reason="screener peer lookup failed")
        if len(industry_tickers) >= _MIN_INDUSTRY_PEERS:
            tickers = industry_tickers
        elif sub_sector_slug:
            # Too few industry peers to trust a median — widen to sub_sector.
            tried = "sub_sector"
            try:
                tickers = _fetch("sub_sector", sub_sector_slug)
            except SectorsAPIError:
                return PeerLookupResult(subject=subject, reason="screener peer lookup failed")
        else:
            tickers = industry_tickers
    elif sub_sector_slug:
        tried = "sub_sector"
        try:
            tickers = _fetch("sub_sector", sub_sector_slug)
        except SectorsAPIError:
            return PeerLookupResult(subject=subject, reason="screener peer lookup failed")

    if not tickers:
        return PeerLookupResult(
            subject=subject, reason=f"no same-{tried} peers found ('{industry_slug or sub_sector_slug}')"
        )

    # Step 2: pull + map each peer through the shared report pipeline.
    peers: list[CompanyComp] = []
    skipped: list[str] = []
    endpoint = "company_report"
    for base in tickers:
        try:
            payload2 = None
            if cache is not None:
                payload2 = cache.get(base, "latest:peers", endpoint)
            if payload2 is None:
                payload2 = client.get_company_report(
                    base, sections=["overview", "financials"]
                )
                if cache is not None:
                    cache.set(base, "latest:peers", endpoint, payload2)
            comp, _t = report_to_company_comp(payload2)
            if comp.is_screenable:
                peers.append(comp)
            else:
                skipped.append(base)
        except (SectorsAPIError, MapperError):
            skipped.append(base)
        except Exception:  # noqa: BLE001
            skipped.append(base)

    return PeerLookupResult(subject=subject, peers=peers, skipped=skipped)


def lookup_peers(
    subject: CompanyComp,
    client: SectorsClient,
    cache: Optional[SQLiteCache] = None,
    limit: int = 5,
) -> PeerLookupResult:
    """Public entry point: resolve same-sub-sector peers for ``subject``."""
    return _resolve_peers(subject, client, cache=cache, limit=limit)


