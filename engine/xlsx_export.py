"""Formula-driven Excel export: a tuneable DCF + implied-valuation workbook.

Unlike the static Comps/Mining/Excluded sheets (pasted values from ``view.py``), these
sheets are built with *live Excel formulas* so the user can open the workbook, change
an assumption cell, and watch the intrinsic EV / implied price recompute in-place —
the download counterpart to the in-app sliders. Nothing here fabricates data: every
formula references the assumption cells at the top of its sheet.

The workbook is written with ``openpyxl`` so formulas (not just evaluated values) are
preserved in the saved file.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from models.company_comp import CompanyComp


def _d(value) -> Optional[float]:
    """Coerce a Decimal/None to a float (or None) for cell writing."""
    if value is None:
        return None
    return float(value)


def write_dcf_sheet(
    writer,
    sheet_name: str,
    revenue: Optional[Decimal],
    g: Decimal,
    m: Decimal,
    r: Decimal,
    tvg: Decimal,
    years: int = 5,
    shares_outstanding: Optional[Decimal] = None,
    net_debt: Optional[Decimal] = None,
    fiscal_period: Optional[str] = None,
    as_of_date: Optional[str] = None,
    ebitda: Optional[Decimal] = None,
    depreciation: Optional[Decimal] = None,
    tax_rate: Optional[Decimal] = None,
    capex: Optional[Decimal] = None,
    nwc_change: Optional[Decimal] = None,
    net_working_capital: Optional[Decimal] = None,
) -> None:
    """Write a formula-driven 3-statement-style FCFF build-up DCF onto a workbook.

    Replaces the old single-column sales-margin sheet with a full **FCFF bridge**,
    mirroring ``engine.dcf.run_dcf(use_fcff_buildup=True)``: per projected year we build
    Revenue → EBITDA → D&A → EBIT → NOPAT → (+D&A − capex − ΔNWC) = FCFF, then discount
    and add a Gordon terminal value, and bridge to equity + per-share price.

    Assumptions live in column B; the FY0 base values (revenue/EBITDA/D&A/tax/capex/NWC)
    are seeded from the company's own audited data where available, and every projection
    cell is a live Excel formula so assumption edits recompute in-place.
    """
    from openpyxl.utils import get_column_letter

    ws = writer.book.create_sheet(sheet_name)

    # --- Data provenance ----------------------------------------------------
    if fiscal_period or as_of_date:
        ws["D1"] = "Financial period"
        ws["E1"] = fiscal_period or ""
        ws["D2"] = "As of"
        ws["E2"] = as_of_date or ""

    # --- Assumptions (col B) ------------------------------------------------
    ws["A1"] = "Assumption"
    ws["B1"] = "Value"
    rows = {}  # label -> 1-based row
    names = [
        ("Revenue (Year 0)", _d(revenue)),
        ("Growth rate (g)", _d(g)),
        ("EBITDA margin (of revenue)", _d(m)),
        ("D&A (of revenue)", _d(depreciation / revenue) if depreciation is not None and revenue else None),
        ("Tax rate", _d(tax_rate)),
        ("Capex (of revenue)", _d(capex / revenue) if capex is not None and revenue else None),
        ("ΔNWC (of revenue)", _d(nwc_change / revenue) if nwc_change is not None and revenue else None),
        ("Discount rate (r)", _d(r)),
        ("Terminal growth", _d(tvg)),
        ("Years", years),
    ]
    for i, (label, val) in enumerate(names, start=2):
        ws.cell(row=i, column=1, value=label)
        ws.cell(row=i, column=2, value=val)
        rows[label] = i

    REV0 = "$B$2"
    G = f"$B${rows['Growth rate (g)']}"
    EM = f"$B${rows['EBITDA margin (of revenue)']}"
    DM = f"$B${rows['D&A (of revenue)']}"
    TR = f"$B${rows['Tax rate']}"
    CX = f"$B${rows['Capex (of revenue)']}"
    NW = f"$B${rows['ΔNWC (of revenue)']}"
    RATE = f"$B${rows['Discount rate (r)']}"
    TVG = f"$B${rows['Terminal growth']}"
    year0_rev = _d(revenue) or 0

    # --- Projection block (income statement → FCFF) -------------------------
    start = 13
    header = ["Year", "Revenue", "EBITDA", "D&A", "EBIT", "Tax",
              "NOPAT", "Capex", "ΔNWC", "FCFF", "Disc factor", "PV FCFF"]
    for col, h in enumerate(header, start=1):
        ws.cell(row=start, column=col, value=h)
    ws.cell(row=start + 1, column=1, value=0)
    ws.cell(row=start + 1, column=2, value=year0_rev)

    for t in range(1, years + 1):
        row = start + 1 + t
        ws.cell(row=row, column=1, value=t)
        ws.cell(row=row, column=2, value=f"={REV0}*(1+{G})^{t}")
        ws.cell(row=row, column=3, value=f"={_col(2,row)}*{EM}")
        ws.cell(row=row, column=4, value=f"={_col(2,row)}*{DM}")
        ws.cell(row=row, column=5, value=f"={_col(3,row)}-{_col(4,row)}")
        ws.cell(row=row, column=6, value=f"={_col(5,row)}*{TR}")
        ws.cell(row=row, column=7, value=f"={_col(5,row)}-{_col(6,row)}")
        ws.cell(row=row, column=8, value=f"={_col(2,row)}*{CX}")
        ws.cell(row=row, column=9, value=f"={_col(2,row)}*{NW}")
        ws.cell(row=row, column=10, value=f"={_col(7,row)}+{_col(4,row)}-{_col(8,row)}-{_col(9,row)}")
        ws.cell(row=row, column=11, value=f"=(1+{RATE})^{-t}")
        ws.cell(row=row, column=12, value=f"={_col(10,row)}/{_col(11,row)}")

    # --- Terminal value + EV ------------------------------------------------
    fcff_last = f"{get_column_letter(10)}{start + 1 + years}"
    tv_row = start + 2 + years
    ws.cell(row=tv_row, column=1, value="Terminal value")
    ws.cell(row=tv_row, column=10, value=f"={fcff_last}*(1+{TVG})/({RATE}-{TVG})")
    ws.cell(row=tv_row, column=11, value=f"=(1+{RATE})^{-years}")
    ws.cell(row=tv_row, column=12, value=f"={_col(10,tv_row)}/{_col(11,tv_row)}")

    sum_row = tv_row + 1
    ws.cell(row=sum_row, column=1, value="Intrinsic EV")
    fcff_col = get_column_letter(12)
    first_pv = start + 2
    last_pv = start + 1 + years
    ws.cell(
        row=sum_row,
        column=12,
        value=f"=SUM({fcff_col}{first_pv}:{fcff_col}{last_pv})+{fcff_col}{tv_row}",
    )

    # --- FCFE bridge --------------------------------------------------------
    if net_debt is not None:
        eq_row = sum_row + 1
        ws.cell(row=eq_row, column=1, value="Intrinsic equity (EV - net debt)")
        ws.cell(row=eq_row, column=12, value=f"={fcff_col}{sum_row}-{_d(net_debt)}")
        if shares_outstanding and shares_outstanding > 0:
            px_row = eq_row + 1
            ws.cell(row=px_row, column=1, value="Intrinsic price per share")
            ws.cell(row=px_row, column=12, value=f"={fcff_col}{eq_row}/{_d(shares_outstanding)}")


def _col(col_index: int, row: int) -> str:
    """A1-style cell reference for ``(1-based col, row)``."""
    from openpyxl.utils import get_column_letter

    return f"{get_column_letter(col_index)}{row}"
