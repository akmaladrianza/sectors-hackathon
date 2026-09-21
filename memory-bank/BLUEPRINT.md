# Sectors Hackathon 2026 — Comps Tool Blueprint

**Project:** Comparable company analysis tool + mining sector overlay
**Stack:** Python, Streamlit, SQLite, Sectors v2 API
**Repo:** C:\Users\User\Sectors_Hackathon
**Status:** Pre-Memory-Bank planning artifact — superseded where it diverges from the core Memory Bank files (see "Reconciliation with the Memory Bank" below).

> **Note (added after the Memory Bank was created):** this file predates the
> `memory-bank/` directory. It is a design draft, not the current source of truth — the six
> core Memory Bank files (`activeContext.md`, `progress.md`, `productContext.md`,
> `projectbrief.md`, `systemPatterns.md`, `techContext.md`) are authoritative per
> `.clinerulesmemory-bank.md.txt`. Where this document’s proposals were actually built,
> defer to what shipped (documented in `systemPatterns.md`); where they weren’t, they’re
> still useful design input and are folded into the core files’ "next steps" /
> "what’s left to build" sections, as cited below.

## Reconciliation with the Memory Bank (added post-hoc)

This file, `schema.sql`, and `endpoint_registry.py` were drafted before the
`memory-bank/` directory existed and before `sectors_client/` + `cache/` were actually
built. Comparing the two:

1. **Cache schema differs from what shipped.** This file’s `api_cache` table (see
   `schema.sql`) uses columns `(entity_id, endpoint, period, response_json, credits_spent,
   fetched_at)`. The cache actually built (`cache/sqlite_cache.py`) uses
   `cache_entries(company, period, endpoint, payload, fetched_at)` — no `credits_spent`
   column, and `company` instead of the more generic `entity_id`. **Resolution:** `company`
   is the term of record (matches `systemPatterns.md`), used generically to also hold mining
   slugs once the mining overlay is built (no rename to `entity_id` — naming preference
   does not justify code churn). Whether to add `credits_spent` back is still open — see
   `activeContext.md`.
2. **`build_sessions` table is dropped**, superseded by `progress.md` / `activeContext.md`
   functioning as the session log (see `architectureOverview.md` section 7 and
   `.clinerulesmemory-bank.md.txt`). The `build_sessions` DDL in `schema.sql` is retained
   only as a historical record.
3. **`companies` seed-universe table is still a legitimate, not-yet-built** piece of the
   target design (ticker registry with `is_bank`/`is_mining`/`mining_slug`) — tracked in
   `progress.md`’s "what’s left to build."
4. **No cache TTL/staleness policy is implemented.** Section 3 below and
   `endpoint_registry.py`’s `cache_ttl_days` describe a policy that `cache/sqlite_cache.py`
   does not enforce today — a cache hit is valid forever until `clear()` is called manually.
   Tracked as a real gap in `progress.md`.
5. **The `period` convention proposal (fiscal year / quarter / as-of date) resolves an open
   question** flagged in `activeContext.md` (today’s `company_report` call bundles
   point-in-time and annual data under one `period` key, which is wrong for the annual
   portion). Adopted as the proposed design in `activeContext.md`, not yet implemented.
6. **The SGX EV data gap (decision 4 below) is a real correctness issue**, not just a
   documentation gap: `CompanyComp.enterprise_value` treats missing `total_debt`/
   `cash_and_equivalents` as zero rather than excluding the peer, so an SGX company would
   silently get an understated EV instead of `None`. Tracked as higher-severity in
   `activeContext.md` pending a decision.
7. **The bulk screener endpoints (`/v2/companies/`, `/v2/sgx/companies/`)** in sections 2
   and 4 below are a genuinely valuable, not-yet-built addition — added to `techContext.md`
   and prioritized in `activeContext.md`’s next steps, ahead of the screener/ranking layer.

The rest of this document is retained below as originally drafted, as design input for the
items above — not as a competing source of truth.

---

## 1. Roadmap (from kickoff)

