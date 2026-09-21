"""Map mining-extension JSON into a :class:`MiningOverlay`.

The mining extension has four endpoints (``performance``, ``financials``,
``sales-destination``, ``companies`` list). A given miner may 404 on any of the
optional ones — the mapper never raises for a missing *optional* dataset; it sets
the corresponding ``has_*_data`` flag False and leaves fields ``None``.

Ticker resolution: the ``performance`` payload carries ``symbol`` per commodity
(sometimes), but the canonical ticker/slug is passed in by the caller (who looked
it up via ``get_mining_companies``). Financials carries ``slug``/``symbol``/``name``
— the authoritative identity when present.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from models.mining_overlay import CommodityStat, MiningOverlay


def _dec(value) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def map_mining_overlay(
    *,
    ticker: str,
    slug: Optional[str] = None,
    company_name: Optional[str] = None,
    performance: Optional[dict] = None,
    financials: Optional[dict] = None,
    sales_destination: Optional[dict] = None,
) -> MiningOverlay:
    """Assemble a ``MiningOverlay`` from up to three mining-extension payloads.

    Only ``performance`` is strictly required to produce reserve/production data;
    the other two are optional (many miners 404 on them). Identity is taken from
    ``financials`` when present, else from the explicit ``ticker``/``slug`` args.
    """
    # Identity: financials carries authoritative slug/symbol/name when present.
    fin_data = (financials or {}).get("data") or {}
    if fin_data:
        ticker = fin_data.get("symbol") or ticker
        slug = fin_data.get("slug") or slug
        company_name = fin_data.get("name") or company_name

    commodities: list[CommodityStat] = []
    has_perf = bool(performance and performance.get("data"))
    if performance:
        for item in performance.get("data") or []:
            cs = item.get("commodity_stats") or {}
            rr = cs.get("resources_reserves") or {}
            commodities.append(
                CommodityStat(
                    commodity_type=item.get("commodity_type") or "Unknown",
                    unit=cs.get("unit"),
                    mining_operation_status=cs.get("mining_operation_status"),
                    production_volume=_dec(cs.get("production_volume")),
                    sales_volume=_dec(cs.get("sales_volume")),
                    total_reserves_Mt=_dec(rr.get("total_reserves_Mt")),
                    total_resources_Mt=_dec(rr.get("total_resources_Mt")),
                    measurement_year=rr.get("measurement_year"),
                )
            )

    volume_map: dict[str, Optional[Decimal]] = {}
    has_sale = bool(sales_destination and sales_destination.get("data"))
    if sales_destination:
        for country, rec in (sales_destination.get("data") or {}).items():
            volume_map[country] = _dec(rec.get("volume"))

    return MiningOverlay(
        ticker=ticker or "UNKNOWN",
        slug=slug,
        company_name=company_name,
        commodities=commodities,
        has_performance_data=has_perf,
        revenue_usd=_dec((fin_data or {}).get("revenue_usd")),
        net_profit_usd=_dec((fin_data or {}).get("net_profit_usd")),
        assets_usd=_dec((fin_data or {}).get("assets_usd")),
        has_financials_data=bool(fin_data),
        sales_destination_volume=volume_map,
        has_sales_destination_data=has_sale,
    )
