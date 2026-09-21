# Active Context

## Current work focus
Product definition, market positioning, and architecture are now settled through
extensive scoping discussion (outside this codebase — see below for what that means for
the code). The codebase now has six real components: the `CompanyComp` model (+ tests),
the **Sectors API client + SQLite cache** (live-verified against BBCA), the
**report → `CompanyComp` mapper** (bank vs generic template), the
**`MiningOverlay` model + mapper** (reserve-adjusted mining metrics), the **EV/tonne
engine** joining the two, the **screener** (batching ticks into a comps table), and the
**Streamlit user-facing app** (Simple mode), plus **Advanced mode** (sector-conditional
proxy library + DCF engine). The remaining work is the AI assistant, a README, and
optional true-NAV (narrated, not built).
`CompanyComp` itself is stable.

## Recent changes
- Initial commit: `5d193e6` — "Initial CompanyComp model with validation, screening
  flags, and test suite".
- Created the `memory-bank/` directory and its core files (initial version).
- **2026-09-21 valuation revision** (this session):
  - **Key discovery — Sectors already ships a `valuation` report section** the code
    never requested: `intrinsic_value`, `forward_pe`, and per-year peer-average
    multiples (`pe_peer_avg`/`pb_peer_avg`/`ps_peer_avg`). This is Sectors' own
    fair-value + comps benchmark, distinct from our locally-derived multiples. Now
    wired into the mapper + screener (`sections=["overview","financials","valuation"]`).
  - Added `engine/implied_valuation.py` (peer-median → implied price + Sectors IV →
    "target vs current" panel with an informational verdict), expanded the DCF to FCFF
    build-up + FCFE bridge, built `news_assistant.py` (Tavily retrieval-then-quote, off
    by default), `engine/xlsx_export.py` (formula-driven DCF sheet), and reworked
    `app.py` (upper-right Mimir branding + explainer, `st.session_state` fix so Advanced
    sliders recompute live). New `tests/test_implied.py`. Full detail in `progress.md`.
- **Product/market scoping session** (outside the codebase): name (Mimir, provisional),
  problem statement, audience, UI/output structure, mining overlay, two-mode
  (Simple/Advanced) valuation architecture, AI-assistant citation rule, and hackathon
  rules review all settled — see decisions below.
- Built `companycomp_crosscheck.xlsx`, an independent Excel re-implementation of the
  documented `CompanyComp` formulas, to cross-check against the Python model's actual
  output. Surfaced one real documentation gap (see Open Questions below).
- **Sectors API client + SQLite cache** (built, live-verified):
  - `sectors_client/client.py` — `SectorsClient` with header-based auth and
    `get_company_report(symbol, sections=...)`.
  - `cache/sqlite_cache.py` — `SQLiteCache` keyed on `(company, period, endpoint)`.
  - `scripts/prove_bbca_pull.py` — deterministic BBCA proof (miss → live pull → hit),
    mechanically verified via a request counter (exactly 1 network call across 2 requests).
  - New `.env` (gitignored) / `.env.example` (committed) convention; cache DB at
    `data/sectors_cache.db`.
- **report → `CompanyComp` mapper** (built, verified across 10 tickers):
  - `mapper/mapper.py` — `ReportMapper` with `classify_template()` splitting the Sectors
    payload into **bank** (`sub_sector == "Banks"`, cash = `total_cash_and_due_from_banks`
    alone) vs **generic** (direct 1:1 names).
  - `tests/test_mapper.py` — fixture-based proof (loads frozen JSON under
    `tests/fixtures/*.json`, so it is deterministic and judgeable without an API key,
    a network connection, or a same-day cache — deliberately NOT keyed on
    `date.today()`, which an earlier version did and broke on calendar rollover).
    10 tickers (BBCA/ARTO bank; TLKM/ASII/UNVR/PGAS/MDKA/ADMF/ASRM/GOTO generic) +
    edge cases (sparse overview, empty financials, malformed numeric field, missing
    identifiers) + a bank-cash double-count regression.
  - **Bank cash fix (audited cross-check)**: initially derived cash as
    `cash_only + total_cash_and_due_from_banks`, but this double-counted — `cash_only`
    ("Kas") is a sub-line already *inside* `total_cash_and_due_from_banks`, per BBCA's
    audited FY2025 balance sheet (Kas 25.3T + Giro BI 47.8T + Giro bank lain 5.3T =
    ~78.4T total). Corrected to `total_cash_and_due_from_banks` alone; BBCA EV corrected
    from 673.7T → 699.0T.
  - **Provenance + error handling**: `report_to_company_comp()` returns `(comp, template)`;
    raises `MapperError` (with ticker) on un-mappable payloads; malformed single fields
    degrade to `None`.