| # | Phase | Status |
|---|-------|--------|
| 1 | SQLite cache schema (ticker/entity + endpoint + period) | Drafted below |
| 2 | Sectors v2 endpoint map (comps core + mining overlay) | Drafted below |
| 3 | Full pipeline: seed tickers → multiples table | Not started |
| 4 | Mining overlay: EV/tonne reserves, EV/tonne production, export concentration | Not started |
| 5 | SGX annual-only periodicity + bank metric swap handling | Partially informed (see §4) |
| 6 | xlsx export | Not started |
| 7 | Session log | This entry is Session 1 |

---

## 2. Key architecture decisions made this session

1. **Cache key is `entity_id`, not strictly `ticker`.** Mining-extension endpoints
   (`financials`, `performance`, `sales-destination`) key on a company **slug**, not an
   IDX symbol — some mining operators aren't even listed (`symbol: null`). Generalising
   the cache key to `entity_id` lets the same table hold IDX tickers, SGX tickers, and
   mining slugs without a schema fork. `companies.mining_slug` is the join column that
   links a listed ticker to its mining-extension identity.

2. **Comps core should be sourced from the bulk screener, not per-ticker `company/report`
   calls.** `/v2/companies/` (IDX) and `/v2/sgx/companies/` (SGX) accept a structured
   `where=symbol in [...]` query and return `market_cap`, `revenue`, `ebitda`, `ebit`,
   `earnings`, `pe`, `pb`, `ps`, and — for IDX only — **precomputed** `enterprise_to_ebitda`
   and `enterprise_to_revenue`, all for **1 credit regardless of how many tickers match**.
   Hitting `company/report/{symbol}/` per ticker would cost 1 credit per section per
   company — for a ~30-50 ticker comp set that's 30-50x more expensive for the same core
   fields. The report endpoint is now a **fallback** for fields the screener doesn't expose
   (ownership, management, peers list, dividend history).

3. **Batch responses are decomposed at cache-write time.** A single screener call returns
   many companies, but the cache is still keyed one row per `(entity_id, endpoint, period)`.
   After a screener call returns, the pipeline loops the `results` array and writes one
   cache row per ticker. This means adding one new ticker to the universe next session
   doesn't force re-fetching everyone — the cache is checked per-ticker before deciding
   what subset actually needs a fresh screener call.

4. **A real gap, not yet resolved: SGX enterprise value may not be computable from Sectors
   data alone.** The SGX screener and SGX company report both expose `total_liabilities`
   and `total_equity` but **no `total_debt` or `cash_and_equivalents` field** — unlike IDX,
   where both are present and even net out into a precomputed EV multiple. Practical
   effect: for SGX names, price-based multiples (PE, PB, PS, PCF) are reliably computable;
   EV/EBITDA and EV/Revenue are not, without pulling debt/cash from a second source. This
   needs a decision before Phase 3: (a) restrict SGX comps to price multiples only, (b)
   supplement via yfinance balance sheet data, or (c) exclude SGX from EV-based rows and
   flag it in the xlsx output rather than fabricate a number. Leaning toward (a) + a visible
   footnote — revisit when the pipeline is actually built.

5. **SGX coverage is tiered, not uniform.** Per the API docs directly: `ebit`, `ebitda`,
   and most balance-sheet/cash-flow fields on the SGX screener are populated for **~22
   large-caps only**; `net_interest_income` and other bank fields are populated for
   **DBS/OCBC/UOB only**. The pipeline needs a coverage check per field per ticker, not an
   assumption that a null means "not applicable" — it may just mean "not in the covered
   tier." This is a strictly stronger version of the "bank sector metric swap" you flagged
   at kickoff: it turns out to apply to *all* SGX fundamentals, not just banks.

6. **Confirmed, not assumed: SGX has no quarterly data.** Directly from the docs: *"SGX
   data is annual only — there is no quarterly data."* This settles Phase 5's periodicity
   question for SGX specifically — the pipeline should never attempt a `[Qn-YYYY]` bracket
   query against `/v2/sgx/companies/`, and period handling for SGX rows is always `'YYYY'`.

---

## 3. SQLite schema (Phase 1)

See `schema.sql` for the runnable DDL. Three tables:

- **`companies`** — the seed universe. One row per ticker, with sector/sub-sector,
  `is_bank` (drives the metric-swap branch), `is_mining` + `mining_slug` (drives the
  overlay join).
