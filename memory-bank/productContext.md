# Product Context

## Why this project exists
Comparable-company ("comps") analysis is a core technique in equity research and
investment banking: an analyst picks a set of peer companies and compares their
valuation multiples to decide whether a given company is under- or over-valued.

At the market level, this project exists because Indonesia's capital market has a real
coverage gap: retail investors already drive the majority of daily trading value, but
professional analyst coverage clusters almost entirely around LQ45 and other large caps.
Everything else — most of the ~900+ listed names, and every mining company whose earnings
are commodity-cyclical rather than reserve-based — is underserved. Mimir automates the
mechanical layers of fundamental analysis (comps, reserve-adjusted valuation, DCF
scaffolding) so that coverage gap narrows, without pretending the tool can or should reach
the sentiment-driven, low-literacy segment of the market — that's a different
(educational) problem, explicitly out of scope here.

At the technical level, the foundation so far is a single, well-behaved data model
(`CompanyComp`) that can hold any comparable company's financial snapshot and compute its
valuation multiples safely.

## Problem it solves
**Market-level problem:** a defensible valuation output — one an M&A advisor could put in
front of an IC, or a self-directed investor could trust for a name nobody covers —
currently takes days of manually reconciling filings, pricing data, and (for miners)
reserve disclosures that live in entirely separate places.

**Data-level problem** (what the current codebase addresses): real-world financial data
is messy:
- Fields are often missing (a small-cap peer may not report EBITDA; a private comp has
  no market cap).
- Magnitudes are large (billions/trillions), where floating-point arithmetic can
  introduce meaningful error.
- A naive implementation that computes multiples from incomplete inputs either crashes
  or silently produces wrong output.

The `CompanyComp` model addresses all three:
- Missing inputs propagate to `None` multiples instead of raising or lying.
- Monetary values use `Decimal`.
- Multiples are *derived* (`computed_field`) from raw figures, so they can never be
  inconsistent, and a missing `market_cap`/EBITDA degrades gracefully.

## How it should work
1. Ingest one company's raw financials into `CompanyComp` — implemented.
2. The model backfills `market_cap` from `price * shares_outstanding` if omitted —
   implemented.
3. Derived valuation multiples are computed on demand — implemented for standard comps.
4. An `is_screenable` flag plus an `exclusion_reasons` list tell the caller whether this
   peer can be screened and, if not, exactly why — implemented.
5. A screener ranks/compares all screenable peers; excluded peers are reported explicitly
   rather than silently dropped — **not yet built**.
6. **Two modes wrap the above, plus new layers** (not yet built):
   - **Simple mode**: comps + a mining overlay (EV/tonne of reserves, EV/tonne of
     production, reserve life, export concentration) — everything here is arithmetic on
     current disclosed data.
   - **Advanced mode**: adds DCF (sector-conditional proxy defaults, an "expected rate of
     return" question standing in for textbook WACC) and true per-asset NAV — both
     require forecasting, both gated behind Advanced mode.
7. **An AI assistant helps fill Advanced-mode inputs** (revenue growth, working capital,
   capex, and research lookups like asset useful life) — not yet built. Hard rule: every
   value it supplies must carry a stated, verifiable reference; Sectors-native data is
   exempt from this (it's just the cache), general-knowledge lookups are not.

## User experience goals
- **Auditable exclusions**: a user must be able to see *why* a peer was excluded
  ("missing market_cap", "non-positive ebitda"), not just that it disappeared.
- **No silent wrong answers**: every multiple is either correct or `None`/`N/A`.
- **Stable JSON**: monetary fields serialize as floats (numbers) in JSON mode, not as
  strings, so downstream clients/tools get numeric values.
- **Defensible by design**: every number — comps, reserve-adjusted, or AI-assisted —
  traces to a source. This is the product's differentiator against both generic retail
  screeners (which show data but not synthesis) and generic AI-analyst tools (which
  synthesize but aren't scoped to IDX/SGX or reserve-based valuation).
- **Two audiences, one mechanic**: a coverage-gap self-directed investor and an M&A
  advisor should feel like they're using the same tool at two depths, not two different
  products — Simple and Advanced share the same underlying calculations, Advanced just
  exposes more assumptions to edit.
