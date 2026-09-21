"""
Sectors v2 endpoint registry -- Sectors Hackathon 2026 comps tool.

NOTE (added after the Memory Bank was created): this file predates the six core
Memory Bank files and the built `sectors_client/` + `cache/`. It is a design artifact,
not a second source of truth. Where it diverges from what shipped, defer to
`systemPatterns.md` (section 7b) and `BLUEPRINT.md` "Reconciliation with the Memory Bank".
In particular: the shipped cache uses `(company, period, endpoint, payload)` with no
`credits_spent` column, and the `cache_ttl_days` / bulk-screener items below are
planned, not yet implemented.

Logical endpoint keys, not raw URLs, are what gets stored in api_cache.endpoint.
This indirection means a path change on Sectors' side is a one-line fix here,
not a cache migration.

See BLUEPRINT.md sections 2 and 4 for the reasoning behind each entry, in
particular:
  - why comps core is sourced from the bulk screener, not per-ticker reports
  - the SGX EV gap (no total_debt / cash_and_equivalents exposed)
  - SGX coverage tiering (big-caps-only and banks-only fields)

Base URL: https://api.sectors.app
Auth header: Authorization: <raw_key>  (NOT "Bearer <key>")
"""

ENDPOINT_REGISTRY = {

    # ---------------------------------------------------------------
    # Comps core
    # ---------------------------------------------------------------
    "idx_screener": {
        "path": "/v2/companies/",
        "domain": "IDX",
        "period_type": "annual + quarterly (bracket notation per field, e.g. revenue[2024], revenue_q[Q1-2024])",
        "credit_cost_structured": 1,   # covers the ENTIRE matched set, not per company
        "credit_cost_natural_language": 3,
        "cache_ttl_days": 1,           # point-in-time fields (market_cap, pe_ttm) dominate; keep this short
        "key_fields": [
            "market_cap", "total_debt", "cash_and_equivalents",
            "revenue", "ebitda", "ebit", "earnings",
            "enterprise_to_ebitda", "enterprise_to_revenue",   # precomputed by Sectors -- reconcile against manual EV calc
            "pe", "pb", "ps", "total_equity", "outstanding_shares",
        ],
        "bank_only_fields": [
            "net_interest_income", "gross_loan", "total_deposit",
            "capital_adequacy_ratio", "casa_ratio", "loan_to_deposit_ratio",
            "net_interest_margin", "core_capital_tier1",
        ],
        "notes": (
            "Primary comps-core source. `where=symbol in [...]` should cover the whole "
            "seed universe in one call -- VERIFY this works for a direct field, not just "
            "array fields (open question in BLUEPRINT.md). Decompose the results array "
            "into one api_cache row per ticker before writing."
        ),
    },

    "sgx_screener": {
        "path": "/v2/sgx/companies/",
        "domain": "SGX",
        "period_type": "annual only -- confirmed by docs, no quarterly data exists for SGX",
        "credit_cost_structured": 1,
        "credit_cost_natural_language": 3,
        "cache_ttl_days": 1,
        "key_fields": [
            "market_cap", "pe", "pb", "ps", "pcf",
            "ebit", "ebitda", "revenue", "earnings",
            "debt_to_equity", "total_liabilities", "total_equity",
        ],
        "coverage_caveats": {
            "big_caps_only": [
                "ebit", "ebitda", "operating_cash_flow", "investing_cash_flow",
                "financing_cash_flow", "free_cash_flow", "capital_expenditure",
                "total_asset", "total_equity", "total_liabilities", "working_capital",
            ],
            "banks_only_dbs_ocbc_uob": [
                "net_interest_income", "interest_income", "interest_expense",
                "net_fee_and_commission_income", "net_loan", "gross_loan",
                "total_deposit", "core_capital_tier1", "total_risk_weighted_asset",
            ],
        },
        "notes": (
            "NO total_debt or cash_and_equivalents field exists on this endpoint -- "
            "EV cannot be reconstructed the way it can for IDX. No precomputed "
            "enterprise_to_ebitda/enterprise_to_revenue either. Treat SGX rows as "
            "price-multiple-only (PE/PB/PS/PCF) until a decision is made "
            "(BLUEPRINT.md decision 4)."
        ),
    },

    "idx_report_section": {
        "path": "/v2/company/report/{symbol}/",
        "domain": "IDX",
        "period_type": "point-in-time (overview, valuation) or annual history (financials, dividend)",
        "credit_cost_per_section": 1,
        "sections": ["overview", "valuation", "future", "peers", "financials", "dividend", "management", "ownership"],
        "cache_ttl_days": {
            "overview": 1, "valuation": 1, "future": 7, "peers": 7,
            "financials": 30, "dividend": 30, "management": 30, "ownership": 30,
        },
        "notes": (
            "Fallback for fields the screener doesn't expose: ownership, management, "
            "peers list, dividend history. Cache per SECTION, not per full response -- "
            "sections are billed and refreshed independently, so request only what's missing."
        ),
    },

    "sgx_report_section": {
        "path": "/v2/sgx/company/report/{symbol}/",
        "domain": "SGX",
        "period_type": "point-in-time (overview, valuation) or annual history (financials, dividend)",
        "credit_cost_per_section": 1,
        "sections": ["overview", "valuation", "financials", "dividend"],
        "cache_ttl_days": {"overview": 1, "valuation": 1, "financials": 30, "dividend": 30},
        "notes": "Only 4 sections exist for SGX -- no peers/management/ownership/future.",
    },

    # ---------------------------------------------------------------
    # Mining overlay
    # ---------------------------------------------------------------
    "mining_companies_list": {
        "path": "/v2/mining/companies/",
        "domain": "MINING",
        "period_type": "n/a -- directory listing, paginated (max 30/page)",
        "credit_cost": 1,
        "cache_ttl_days": 30,
        "notes": (
            "One-time (or periodic) build of the ticker<->slug map for companies.mining_slug. "
            "`symbol` is null for unlisted operators -- filter those out before joining. "
            "`has_financials=true` filter recommended to skip shell/holding entities."
        ),
    },

    "mining_financials": {
        "path": "/v2/mining/companies/financials/{slug}/",
        "domain": "MINING",
        "period_type": "annual",
        "credit_cost": 1,
        "cache_ttl_days": 30,
        "key_fields": ["assets_usd", "revenue_usd", "revenue_breakdown", "cost_of_revenue_usd", "net_profit_usd"],
        "notes": "USD millions -- separate currency/scale from the IDX screener's IDR figures. Keyed by slug, not ticker. Returns `{year, available_years, data:{slug, symbol, name, year, ...}}`. 404s with 'Company not found or no financial data available' for holdings/miners without data (e.g. MDKA).",
    },

    "mining_performance": {
        "path": "/v2/mining/companies/performance/{slug}/",
        "domain": "MINING",
        "period_type": "annual",
        "credit_cost": 1,
        "cache_ttl_days": 30,
        "key_fields": [
            "production_volume", "sales_volume", "strip_ratio",
            "resources_reserves.total_reserves_Mt", "resources_reserves.total_resources_Mt",
        ],
        "notes": (
            "Direct source for EV/tonne of reserves and EV/tonne of production. "
            "`data` is an array with one entry per commodity_type the company reports -- "
            "a multi-commodity miner needs a metric per commodity, or an explicit "
            "aggregation rule if the mining overlay wants one number per company. "
            "NOTE: `resources_reserves.total_reserves_Mt` is COMPANY-level and repeated "
            "identically across every commodity entry (verified: MDKA Copper and Gold both "
            "show 430.8 Mt); it is NOT per-commodity. `measurement_year` is the reserve "
            "price-deck vintage."
        ),
    },

    "mining_sales_destination": {
        "path": "/v2/mining/sales-destination/{slug}/",
        "domain": "MINING",
        "period_type": "annual",
        "credit_cost": 1,
        "cache_ttl_days": 30,
        "key_fields": ["percentage_of_sales_volume", "percentage_of_total_revenue", "revenue_usd"],
        "notes": (
            "Company-level destination breakdown by country -- source for export-destination "
            "concentration (e.g. an HHI over percentage_of_sales_volume). This is distinct "
            "from the national-aggregate 'Top Export Destinations' endpoint, which is the "
            "wrong granularity for a per-company overlay metric."
        ),
    },
}
