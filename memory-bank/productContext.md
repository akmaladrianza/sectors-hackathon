# Product Context

## Why this project exists
Comparable-company ("comps") analysis is a core technique in equity research and
investment banking: an analyst picks a set of peer companies and compares their
valuation multiples to decide whether a given company is under- or over-valued.

The hackathon project automates this comparison. The foundation so far is a single,
well-behaved data model that can hold any comparable company's financial snapshot and
compute its valuation multiples safely.

## Problem it solves
Real-world financial data is messy:
- Fields are often missing (a small-cap peer may not report EBITDA; a private comp has
  no market cap).
- Magnitudes are large (billions/trillions), where floating-point arithmetic can
  introduce meaningful error.
- A naive implementation that computes multiples from incomplete inputs either crashes
  or silently produces wrong output.

This model addresses all three:
- Missing inputs propagate to `None` multiples instead of raising or lying.
- Monetary values use `Decimal`.
- Multiples are *derived* (`computed_field`) from raw figures, so they can never be
  inconsistent, and a missing `market_cap`/EBITDA degrades gracefully.

## How it should work
1. Ingest one company's raw financials into `CompanyComp`.
2. The model backfills `market_cap` from `price * shares_outstanding` if omitted.
3. Derived valuation multiples (`enterprise_value`, `ev_to_ebitda`, `ev_to_revenue`,
   `pe_ratio`, `price_to_book`) are computed on demand.
4. An `is_screenable` flag plus an `exclusion_reasons` list tell the caller whether
   this peer can be screened and, if not, exactly why.
5. (Future) a screener ranks/compares all screenable peers; excluded peers are
   reported explicitly rather than silently dropped.

## User experience goals
- **Auditable exclusions**: a user must be able to see *why* a peer was excluded
  ("missing market_cap", "non-positive ebitda"), not just that it disappeared.
- **No silent wrong answers**: every multiple is either correct or `None`.
- **Stable JSON**: monetary fields serialize as floats (numbers) in JSON mode, not as
  strings, so downstream clients/tools get numeric values.
