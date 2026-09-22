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
) -> None:
    """Write a formula-driven 2-stage DCF onto a workbook via an openpyxl writer.

    Layout: assumption cells in column B (rows 2..8), then a per-year projection
    block with formulas, terminal value, and the intrinsic EV / equity / price cells.
    Financial-period provenance (fiscal period / as-of date) is written into columns
    D/E so the formula anchor cells ($B$2..$B$7) never shift.
    """
    from openpyxl.utils import get_column_letter

    ws = writer.book.create_sheet(sheet_name)

    # --- Data provenance (financial period the DCF is built on) -------------
    if fiscal_period or as_of_date:
        ws["D1"] = "Financial period"
        ws["E1"] = fiscal_period or ""
        ws["D2"] = "As of"
        ws["E2"] = as_of_date or ""

    # --- Assumptions --------------------------------------------------------
    ws["A1"] = "Assumption"
    ws["B1"] = "Value"
    ws["A2"] = "Revenue (Year 0)"
    ws["B2"] = _d(revenue)
    ws["A3"] = "Growth rate (g)"
    ws["B3"] = _d(g)
    ws["A4"] = "FCF margin (m)"
    ws["B4"] = _d(m)
    ws["A5"] = "Discount rate (r)"
    ws["B5"] = _d(r)
    ws["A6"] = "Terminal growth"
    ws["B6"] = _d(tvg)
    ws["A7"] = "Years"
    ws["B7"] = years

    # --- Projection block ---------------------------------------------------
    start = 10
    ws.cell(row=start, column=1, value="Year")
    ws.cell(row=start, column=2, value="Revenue")
    ws.cell(row=start, column=3, value="FCF")
    ws.cell(row=start, column=4, value="Discount factor")
    ws.cell(row=start, column=5, value="PV of FCF")

    for t in range(1, years + 1):
        row = start + t
        ws.cell(row=row, column=1, value=t)
        ws.cell(row=row, column=2, value=f"=$B$2*(1+$B$3)^{t}")
        ws.cell(row=row, column=3, value=f"={get_column_letter(2)}{row}*$B$4")
        ws.cell(row=row, column=4, value=f"=(1+$B$5)^{-t}")
        ws.cell(row=row, column=5, value=f"={get_column_letter(3)}{row}/{get_column_letter(4)}{row}")

    # --- Terminal value + sums ----------------------------------------------
    tv_row = start + years + 2
    ws.cell(row=tv_row, column=1, value="Terminal value")
    final_fcf_ref = f"{get_column_letter(3)}{start + years}"
    ws.cell(
        row=tv_row,
        column=5,
        value=f"={final_fcf_ref}*(1+$B$6)/($B$5-$B$6)",
    )
    ws.cell(row=tv_row, column=4, value=f"=(1+$B$5)^{-years}")

    pv_terminal_ref = f"{get_column_letter(5)}{tv_row}"
    sum_row = tv_row + 1
    ws.cell(row=sum_row, column=1, value="Intrinsic EV")
    ws.cell(
        row=sum_row,
        column=5,
        value=f"=SUM({get_column_letter(5)}{start+1}:{get_column_letter(5)}{start+years})"
        f" + ({pv_terminal_ref}/{get_column_letter(4)}{tv_row})",
    )

    # --- FCFE bridge --------------------------------------------------------
    if net_debt is not None:
        eq_row = sum_row + 1
        ws.cell(row=eq_row, column=1, value="Intrinsic equity (EV - net debt)")
        ws.cell(row=eq_row, column=5, value=f"={get_column_letter(5)}{sum_row}-{_d(net_debt)}")
        if shares_outstanding and shares_outstanding > 0:
            px_row = eq_row + 1
            ws.cell(row=px_row, column=1, value="Intrinsic price per share")
            ws.cell(row=px_row, column=5, value=f"={get_column_letter(5)}{eq_row}/{_d(shares_outstanding)}")
