# Tech Context

## Technologies (implemented)
- **Language**: Python 3.11.9
- **Pydantic 2.13.4** (with pydantic-core, typing-extensions) — data model.
- **requests 2.33.0** — HTTP client for the Sectors API.
- **python-dotenv 1.2.2** — loads `SECTORS_API_KEY` from a local `.env`.
- **SQLite (stdlib `sqlite3`)** — the cache layer.
- **Standard library**: `datetime.date`, `decimal.Decimal`, `enum.Enum`,
  `typing.Optional`, `json`, `os`.

## Technologies (decided, not yet added)
- **Sectors v2 API** — now wired in as the data source; base URL
  `https://api.sectors.app`, auth via `Authorization: <key>` header. Core and
  load-bearing: per the Sectors Hackathon 2026 rules, the product must lose its core
  functionality if Sectors data is removed. Confirmed contract for the company-report
  endpoint: `GET /v2/company/report/{symbol}/`, optional `sections` query param
  (`overview, valuation, future, financials, dividend, management, ownership, peers`);
  1 credit per requested section (8 for the default all-sections response).
- **Bulk screener endpoints (planned, not yet called):** `GET /v2/companies/` (IDX) and
  `GET /v2/sgx/companies/` (SGX) — structured `where`/`order_by`/`limit` queries for an
  entire comp set in 1 credit (versus per-company report calls). IDX returns precomputed
  `enterprise_to_ebitda`/`enterprise_to_revenue`; SGX exposes `total_liabilities`/
  `total_equity` but no `total_debt`/`cash_and_equivalents` (annual financials only, no
  quarterly). Documented in `endpoint_registry.py` / `BLUEPRINT.md` sections 2 and 4.
- **Streamlit** — the deliverable UI. Single-user, local; no live deployment required
  for the hackathon submission.
- **An LLM SDK** for the Advanced-mode input-filling assistant — not yet chosen. Whatever
  is chosen must support the citation-safety pattern in `systemPatterns.md` (either a
  constrained/curated retrieval set, or verbatim-quote retrieval) — a plain chat
  completion with an instruction to "cite sources" is not sufficient on its own.

## Development setup
- **OS / shell**: Windows (win32), PowerShell.
- **Run tests**: `python -m tests.test_company_comp`
  - Note: running `python tests/test_company_comp.py` directly FAILS with
    `ModuleNotFoundError: No module named 'models'` because the script imports
    `from models.company_comp import ...`. Use the `-m` module form (run from the repo
    root), which puts the repo root on `sys.path`.
- **Run the client+cache proof**: `python scripts/prove_bbca_pull.py`
  (requires `SECTORS_API_KEY` in `.env`; script inserts the repo root on `sys.path`
  itself so it can be run directly).
- **Test framework**: none installed. Tests are a hand-rolled script with `assert`
  statements and a `main()` guarded by `if __name__ == "__main__":`. No pytest/unittest.

## Technical constraints
- `Decimal` fields with `ge=0` guard non-negative financial values; validation rejects
  negative market cap, price, shares outstanding, revenue, total assets, and cash, plus
  empty-string identifiers.
- **Hackathon constraints** (Sectors Hackathon 2026 official rules — not just style
  preferences, these gate eligibility):
  - No project code before 19 August 2026 (build period start); repo created during the
    build period; commit history is inspectable by judges.
  - Automated trade execution is prohibited in every track — analysis, screening,
    scoring, and alerting are fine; placing or executing orders is not.
  - The product must not read as financial advice — position as an information/analysis
    tool, disclaimer required where relevant.
  - Submission freezes the repo (only exception: rotating a leaked credential).

## Dependencies
- No `requirements.txt`, `pyproject.toml`, `setup.py`, or `setup.cfg` exists yet.
  **Gap**: dependencies are currently implicit — Pydantic 2.13.4, requests 2.33.0, and
  python-dotenv 1.2.2 are installed in the active Python environment but not declared.
  A manifest should be added — and updated again once Streamlit, a Sectors API client
  (for real), and an LLM SDK are added.

## Tool usage patterns
- Git remote: `https://github.com/akmaladrianza/sectors-hackathon` (origin).
- Single commit so far: `5d193e6 Initial CompanyComp model with validation, screening
  flags, and test suite`.

## Known gaps / TODOs
- Add a dependency manifest (`requirements.txt` / `pyproject.toml`).
- Consider adopting pytest (or keep the script runner — TBD).
- No CI/CD, no linter/type-checker config, no README.
- Map cached report JSON → `CompanyComp` fields (next build step).
- Streamlit UI, mining overlay data model, DCF/NAV logic, and the AI assistant are all
  decided but not started — see `activeContext.md` for build sequencing.
