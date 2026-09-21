# Progress

## What works
- `CompanyComp` Pydantic model fully implemented (`models/company_comp.py`):
  - Identifiers, market data, balance-sheet, income-statement, growth, margin, and
    metadata fields.
  - `model_validator` backfills `market_cap` from `price * shares_outstanding`.
  - Derived `computed_field` multiples: `enterprise_value`, `ev_to_ebitda`,
    `ev_to_revenue`, `pe_ratio`, `price_to_book`.
  - `is_screenable` flag and `exclusion_reasons` list for auditability.
  - `field_serializer` emits monetary fields as floats in JSON mode.
- `Currency` enum (USD, EUR, IDR, SGD, GBP, JPY) — broader than the project's actual
  IDX/SGX scope; flagged for trimming, not yet acted on.
- `models/__init__.py` re-exports `CompanyComp`, `Currency`.
- Full test suite passing (verified by running `python -m tests.test_company_comp`):
  all 9 scenarios PASS — full-data, missing-market-cap, backfill, missing-ebitda,
  zero-ebitda, screening partition, JSON serialization, negative-value rejection,
  empty-string-identifier rejection.
- `companycomp_crosscheck.xlsx` — an independent Excel re-implementation of the
  documented `CompanyComp` formulas (5 scenarios × 8 metrics, with a
  Python-output-paste column and a Match? flag), used to validate the Python model's
  logic against a second, hand-built calculation. Surfaced the `ev_to_revenue` /
  `exclusion_reasons` asymmetry noted in `activeContext.md`.
- **Sectors API client** (`sectors_client/client.py`) — `SectorsClient` with
  header-based auth (`Authorization: <key>`, no Bearer), symbol normalization
  (`.JK` stripped / uppercased), and `get_company_report(symbol, sections=...)`.
  Raises `SectorsAPIError` on non-2xx with the API's own error payload; no retry-loop
  (400/401/403/429/5xx are free per the credit-billing rules).
- **SQLite cache** (`cache/sqlite_cache.py`) — `SQLiteCache` keyed on
  `(company, period, endpoint)` with a composite primary key and `ON CONFLICT` upsert;
  `get` / `set` / `clear`. DB at `data/sectors_cache.db` (gitignored), WAL mode.
- **Live proof against BBCA** (`scripts/prove_bbca_pull.py`) — verified end-to-end with
  a real API key: call 1 = cache miss → one live pull (market cap 771.9T IDR, last close
  6325, EPS ttm 471.45, latest FY 2025) → cached; call 2 = cache hit served from SQLite.
  The "only one network call" claim is mechanically asserted via a request-count wrapper,
  not trusted by inspection. Cross-process persistence also confirmed (a warm-cache run
  performs zero network calls).
- **report → `CompanyComp` mapper** (`mapper/mapper.py`, `tests/test_mapper.py`,
  `tests/fixtures/*.json`) — maps a cached report payload into a `CompanyComp`,
  splitting on the Sectors API's two financial templates: **bank** (`sub_sector == "Banks"`,
  cash = `total_cash_and_due_from_banks` alone) vs **generic** (direct 1:1). Verified
  against 10 frozen fixture payloads + edge cases (deterministic, no network/date
  dependency). Bank cash was corrected after an audited-BBCA cross-check (drop the
  `cash_only` double-count); BBCA EV now 699.0T. Returns `(comp, template)` for
  provenance; raises `MapperError` on un-mappable payloads; malformed single fields
  degrade to `None`.
