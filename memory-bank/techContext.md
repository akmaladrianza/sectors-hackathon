# Tech Context

## Technologies
- **Language**: Python 3.11.9
- **Primary dependency**: Pydantic 2.13.4 (with pydantic-core, typing-extensions)
- **Standard library**: `datetime.date`, `decimal.Decimal`, `enum.Enum`,
  `typing.Optional`

## Development setup
- **OS / shell**: Windows (win32), PowerShell.
- **Run tests**: `python -m tests.test_company_comp`
  - Note: running `python tests/test_company_comp.py` directly FAILS with
    `ModuleNotFoundError: No module named 'models'` because the script imports
    `from models.company_comp import ...`. Use the `-m` module form (run from the
    repo root), which puts the repo root on `sys.path`.
- **Test framework**: none installed. Tests are a hand-rolled script with `assert`
  statements and a `main()` guarded by `if __name__ == "__main__":`. No pytest/unittest.

## Technical constraints
- `Decimal` fields with `ge=0` guard non-negative financial values; validation
  rejects negative market cap, price, shares outstanding, revenue, total assets, and
  cash, plus empty-string identifiers.

## Dependencies
- No `requirements.txt`, `pyproject.toml`, `setup.py`, or `setup.cfg` exists yet.
  **Gap**: dependencies are currently implicit (Pydantic 2.13.4 is installed in the
  active Python environment). A manifest should be added.

## Tool usage patterns
- Git remote: `https://github.com/akmaladrianza/sectors-hackathon` (origin).
- Single commit so far: `5d193e6 Initial CompanyComp model with validation, screening
  flags, and test suite`.

## Known gaps / TODOs
- Add a dependency manifest (`requirements.txt` / `pyproject.toml`).
- Consider adopting pytest (or keep the script runner — TBD).
- No CI/CD, no linter/type-checker config, no README.