- **`MiningOverlay` model + mapper** (built):
  - `models/mining_overlay.py` — `MiningOverlay` (plural `CommodityStat` list) holding
    production/reserve tonnage, USD financials, and sales-destination volume; sibling to
    `CompanyComp` (joined by ticker/slug), per `architectureOverview.md`.
  - `mapper/mining_overlay.py` — `map_mining_overlay()`; flags `has_performance_data` /
    `has_financials_data` / `has_sales_destination_data` for optional datasets.
  - `sectors_client` gained `get_mining_companies/performance/financials/sales_destination`.
  - **Live finding (changes seed plan):** MDKA's mining financials and sales-destination
    endpoints both 404 (it's a `Holding` with performance-only coverage). ADRO (Alamtri,
    a coal miner) has the *full* set — so the full metric set is proven on ADRO, while
    MDKA covers the reserve/production metrics. The `resources_reserves.total_reserves_Mt`
    figure is **company-level**, repeated identically across every commodity entry.
  - `scripts/prove_mining_overlay.py` + `tests/test_mining_overlay.py` (frozen fixtures).
- **True P/B fix** (built, **user-reviewed & approved**):
  - `CompanyComp` gained `total_liabilities` / `total_equity`; `total_equity` backfilled
    as `assets - liabilities`; `price_to_book` now computes `market_cap / total_equity`
    (textbook) instead of the old `market_cap / total_assets` approximation.
  - Verified against BBCA's audited FY2025 balance sheet: P/B corrected from a wrong 0.49x
    (assets-denominated) to a true 2.75x (equity-denominated). Approved by the user.
- **EV/tonne engine** (built, then **unit-conversion bug fixed in review**):
  - `engine/mining_valuation.py` — `ev_to_tonne_of_reserves()` / `ev_to_tonne_of_resources()`
    joining `CompanyComp.enterprise_value` with `MiningOverlay` tonnage; returns `EVPerTonne`
    (value + reason on failure), never silently substitutes. Converts Mt → tonnes before
    dividing (the original review pass caught a 1,000,000x off-by-megatonne bug).
  - `scripts/prove_ev_tonne.py` + `tests/test_ev_tonne.py` (incl. a real-world magnitude
    sanity test). Live (corrected): MDKA ≈ 229.8k IDR/t, ADRO ≈ 72.6k IDR/t of reserves.
    Tonnage is Mt of *ore*, not metal content.
- **Screener** (built, then **SGX + cache fixed in review**):
  - `screener/screener.py` — `screen_tickers()` batches tickers → `screenable` / `miners`
    (with EV/tonne) / `excluded` (with reasons). One bad ticker never aborts the batch.
    Accepts an optional cache (reuses reports across runs). SGX tickers are excluded
    honestly ("not yet supported"), not silently mis-routed through the IDX mapper.
  - `scripts/prove_screener.py` + `tests/test_screener.py` (fake-client, deterministic;
    includes cache-reuse and SGX-honesty tests). Live: BBCA/TLKM/ASII/UNVR/MDKA →
    4 screenable + 1 miner, 0 excluded.
- **Streamlit app (Simple mode)** (built):
  - `app.py` — ticker input → screener → comps table + mining overlay panel + excluded
    panel, source-dated, with xlsx export and a not-financial-advice disclaimer.
  - `view.py` — presentation transforms (`ScreenerResult` → table rows) kept separate so
    they're unit-testable (`tests/test_view.py`).
  - `requirements.txt` added (pydantic, requests, python-dotenv, pandas, streamlit,
    openpyxl). App boots clean (verified `streamlit run` + health check).
- **AI assistant + README** (built, then review-completed):
  - `assistant.py` — citation-safe suggestion helper. Only two allowed value sources:
    Sectors-native cached data (cited/exempt) or a hand-curated reference set (each
    value cited). Now covers **capex** (as % revenue), working capital, and asset
    useful life — the full set promised in the brief. Unknown values → "no cited value
    available", never fabricated. Industry classifier is mining-specific (not the
    broad "Materials" bucket). Wired into the app's Advanced-mode panel (work-capital,
    capex, useful-life, shown with sources).
  - `README.md` — cold-clone onboarding: setup, run, architecture table, test commands,
    design principles, and expanded Scope notes (SGX, mining-ticker hardcoding, DCF
    growth-default-for-banks-only, NAV not built).
  - `tests/test_assistant.py` — 6 tests (incl. capex + "Materials-not-mining" guard).
- **Advanced mode** (built): `engine/proxy_library.py` (sector-conditional growth
  proxies: bank = GDP+spread, generic = historical CAGR, miner = CAGR × commodity-price)
  + `engine/dcf.py` (2-stage DCF, "expected rate of return" in place of WACC).
  `scripts/backtest_proxies.py` sanity-checks proxies vs realized growth (BBCA 0.93x,
  MDKA 1.02x, TLKM 1.00x — all near 1.0). DCF wired into `app.py` under an "Advanced
  mode" checkbox. **Known limitation (honest, not hidden):** the generic/miner proxies
  need historical revenue, which the screener discards after mapping; the app seeds
  banks from the live proxy and asks for manual growth elsewhere. True per-asset NAV is
  deliberately NOT built (narrated roadmap item per time constraints).

## Settled decisions (previously open, now resolved)
- **Data source**: Sectors v2 API (REST + MCP available). Core and load-bearing — the
  product must lose its core functionality if Sectors data is removed (hackathon rule).
