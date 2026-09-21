# System Patterns

## Architecture
```
Sectors_Hackathon/
├── models/                     # package of Pydantic schemas
│   ├── __init__.py             # re-exports CompanyComp, Currency, MiningOverlay, CommodityStat
│   ├── company_comp.py         # CompanyComp model + Currency enum
│   └── mining_overlay.py       # MiningOverlay + CommodityStat (reserve-adjusted mining)
├── sectors_client/             # Sectors v2 API client
│   ├── __init__.py             # re-exports SectorsClient
│   └── client.py               # SectorsClient (auth, company-report + mining endpoints)
├── cache/                      # SQLite cache layer
│   ├── __init__.py             # re-exports SQLiteCache
│   └── sqlite_cache.py         # SQLiteCache (company+period+endpoint keyed)
├── mapper/                     # JSON -> domain models
│   ├── __init__.py             # re-exports report mapper + mining mapper
│   ├── mapper.py               # ReportMapper (bank vs generic template, cash derivation)
│   └── mining_overlay.py       # map_mining_overlay (perf/financials/sales-destination)
├── engine/                     # cross-model valuation functions
│   ├── __init__.py             # re-exports all engines
│   ├── mining_valuation.py     # EV/tonne-of-reserves & -resources join
│   ├── implied_valuation.py    # peer-median -> implied price + Sectors IV comparison
│   ├── football_field.py       # industry-matched valuation ranges (min-max bars)
│   ├── peer_lookup.py          # same-sub_sector peer resolution (Companies Screener)
│   ├── proxy_library.py        # sector-conditional growth proxies (bank/miner/generic)
│   ├── dcf.py                  # 2-stage DCF (FCFF build-up + FCFE bridge + WC days)
│   └── xlsx_export.py          # formula-driven DCF sheet for the workbook export
├── screener/                   # multi-peer batch orchestration
│   ├── __init__.py             # re-exports ScreenerResult, screen_tickers, ...
│   └── screener.py             # screen_tickers (screenable/miners/excluded partition)
├── view.py                     # presentation transforms (result -> table rows)
├── app.py                      # Streamlit "Simple + Advanced mode" UI entry point
├── assistant.py                # citation-safe DCF suggestion helper (curated refs only)
├── sectors_news.py             # Sectors-native news quoting (retrieval-then-quote)
├── README.md                   # cold-clone onboarding
├── requirements.txt            # declared deps (+ plotly)
├── scripts/
│   ├── prove_bbca_pull.py      # live BBCA client+cache proof (network-count assert)
│   ├── prove_mining_overlay.py # live MDKA+ADRO mining overlay proof
│   ├── prove_ev_tonne.py       # live EV/tonne engine proof (MDKA + ADRO)
│   ├── prove_screener.py       # live screener proof (5-ticker batch)
│   └── backtest_proxies.py     # proxy vs realised-growth sanity check
├── tests/
│   ├── test_company_comp.py    # script-style test runner (no pytest)
│   ├── test_mapper.py          # mapper tests over frozen fixtures (10 tickers)
│   ├── test_mining_overlay.py  # mining overlay tests (MDKA perf-only + ADRO full)
│   ├── test_ev_tonne.py        # EV/tonne engine unit tests (pure, in-memory)
│   ├── test_screener.py        # screener tests (fake client, deterministic)
│   ├── test_view.py            # presentation-transform tests (pure)
│   ├── test_advanced.py        # proxy library + DCF tests (pure)
│   ├── test_implied.py         # implied-valuation + FCFF/FCFE tests (pure)
│   ├── test_football.py        # football-field + WC-days tests (pure)
│   ├── test_assistant.py       # citation-safe assistant tests
│   └── fixtures/               # static JSON payloads (incl. mining/*.json)
├── data/                       # runtime artifacts (gitignored)
│   └── sectors_cache.db        # SQLite cache
├── .env                        # SECTORS_API_KEY (gitignored)
├── .env.example                # committed key template
└── memory-bank/                # this documentation
```