- **`MiningOverlay` model + mapper** (`models/mining_overlay.py`,
  `mapper/mining_overlay.py`, `tests/test_mining_overlay.py`,
  `tests/fixtures/mining/*.json`, `scripts/prove_mining_overlay.py`) — reserve-adjusted
  mining metrics. Holds per-commodity production/reserve tonnage, USD financials, and
  sales-destination volume; exposes `total_reserves_Mt`/`total_resources_Mt`/
  `reserve_vintage_year`/`is_self_reported` (defensibility flags). Live-verified: ADRO
  (full: perf + financials + sales-dest), MDKA (performance-only — its financials and
  sales-destination endpoints 404; it's a holding). EV/tonne ratios are computed at the
  engine layer (EV lives on `CompanyComp`, tonnage on `MiningOverlay`).
- **EV/tonne engine** (`engine/mining_valuation.py`, `tests/test_ev_tonne.py`,
  `scripts/prove_ev_tonne.py`) — pure functions joining `CompanyComp.enterprise_value`
  with `MiningOverlay` tonnage to produce EV/tonne-of-reserves and EV/tonne-of-resources.
  Returns an `EVPerTonne` (value + reason on failure), never silently substituting.
  **Unit-conversion fix:** `total_reserves_Mt` is in megatonnes; the engine converts to
  tonnes before dividing. Live-verified (corrected): MDKA ≈ 229.8k IDR/t (~$14.6/t),
  ADRO ≈ 72.6k IDR/t (~$4.6/t) of reserves. A real-world magnitude sanity test guards
  against the original 1,000,000x off-by-megatonne bug. Tonnage is Mt of *ore*, not
  metal content — surfaced, not hidden.
- **Screener / ranking layer** (`screener/screener.py`, `tests/test_screener.py`,
  `scripts/prove_screener.py`) — `screen_tickers()` batches a list of tickers through
  pull → map → mine-join → partition. Returns `screenable` (comps), `miners` (with
  EV/tonne overlay), and `excluded` (with reasons). One bad ticker never aborts the
  batch; data-quality exclusions reuse `CompanyComp.exclusion_reasons`. **Cache wiring:**
  accepts an optional `SQLiteCache` and reuses cached reports across runs (2nd run = 0
  API calls, per test). **SGX:** excluded with an honest "not yet supported" reason —
  no SGX mapper exists yet, so SGX tickers are NOT silently routed through the IDX
  mapper (that would produce misleading results). Live-verified on BBCA/TLKM/ASII/
  UNVR/MDKA (4 screenable + 1 miner, 0 excluded).
- **True P/B** (`models/company_comp.py`) — `CompanyComp` now has `total_liabilities`
  and `total_equity` fields; `total_equity` is backfilled as `assets - liabilities` and
  `price_to_book` now computes `market_cap / total_equity` (textbook) instead of the old
  `market_cap / total_assets` approximation. Verified against BBCA's audited FY2025
  balance sheet: P/B corrected from a wrong 0.49x (assets-denominated) to a true 2.75x
  (equity-denominated) — materially meaningful for a deposit-funded bank.

- **Streamlit app (Simple mode)** (`app.py`, `view.py`, `tests/test_view.py`,
  `requirements.txt`) — the clickable deliverable: ticker input → comps table + mining
  overlay + excluded panel, xlsx export, not-financial-advice disclaimer. The data→table
  transforms in `view.py` are unit-tested; the app itself boots clean (verified
  `streamlit run` + health check). `requirements.txt` now declares deps (pandas,
  streamlit, openpyxl added).

- **Advanced mode** (`engine/proxy_library.py`, `engine/dcf.py`,
  `tests/test_advanced.py`, `scripts/backtest_proxies.py`) — sector-conditional growth
  proxies (bank=GDP+spread, generic=CAGR, miner=CAGR×commodity-price) + a 2-stage DCF
  ("expected rate of return" in place of WACC), wired into `app.py`. Back-test: proxies
  vs realized growth = BBCA 0.93x / MDKA 1.02x / TLKM 1.00x (all near 1.0). Honest
  limitation: generic/miner proxies need historical revenue the screener doesn't retain;
  true NAV narrated, not built.

- **AI assistant** (`assistant.py`, `tests/test_assistant.py`) — citation-safe DCF
  suggestions covering **capex** (as % revenue), working capital, and asset useful life.
  Only two allowed value sources: Sectors-native cached data (exempt) or a hand-curated
  reference set (each value cited). Unknown → "no cited value", never fabricated.
  Industry matching is mining-specific (not the broad "Materials" bucket). Wired into
  `app.py` Advanced mode; README Scope notes cover mining-ticker hardcoding + bank-only
  growth default.

## What's left to build
- (Optional) true per-asset NAV for miners — narrated, not built.
- (Optional) pytest over script-runner; cross-market FX (post-SGX-mapper).
- **Cache TTL / staleness policy** — `SQLiteCache.get()` currently treats any cached
  payload as valid forever (until `clear()` is called manually), but the drafted design
  (`endpoint_registry.py` `cache_ttl_days`, `BLUEPRINT.md` section 3) calls for
  per-endpoint TTLs: 1 day for point-in-time fields (market_cap, pe_ttm), 30 days for
  annual financials. Not yet implemented.
- **Bulk screener endpoint** — add `SectorsClient.screen()` hitting `/v2/companies/`
  (IDX) and `/v2/sgx/companies/` (SGX): market cap, revenue, ebitda, ebit, earnings,
  pe/pb/ps (and IDX-only precomputed EV multiples) for a whole matched comp set in 1
  credit, vs 1 credit/section/company via `get_company_report`. Build before the
  screener layer.
- **SGX EV data gap** — SGX endpoints expose `total_liabilities`/`total_equity` but no
  `total_debt`/`cash_and_equivalents`, so `CompanyComp.enterprise_value` would treat
  missing debt/cash as zero and silently understate SGX-names' EV. Needs a code
  decision (exclude SGX names from EV multiples, or source debt/cash elsewhere).
- **`companies` seed-universe table** (from `schema.sql`) — a persistent ticker registry
  with `is_bank`/`is_mining`/`mining_slug`, distinct from the JSON-blob cache. Planned
  but not built.

## Current status
- **Codebase: complete.** Six real components plus Advanced mode and the AI assistant:
  `CompanyComp` model (+ tests), Sectors API client + SQLite cache (live-verified),
  report → `CompanyComp` mapper (bank vs generic), `MiningOverlay` model + mapper,
  the EV/tonne engine, the screener, the Streamlit app (Simple + Advanced), the
  sector-conditional proxy library + DCF, and the citation-safe assistant + README.
  All 8 test suites green. Everything else below is a documented, deliberate deferral.
- **2026-09-21 UI/valuation revision (this session):**
  - **Sectors `valuation` section now wired in** (was never requested before): the
    mapper reads `intrinsic_value`, `forward_pe`, and the latest-year peer-average
    multiples (`pe_peer_avg`/`pb_peer_avg`/`ps_peer_avg`) from the report's
    `valuation` block. `CompanyComp` gained `intrinsic_value` / `forward_pe` /
    `pe_peer_avg` / `pb_peer_avg` / `ps_peer_avg` plus a computed `intrinsic_upside`.
    `screen_tickers` now requests `sections=["overview","financials","valuation"]`.
  - **New `engine/implied_valuation.py`** — inverts peer-median multiples (excluding
    the subject) into implied share prices (EV/EBITDA + EV/Revenue via EV→equity→price;
    P/E + P/B direct), combined with Sectors' own `intrinsic_value`, to produce a
    "target vs current price" panel with an informational Undervalued/Fair/Overvalued
    verdict (never a recommendation). Requires ≥2 peers (a single peer isn't a group).
  - **DCF expanded** (`engine/dcf.py`) — added an optional FCFF build-up (EBITDA
    margin, D&A %, tax rate, capex %, ΔNWC %) plus an FCFE bridge (`shares_outstanding`
    + `net_debt`) yielding `intrinsic_equity` and `intrinsic_price_per_share`, so the
    DCF now also produces a price (not just an EV). Backward-compatible: sales-margin
    fallback unchanged. `assistant.suggest_working_capital`/`suggest_capex` are now
    wired into the DCF form (previously computed but never used).
  - **`news_assistant.py`** — optional Tavily-powered retrieval-then-quote layer (off
    by default; `TAVILY_API_KEY`). Only surfaces verbatim-quoted snippets + source
    URL, never interprets; no result → "no cited source found". Calls Tavily REST
    directly via `requests` (no SDK dep).
  - **`engine/xlsx_export.py`** — formula-driven DCF sheet in the downloadable workbook
    (live Excel `=` formulas over editable assumption cells), plus an "Implied" sheet.
  - **`app.py`** — Mimir branding repositioned to the upper-right + "what is Mimir"
    explainer; screen result persisted in `st.session_state` so Advanced-mode sliders
    recompute live (the old `if run:` block only rendered on the button rerun, so
    edits never re-rendered); live-updating DCF inputs + news toggle.
  - New test suite `tests/test_implied.py` (implied-valuation + FCFF/FCFE) — green.
- Product definition: settled — name (provisional), problem statement, dual audience
  (coverage-gap retail via Simple mode, M&A advisors via Advanced mode), UI/output
  structure, mining overlay, two-mode valuation architecture, AI-assistant citation
  rule, and hackathon rules are all worked through. See `activeContext.md` for the full
  decision log.
- A validation practice exists (`companycomp_crosscheck.xlsx`) independent of the
  Python test suite, for cross-checking model logic as new layers get built.

## Known issues
- No cross-currency conversion — the `Currency` enum exists but values are not
  normalized, so cross-market comparisons would be wrong until FX handling is added
  (**deferred**: only matters for cross-market SGX comps, which is post-SGX-mapper).
- Running tests via `python tests/test_company_comp.py` (script path) fails due to
  import path; must use `python -m tests.test_company_comp`.
- Cache `period` convention: still uses today's-ISO-date for everything; the
  fiscal-year/quarter/as-of-date split is proposed but not implemented (**deferred**).
- `companies` seed-universe table (from `schema.sql`) never built; the screener uses a
  hardcoded 2-ticker mining map (**deferred**).

## Evolution of decisions
- Chose `Decimal` for monetary fields (precision) over `float`.
- Chose computed/derived multiples over stored fields (consistency, no staleness).
- Chose explicit `is_screenable` + `exclusion_reasons` over silently skipping peers.
- Chose to avoid deprecated `json_encoders` (removed in Pydantic V3), using
  `field_serializer` instead.
- Chose a hand-rolled script test runner over pytest (no test framework installed).
- Chose Sectors v2 API as the data source, Streamlit as the deliverable, SQLite as the
  cache layer (all previously "TBD").
- Chose a two-mode (Simple/Advanced) architecture, split by whether a method requires
  forecasting — not by method name — so comps and reserve-adjusted comps sit in Simple,
  DCF and true NAV sit in Advanced.
- Chose to drop precedent transactions and the low-literacy/sentiment-driven segment
  from scope entirely, rather than deprioritize them.
- Chose "coverage-gap" over "literacy-gap" as the framing for the Simple-mode audience.
- Chose a hard, non-negotiable citation rule for the AI assistant: every AI-supplied
  value must carry a verifiable reference, with a technical backstop (curated
  reference set or verbatim quoting) rather than a prompt-level instruction alone.
- Chose `Authorization: <key>` (not `Bearer`) as the Sectors auth header, matching the
  API's actual `ApiKeyAuth` security scheme.
- Chose to key the cache on an application-defined `period` string (today's ISO date)
  because the company-report endpoint has no period parameter of its own; flagged for
  revisit once period-bearing endpoints (quarterly financials) are cached.
- Chose to make the cache-hit proof mechanically verified (request-count wrapper + assert
  of exactly one call) rather than trusted by inspection, so the demo can't drift from
  reality.