- **`api_cache`** — every raw API response, keyed `(entity_id, endpoint, period)`.
  `endpoint` is a logical key from `endpoint_registry.py`, not a raw URL, so the cache
  survives if a path changes. Stores the full response JSON, not a normalized shape —
  normalization happens in Python at read time, keeping the cache schema stable even as
  which fields we pull evolves.
- **`build_sessions`** — Phase 7's session log. One row per work session, with phase,
  status, a free-text summary, blockers, and credits spent that session.

Cache TTL is **not** a column — it's policy, and policy differs wildly by endpoint (a
2019 annual financial statement is immutable; today's `market_cap` is not). That policy
lives in `endpoint_registry.py` as `cache_ttl_days` per logical endpoint, so the pipeline
checks `fetched_at` against the registry's TTL for that specific endpoint before deciding
to hit the cache or the API.

---

## 4. Endpoint map (Phase 2)

Full detail is in `endpoint_registry.py`. Summary:

### Comps core
| Logical key | Path | Domain | Period | Notes |
|---|---|---|---|---|
| `idx_screener` | `/v2/companies/` | IDX | annual + quarterly (bracket) | Primary source. 1 credit for the whole matched universe. |
| `sgx_screener` | `/v2/sgx/companies/` | SGX | **annual only** | No `total_debt`/`cash_and_equivalents`. EV fields absent — see decision 4 above. |
| `idx_report_section` | `/v2/company/report/{symbol}/` | IDX | mixed | Fallback for ownership/management/peers/dividend. 1 credit **per section**. |
| `sgx_report_section` | `/v2/sgx/company/report/{symbol}/` | SGX | mixed | Only 4 sections exist (overview/valuation/financials/dividend). |

### Mining overlay
| Logical key | Path | Period | Feeds |
|---|---|---|---|
| `mining_companies_list` | `/v2/mining/companies/` | n/a | One-time build of the ticker↔slug map. `symbol` is null for unlisted operators — filter before joining. |
| `mining_financials` | `/v2/mining/companies/financials/{slug}/` | annual | Revenue/assets/profit in USD millions — mining-specific financials, separate from the IDX screener's IDR figures. |
| `mining_performance` | `/v2/mining/companies/performance/{slug}/` | annual | `production_volume`, `resources_reserves.total_reserves_Mt` — **direct source for EV/tonne of reserves and EV/tonne of production.** Returns one array entry per commodity the company reports. |
| `mining_sales_destination` | `/v2/mining/sales-destination/{slug}/` | annual | Company-level revenue/volume by destination country — **source for export-destination concentration** (e.g. an HHI on `percentage_of_sales_volume`). Note: this is company-level, distinct from the national-aggregate "Top Export Destinations" endpoint, which is the wrong granularity for a per-company overlay metric. |

---

## 5. Open questions to resolve in Phase 3

- [ ] Confirm `where=symbol in ['BBCA','TLKM',...]` is valid screener syntax (docs show
      `in` only demonstrated on array fields like `tags`/`indices`; `symbol` is a direct
      field). If unsupported, fall back to `where=symbol='BBCA' or symbol='TLKM' or ...`
      or paginate with a `market_cap` floor instead.
- [ ] Decide the SGX EV treatment (decision 4 above) before building the multiples table.
- [ ] Confirm `has_financials=true` on `mining_companies_list` reliably filters to
      companies worth caching, to avoid wasting rows on shell/holding entities with no data.

---

## 6. Session log (Phase 7)

| Session | Date | Phase(s) | Status | Summary | Blockers |
|---|---|---|---|---|---|
| 1 | 2026-09-06 | 1, 2 | Done | Researched live Sectors v2 API reference; drafted cache schema, endpoint registry, and 5 architecture decisions (see §2). | SGX EV computability (decision 4) and `symbol in [...]` syntax (open question) need resolving before Phase 3 pipeline code is written. |

---

## Changelog

- **2026-09-06** — Initial version. Schema and endpoint map drafted from live API docs
  rather than assumption; original kickoff plan's "SGX annual-only constraint" confirmed
  and found to be broader than expected (coverage tiering, not just periodicity).
