"""Multi-peer screener: batch a list of tickers into a comparable comps table.

Pulls each ticker via the Sectors client, maps it into a ``CompanyComp`` (and, for
miners, a ``MiningOverlay`` + EV/tonne), then partitions the batch into:

- **screenable** — peers with enough data to compare on valuation multiples.
- **excluded** — peers that can't be fairly compared, each with a human-readable
  reason (either ``CompanyComp.exclusion_reasons`` for data gaps, or a pull-level
  failure like a bad ticker / API error).

Design goals (consistent with the rest of the project):
- One bad ticker never aborts the whole batch — it is recorded as an exclusion.
- Exclusions are explicit and auditable, never silently dropped.
- SGX names are currently excluded outright with an honest "not yet supported" reason
  (there is no SGX mapper yet, and routing SGX through the IDX mapper would produce
  misleading results). The longer-term SGX decision — price multiples only, since the
  SGX schema lacks total_debt/cash — is documented in the Memory Bank but is NOT yet
  implemented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from cache.sqlite_cache import SQLiteCache
from engine.mining_valuation import EVPerTonne, ev_to_tonne_of_reserves, ev_to_tonne_of_resources
from mapper.mapper import MapperError, report_to_company_comp
from mapper.mining_overlay import map_mining_overlay
from models.company_comp import CompanyComp
from models.mining_overlay import MiningOverlay
from sectors_client.client import SectorsClient, SectorsAPIError


@dataclass
class Exclusion:
    """A peer that could not be screened, with the reason."""

    ticker: str
    reason: str


@dataclass
class ScreenedMiner:
    """A screenable IDX *mining* peer, carrying both its comps and mining metrics."""

    comp: CompanyComp
    overlay: MiningOverlay
    ev_per_tonne_reserves: EVPerTonne
    ev_per_tonne_resources: EVPerTonne


@dataclass
class ScreenerResult:
    """The output of a screening run."""

    screenable: list[CompanyComp] = field(default_factory=list)
    miners: list[ScreenedMiner] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)


# Known mining tickers → their mining-extension slug. This is the small hand-built
# map the architecture calls for (`companies.mining_slug`); it would eventually be
# sourced from `get_mining_companies` + a persistent `companies` table, but for the
# seed universe a literal map is simpler and deterministic.
MINING_SLUGS: dict[str, str] = {
    "MDKA": "pt-merdeka-copper-gold-tbk",
    "ADRO": "pt-alamtri-resources-indonesia-tbk",
}


def screen_tickers(
    tickers: list[str],
    client: Optional[SectorsClient] = None,
    cache: Optional[SQLiteCache] = None,
    mining_slugs: Optional[dict[str, str]] = None,
) -> ScreenerResult:
    """Screen a batch of tickers into screenable + excluded partitions.

    ``mining_slugs`` maps IDX ticker (no suffix) to a mining-extension slug so the
    screener can also join reserve metrics; defaults to the built-in seed map.

    ``cache`` (optional): an SQLiteCache keyed on ``(symbol, today, endpoint)``; if
    provided, company-report payloads are read/written there so repeated screener
    runs on the same universe don't re-burn API credits.
    """
    client = client or SectorsClient()
    mining_slugs = mining_slugs if mining_slugs is not None else MINING_SLUGS
    today = date.today().isoformat()

    result = ScreenerResult()

    for raw in tickers:
        ticker = raw.strip().upper()
        is_sgx = ticker.endswith(".SI")
        base = ticker.split(".")[0]

        # --- SGX: not yet mapped (early return, before any pull) --------------
        # The SGX report schema is structurally different from IDX (nested
        # balance_sheet_metrics/income_stmt_metrics, no total_debt/cash), and we
        # do not yet have an SGX mapper. Routing SGX through the IDX mapper would
        # produce misleading results, so we exclude SGX with an honest reason
        # rather than pretend to support it. (Eventually: SGX price-multiples-only.)
        if is_sgx:
            result.excluded.append(
                Exclusion(ticker, "SGX not yet supported (no SGX mapper)")
            )
            continue

        # --- Pull + map (never let one ticker abort the batch) ---------------
        endpoint = "company_report"
        cache_key = (base, today, endpoint)
        try:
            payload = None
            if cache is not None:
                payload = cache.get(*cache_key)
            if payload is None:
                payload = client.get_company_report(base, sections=["overview", "financials", "valuation"])
                if cache is not None:
                    cache.set(*cache_key, payload)
            comp, _template = report_to_company_comp(payload)
        except (SectorsAPIError, MapperError) as exc:
            result.excluded.append(Exclusion(ticker, f"pull/map failed: {exc}"))
            continue
        except Exception as exc:  # noqa: BLE001
            # Catch-all so a single unexpected ticker can't kill the batch, but
            # record the full error type so it isn't silently ignored.
            result.excluded.append(
                Exclusion(ticker, f"unexpected error ({type(exc).__name__}): {exc}")
            )
            continue

        # --- Data-quality exclusions (from the model itself) ------------------
        if not comp.is_screenable:
            result.excluded.append(
                Exclusion(ticker, "; ".join(comp.exclusion_reasons))
            )
            continue

        # --- Mining join (IDX miners only) ------------------------------------
        slug = mining_slugs.get(base)
        if slug:
            try:
                perf = client.get_mining_performance(slug)
                overlay = map_mining_overlay(ticker=ticker, slug=slug, performance=perf)
                result.miners.append(
                    ScreenedMiner(
                        comp=comp,
                        overlay=overlay,
                        ev_per_tonne_reserves=ev_to_tonne_of_reserves(comp, overlay),
                        ev_per_tonne_resources=ev_to_tonne_of_resources(comp, overlay),
                    )
                )
                continue
            except (SectorsAPIError, MapperError) as exc:
                # Mining join failed — still a screenable comp, just no overlay.
                pass

        result.screenable.append(comp)

    return result


def rank(
    screenable: list[CompanyComp],
    by: str = "ev_to_ebitda",
) -> list[CompanyComp]:
    """Return peers sorted by a multiple ascending (None values sort last)."""
    def key(c: CompanyComp):
        v = getattr(c, by, None)
        return (v is None, v)
    return sorted(screenable, key=key)