- **Deliverable shape**: Streamlit web app, single-user, local. No live deployment
  required.
- **Market/sector scope**: IDX and SGX. The `Currency` enum's EUR/GBP/JPY are broader
  than needed; USD is likely still needed for commodity-priced mining inputs.
- **Two audiences, mode-mapped**: Simple mode → coverage-gap self-directed investor
  (analyst coverage stops at LQ45; this replaces an earlier, now-dropped "low-literacy"
  framing — the audience is defined by the coverage gap, not by financial
  sophistication). Advanced mode → M&A advisors and other power users who want full
  assumption control.
- **Precedent transactions**: dropped from scope entirely (control-premium concept,
  doesn't apply to secondary-market share purchases).
- **Low-literacy / sentiment-driven / "gambler" segment**: dropped from scope entirely —
  a different (educational) problem this product doesn't attempt to solve.

## Next steps
1. (Optional/deferred): true per-asset NAV for miners — narrated only, not built.
2. (Optional): currency normalization / FX conversion — only matters for cross-market
   SGX comps, which is post-SGX-mapper.
3. (Optional): adopt pytest over the current script-runner.

The core deliverable — Simple mode (comps + mining overlay + screener + Streamlit app)
plus Advanced mode (DCF + proxy library + citation-safe assistant) — is complete.

## Open questions for the user
- **Trademark/namespace check on "Mimir"** — never resolved; still a placeholder name.
- **Cache `period` semantics — resolved (proposed by `BLUEPRINT.md` /
  `architectureOverview.md`, not yet implemented):** `period` should be the natural period
  of the underlying data, not one fixed convention: fiscal year (`"2024"`) for annual
  financials, `"Q1-2024"` for IDX quarterlies (SGX has no quarterly data), and today's
  ISO date only for point-in-time fields (market_cap, last_close_price, the `overview`/
  `valuation` sections). Note the current `company_report` call bundles point-in-time and
  annual data under a single `period` key, which is incorrect for the annual portion and
  must be split before the screener scales up.
- **SGX EV data gap — RESOLVED (decision): SGX multiples-only.** SGX endpoints
  (v2 `/v2/sgx/company/report/{symbol}/`) expose `total_liabilities`/`total_equity` and a
  `debt_to_equity` ratio, but **no** `total_debt`/`cash_and_equivalents`/`net_debt` anywhere
  in the schema (verified against the v2 docs + DBS example). So EV-based multiples are
  not computable for SGX names from this API. Decision: **SGX peers are restricted to
  price-based multiples only** (PE/PB/PS/PCF); no EV/EBITDA or EV/Revenue for SGX.
  **Current state:** no SGX mapper exists yet, so the screener excludes SGX tickers with
  an honest "not yet supported" reason rather than mis-routing them through the IDX mapper.
  `SectorsClient.get_sgx_company_report()` exists as the future entry point. No second
  source for debt/cash will be added (out of scope, hackathon).
- **Reserve price-deck vintage flag — RESOLVED (implemented).** The mining performance
  endpoint exposes `resources_reserves.measurement_year` — the year the reserve statement
  was struck against its commodity-price assumptions. Surfaced as
  `MiningOverlay.reserve_vintage_year`. Combined with `is_self_reported` (always True:
  reserve figures are company self-reported, not independently audited), this is the full
  defensibility flag pair the product brief required. (A mismatch-detection UX across two
  reserve statements is still unbuilt — see Next steps / Advanced mode.)
- **Proxy library back-testing methodology** — RESOLVED (implemented): a lightweight
  sanity check (`scripts/backtest_proxies.py`) compares each proxy vs realized growth
  (≈0.93–1.02x), documented as a ballpark check, not a statistical validation.
- **`ev_to_revenue` / `exclusion_reasons` asymmetry** — RESOLVED (fixed): `missing
  revenue` / `non-positive revenue` are now first-class `exclusion_reasons`, mirroring
  the existing EBITDA/market-cap pattern (see `models/company_comp.py`).
- **pytest vs script-runner** — DEFERRED (not blocking): stays script-based for now.
- **LLM SDK choice for the AI assistant** — RESOLVED by design: the assistant is a
  citation-safe curated-reference helper, not a live LLM, so no SDK is needed.

## Important patterns and preferences
- Keep monetary fields as `Decimal`; emit floats only at the JSON serialization
  boundary.
- Prefer derived/computed multiples over stored values.
- Keep exclusions explicit and human-readable (`exclusion_reasons`).
- Accept `Optional` inputs everywhere except stable identifiers.
- **Defensibility is non-negotiable**: every number the product surfaces — comps, mining
  overlay, AI-assisted — must trace to a source. This is the product's core
  differentiator, not a hackathon checkbox.
- **"Coverage-gap," not "literacy-gap"**: when describing the Simple-mode audience, use
  the coverage framing (underserved by analyst coverage) — the literacy framing was
  explicitly dropped.
- Simple and Advanced modes share one calculation engine; Advanced exposes more editable
  assumptions, it does not run different logic.