The project now has a data-ingestion spine (client → cache → mapper) feeding two sibling
domain models (`CompanyComp` for comps, `MiningOverlay` for reserve-adjusted mining).
There is still no screener, service, or UI layer. The expected flow is: **Sectors API →
SQLite cache → mappers (built) → screener / Streamlit UI (not yet built)**.

## Key design patterns (implemented)

### 1. Derived (computed) multiples, not stored fields
Valuation multiples are implemented with `@computed_field @property`. They are recomputed
from raw inputs on every access, so they can never diverge from their underlying figures.
A missing/zero input yields `None` rather than an exception.

### 2. Optional everywhere except stable identifiers
Only `ticker`, `company_name`, and `sector` are required (non-optional). Everything else
is `Optional`, reflecting that real data feeds have gaps. `ticker`/`company_name`/`sector`
enforce `min_length=1` and are validated as non-empty strings.

### 3. Decimal for monetary magnitudes
All monetary fields (`market_cap`, `price`, `shares_outstanding`, `total_debt`,
`cash_and_equivalents`, `total_assets`, `revenue`, `ebitda`, `ebit`, `net_income`, `eps`)
use `Decimal` to avoid floating-point precision error on large figures.

### 4. Cross-field backfill via `model_validator(mode="after")`
`_fill_market_cap` derives `market_cap = price * shares_outstanding` when `market_cap` is
omitted but both inputs are present.

### 5. Explicit screening exclusion instead of silent skipping
`is_screenable` (a `computed_field`, `True` iff `exclusion_reasons` is empty) plus
`exclusion_reasons` (a `computed_field` returning a human-readable list) let downstream
code report *why* a peer was excluded.

### 6. JSON float serialization for Decimals
A `@field_serializer(..., when_used="json")` converts the `Decimal` monetary fields (and
`enterprise_value`) to floats for JSON output. Deliberately avoids the deprecated
`json_encoders` config, slated for removal in Pydantic V3.

### 7. Enum for currency
`Currency(str, Enum)` holds USD/EUR/IDR/SGD/GBP/JPY. It inherits `str` so values
serialize as plain strings. No FX conversion logic exists yet. **Note**: broader than the
project's actual IDX/SGX scope — EUR/GBP/JPY are likely unnecessary, USD is likely still
needed (mining commodities price in USD). Worth trimming next time this file is touched.

### 7a. Sectors API client (header auth, no retry)
`SectorsClient` authenticates with a raw `Authorization: <key>` header (the API's
`ApiKeyAuth` scheme — NOT `Bearer`). It normalizes symbols (strip `.JK`, upper-case) and
raises `SectorsAPIError` on any non-2xx without retrying, because the API's credit
billing is status-dependent (2xx/404 cost credits, 400/401/403/429/5xx are free). The
key is read from `SECTORS_API_KEY` (via `python-dotenv` + `os.environ`).

### 7b. SQLite cache, keyed on company + period + endpoint
`SQLiteCache` stores JSON blobs in a single `cache_entries` table with a composite
primary key `(company, period, endpoint)` and an `ON CONFLICT ... DO UPDATE` upsert.
`period` is an application-defined string — for the company-report endpoint it is the
"as-of" ISO date (no period param exists); period-bearing endpoints (quarterly
financials) will use their natural period. WAL mode; DB at `data/sectors_cache.db`.

> **Naming note:** the pre-Memory-Bank draft (`schema.sql`, `BLUEPRINT.md`) called this
> column `entity_id` and used `response_json` for the payload, with a `credits_spent`
> column. What shipped is `company` + `payload`, no `credits_spent`. `company` is the term
> of record (see `BLUEPRINT.md` "Reconciliation with the Memory Bank"); it is a generic
> entity key that will also hold mining slugs once the overlay lands, not strictly an IDX
> ticker. Whether to add `credits_spent` back remains an open decision (see `activeContext.md`).

### 7c. Industry-conditional mapping (bank vs generic template)
The Sectors `company_report` endpoint emits **two structurally different financial
templates**, discovered empirically (not just null-variation within one schema):

