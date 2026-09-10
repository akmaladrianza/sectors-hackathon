# Active Context

## Current work focus
Initializing the Memory Bank for the `Sectors_Hackathon` project. The codebase itself
is at its first commit (the `CompanyComp` model + tests).

## Recent changes
- Initial commit: `5d193e6` — "Initial CompanyComp model with validation, screening
  flags, and test suite".
- Created the `memory-bank/` directory and its core files (this initial).

## Next steps (candidates, not yet committed)
1. Add the **screener/ranking layer** that consumes a list of `CompanyComp` and
   partitions/ranks them by valuation multiples.
2. Decide and document the **data source / ingestion** approach (static fixtures, CSV,
   an external API, or an exchange feed).
3. Implement **currency normalization / FX conversion** so cross-market peers are
   comparable.
4. Fix **true P/B** by adding `total_equity` (or liabilities) to the model.
5. Add a **dependency manifest** and, optionally, migrate tests to pytest + CI.

## Active decisions and considerations
- Test invocation convention: use `python -m tests.test_company_comp` (module form),
  not the script path.

## Open questions for the user
- What is the intended **data source** for comparable-company data?
- What is the hackathon's **target deliverable** — a library, CLI, REST API, or web
  UI?
- Should the project **adopt pytest** (and formal packaging) or stay script-based?
- Which **sector(s) / market(s)** are in scope for the screener (the currency enum
  hints at multi-market: USD, EUR, IDR, SGD, GBP, JPY)?

## Important patterns and preferences
- Keep monetary fields as `Decimal`; emit floats only at the JSON serialization
  boundary.
- Prefer derived/computed multiples over stored values.
- Keep exclusions explicit and human-readable (`exclusion_reasons`).
- Accept `Optional` inputs everywhere except stable identifiers.
