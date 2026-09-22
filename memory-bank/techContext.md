# Tech Context

## Technologies (implemented)
- **Language**: Python 3.11.9
- **Pydantic 2.13.4** (with pydantic-core, typing-extensions) — data model.
- **requests 2.33.0** — HTTP client for the Sectors API (report, screener, news endpoints).
- **python-dotenv 1.2.2** — loads `SECTORS_API_KEY` from a local `.env`.
- **Streamlit** — the deliverable UI (single-user app, `streamlit run app.py`).
- **pandas** — DataFrame assembly for tables + Excel export.
- **openpyxl** — `.xlsx` export (formula-driven DCF sheet).
- **plotly** (`plotly>=5.18`) — the football-field chart (horizontal min–max bars).
- **SQLite (stdlib `sqlite3`)** — the cache layer.
- **Standard library**: `datetime.date`, `decimal.Decimal`, `enum.Enum`,
  `typing.Optional`, `json`, `os`.

## External APIs & tooling
- **Sectors v2 API** — wired in as the data source; base URL
  `https://api.sectors.app`, auth via `Authorization: <key>` header. Core and
  load-bearing: per the Sectors Hackathon 2026 rules, the product must lose its core
  functionality if Sectors data is removed. Confirmed contract for the company-report
  endpoint: `GET /v2/company/report/{symbol}/`, optional `sections` query param
  (`overview, valuation, future, financials, dividend, management, ownership, peers`);
  1 credit per requested section (8 for the default all-sections response).
- **Companies Screener (`GET /v2/companies/`)** — implemented and used for two things:
  (1) company-name → ticker search (`where=company_name like '%kw%'`), and (2) resolving
  a ticker's same-`sub_sector` peer *list* (`where=sub_sector = '<slug>'`). **Important
  limitation (verified live):** its `results` only ever return `symbol` + `company_name`
  — the multiple/balance-sheet fields are `where`/`order_by` filters (bracket notation
  `field[YYYY]`) but are never projected into the response. Real multiples must come
  from `company_report`. See `engine/peer_lookup.py`.
- **Sectors News (`GET /v2/news/`, `extension=idx`)** — implemented as the only news
  source (`sectors_news.py`); `symbols`/`sub_sector`/`sector`/`tags`/`keyword`/`start`/
  `end`/`limit` params; returns `title`/`body`/`source`/`timestamp`/`symbols`.
- **An LLM SDK** for the Advanced-mode input-filling assistant — not yet chosen. Whatever
  is chosen must support the citation-safety pattern in `systemPatterns.md` (either a
  constrained/curated retrieval set, or verbatim-quote retrieval) — a plain chat
  completion with an instruction to "cite sources" is not sufficient on its own.
  (Note: the current assistant is Sectors-native + curated-reference only; no live LLM.)

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
- `requirements.txt` exists and declares: `pydantic>=2.6`, `requests>=2.31`,
  `python-dotenv>=1.0`, `pandas>=2.0`, `streamlit>=1.40`, `openpyxl>=3.1`,
  `plotly>=5.18`. (No LLM SDK yet — the assistant is citation-safe + curated-reference
  only, so no SDK is required unless a live LLM is added later.)

## Tool usage patterns
- Git remote: `https://github.com/akmaladrianza/sectors-hackathon` (origin).
- Single commit so far: `5d193e6 Initial CompanyComp model with validation, screening
  flags, and test suite`. (Local working tree has significant uncommitted changes as of
  this entry — see `progress.md` "Current status".)

## API cost patterns (Sectors credits)
- `company_report` costs **1 credit per requested section**; the main screener requests
  `overview` + `financials` + `valuation` (3 credits) per ticker.
- The football-field peer resolution costs an additional **~2 credits × up to 5 peers ≈
  10 credits per subject company**, cached in `st.session_state` + SQLite per session.
- `GET /v2/companies/` and `GET /v2/news/` each cost **1 credit** per call.

## Known gaps / TODOs
- Consider adopting pytest (or keep the script runner — TBD).
- No CI/CD, no linter/type-checker config, no README.
- Cache `period` convention still uses today's-ISO-date (per-endpoint TTL policy from
  `endpoint_registry.py` is designed but not implemented).
- `companies` seed-universe table (from `schema.sql`) never built; the screener uses a
  hardcoded 2-ticker mining map (MDKA/ADRO) rather than a dynamic
  `get_mining_companies()` lookup. TODO carried from earlier rounds.