- **`bank` (67 fields)** — triggered by `overview.sub_sector == "Banks"` (covers
  traditional banks like BBCA and digital banks like ARTO). `cash_and_equivalents` is
  *always* null; cash is **`total_cash_and_due_from_banks` alone** (NOT summed with
  `cash_only` — `cash_only` is a *sub-line* already inside the aggregate: verified against
  BBCA's audited FY2025 balance sheet, where Kas + Giro BI + Giro bank lain sum to the
  "Total" ≈ `total_cash_and_due_from_banks`). No `short_term_debt`/`long_term_debt` split
  (aggregate `total_debt` only), and bank-only figures (`net_interest_income`,
  `gross_loan`, `total_deposit`, RWA fields, etc.).
- **`generic` (39 fields)** — everything else: telecom (TLKM), industrials/holdings
  (ASII), consumer staples (UNVR), energy (PGAS), materials/mining (MDKA), insurance
  (ASRM), multifinance (ADMF), software/tech/fintech (GOTO). Direct 1:1 field names.

`mapper.mapper.classify_template()` keys on `sub_sector`, **not** `sector ==
"Financials"` — insurance and multifinance are Financials-sector but use the *generic*
template; Sectors classifies GOTO under `Technology` even though it's colloquially
"fintech". Only the `cash_and_equivalents` resolution differs by template; everything
else falls out of the generic field names (a superset of what `CompanyComp` consumes).

`report_to_company_comp()` returns `(comp, template)` so a caller/UI can surface which
template produced a row (minimal "defensible by design" provenance without bloating the
model). On a payload that can't produce a valid model (missing `ticker`/`company_name`/
`sector`) it raises `MapperError` with the ticker attached; malformed *individual* numeric
fields degrade to `None` via `_dec()` (which catches `decimal.InvalidOperation`).

Insurance (ASRM) is an edge case *within* the generic template: `cash_and_equivalents`
and `ebitda` are null, so it degrades to `screenable=False` via the existing
`exclusion_reasons` logic — no special-casing in the mapper. This mirrors the planned
SGX EV-gap handling (missing debt/cash → `None`, never silently substituted).

### 7d. Mining overlay as a sibling model (not a `CompanyComp` fork)
`MiningOverlay` (with a plural `CommodityStat` list) carries a miner's reserve/production
tonnage, USD financials, and sales-destination volume — the *tonnage* that `CompanyComp`'s
`enterprise_value` gets divided by to yield EV/tonne. It is a **sibling** model joined by
ticker/slug, not extra fields bolted onto `CompanyComp`, so a multi-commodity miner
(Copper + Gold) and a single-commodity miner (Coal) both map cleanly without distorting
the comps-screening axis. Optional datasets are flagged (`has_performance_data` /
`has_financials_data` / `has_sales_destination_data`) rather than 404ing — MDKA (a
holding) has performance-only coverage, ADRO has the full set. Defensibility flags are
first-class: `is_self_reported` (always True — reserve figures are company-disclosed,
not audited) and `reserve_vintage_year` (`measurement_year` — when the reserve was struck
against a commodity-price deck).

## Formulas implemented
- `enterprise_value = market_cap + total_debt - cash_and_equivalents` (`None` if
  `market_cap` is missing; missing debt/cash treated as 0)
- `ev_to_ebitda = enterprise_value / ebitda` (`None` if EV missing or EBITDA
  missing/zero)
- `ev_to_revenue = enterprise_value / revenue` (`None` if EV missing or revenue
  missing/zero) — **see the asymmetry flagged below**
- `pe_ratio = price / eps` (`None` if price missing or EPS missing/zero; computed from
  `price`, not market cap)
- `price_to_book = market_cap / total_equity` (`None` if market cap or equity
  missing/zero) — **true P/B**; `total_equity` is backfilled as
  `total_assets - total_liabilities` when not supplied directly.

## Exclusion reasons (implemented)
- `"missing market_cap"` — no market cap (and not backfillable)
- `"missing ebitda"` — EBITDA absent
- `"non-positive ebitda"` — EBITDA <= 0

**Open discrepancy, flagged during the Excel cross-check build**: `ev_to_revenue` returns
`None` for missing/zero revenue, but no `"missing revenue"` / `"non-positive revenue"`
reason exists in `exclusion_reasons`. Either the list is incomplete, or revenue-based
exclusion is deliberately not modeled — worth resolving explicitly rather than leaving
implicit. See `companycomp_crosscheck.xlsx` (Read Me tab) for how this was surfaced.

## Planned patterns (decided, not yet implemented)

### 8. Two-mode valuation split (Simple / Advanced)
The dividing principle is **whether the method requires forecasting the future**, not the
method's name:
- Simple: comps, reserve-adjusted comps (EV/tonne reserves, EV/tonne production, reserve
  life) — arithmetic on current disclosed data.
- Advanced: DCF, true per-asset NAV — both require forecasting, both grouped together for
  that reason.

Both modes share the same underlying calculation engine; Advanced exposes more editable
assumptions, it does not run different logic. Simple mode is the coverage-gap retail
persona's surface; Advanced mode is the M&A advisor / power-user surface.

### 9. Mining overlay data model
**Implemented** — see §7d. (Original plan: sourced from Sectors' mining extension; the
`is_self_reported` + `reserve_vintage_year` flags are now first-class fields on
`MiningOverlay`. Build the EV/tonne engine calc next — §see `progress.md`.)

### 10. Sector-conditional proxy library (for Advanced-mode DCF defaults)
Branches by sector rather than one formula for every company (bank → GDP + spread,
miner → revenue CAGR × commodity-price assumption, generic → historical average).
**Note on the miner branch:** the original plan specified "production growth × commodity
price," but our `MiningOverlay` stores only the *latest* production volume (no multi-year
series), so the implemented miner proxy uses historical *revenue* CAGR scaled by a
forward commodity-price assumption instead — see `engine/proxy_library.py` and
`progress.md`. **Back-test**: proxy vs realized growth ≈ 0.93–1.02x for the three seed
sectors (a sanity check, not a statistical validation).

### 11. AI-assistant citation-safety pattern
For Advanced-mode input-filling. Hard rule: every AI-supplied value must carry a stated,
verifiable reference.
- Sectors-native inputs (AR days, historical margins, anything already in the cache) are
  exempt — reading your own cached data carries no citation risk.
- External/general-knowledge lookups (e.g., "how long does a mining truck run before
  replacement") must draw from a small, pre-vetted, curated reference set, or quote
  retrieved text verbatim — never open-ended generation with an unverifiable citation
  attached. A well-formatted but fabricated citation is more dangerous than no citation,
  so "must cite a source" needs this technical backstop, not just a prompt-level rule.

### 12. Independent formula cross-check (validation practice, not code)
`companycomp_crosscheck.xlsx` re-implements the documented `CompanyComp` formulas in Excel
as ground truth, to catch divergence between the documented logic and the actual Python
output. Extend this workbook (or build a parallel one) once the screener, mining overlay,
and DCF logic exist, rather than trusting each new layer by inspection alone.

### 13. Bulk screener as the primary comps-core source (not per-ticker reports)
Comps core should be pulled from the bulk screener endpoints `GET /v2/companies/` (IDX)
and `GET /v2/sgx/companies/` (SGX) via a `where=symbol in [...]` query, returning
market_cap, revenue, ebitda, ebit, earnings, pe/pb/ps (and IDX-only precomputed
`enterprise_to_ebitda`/`enterprise_to_revenue`) for an entire matched comp set in **1
credit**, versus 1 credit per section per company via `get_company_report`. The report
endpoint becomes a fallback for fields the screener does not expose (ownership,
management, peers list, dividend history). A single screener response is decomposed at
cache-write time into one row per `(company, period, endpoint)`. Requires adding a
`SectorsClient.screen()` method (see `endpoint_registry.py`).

### 14. Per-endpoint cache TTL policy (not yet implemented)
Cache staleness is policy, not schema: a 2019 annual statement is immutable; today's
`market_cap` is not. `endpoint_registry.py` specifies `cache_ttl_days` per logical
endpoint (1 day for point-in-time fields, 30 days for annuals). The built
`SQLiteCache.get()` does not yet enforce this — it returns any cached row regardless of
`fetched_at`. This must be added (check `fetched_at` against the endpoint's TTL before
deciding cache-vs-API) before the screener starts pulling many companies.
