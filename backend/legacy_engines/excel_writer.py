"""
excel_writer.py
Generates Output_Analysis.xlsx with LIVE Excel formulas (not pre-computed values).

Color coding follows financial-modeling industry standards:
  Blue text  → hardcoded inputs (analyst can edit these)
  Black text → formulas / calculations (auto-recalculate)
"""

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
from pathlib import Path
from engine_utils import setup_logger

logger = setup_logger("excel_writer")

# ── Style constants ──────────────────────────────────────────────────
CLR_HEADER_DARK  = "1F3864"
CLR_HEADER_MID   = "2E75B6"
CLR_HEADER_LIGHT = "D6E4F0"
CLR_STRIPE       = "F2F9FF"
CLR_TITLE_FONT   = "FFFFFF"
CLR_GREEN        = "92D050"
CLR_YELLOW       = "FFFF00"
CLR_RED          = "FF6666"

FONT_BLUE  = "0000FF"   # hardcoded inputs
FONT_BLACK = "000000"   # formulas

NUM_FMT_M     = '#,##0;(#,##0);"-"'
NUM_FMT_PCT   = '0%;(0%);"-"'
NUM_FMT_RATIO = '0.00'
NUM_FMT_DAYS  = '0'


def _side():   return Side(style="thin", color="BFBFBF")
def _border(): s=_side(); return Border(left=s,right=s,top=s,bottom=s)
def _thick_bottom():
    return Border(left=_side(), right=_side(), top=_side(),
                  bottom=Side(style="medium", color="1F3864"))
def _fill(c):  return PatternFill("solid", fgColor=c)
def _font(bold=False, color="000000", size=10, italic=False):
    return Font(name="Arial", bold=bold, color=color, size=size, italic=italic)
def _align(h="left", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


class ExcelWriter:
    """Writes analysis results with live Excel formulas."""

    COMPANY_NAME = "Sun Pharmaceutical industries Ltd (SUN.NS)"
    DATA_SOURCE  = "Source: Refinitiv Eikon & Company Annual report"
    UNIT_LABEL   = "Unit: As Mentioned"

    def __init__(self, output_path: str, years: list, company_name: str = None):
        self.output_path = Path(output_path)
        self.years = years
        self.wb = Workbook()
        self.wb.remove(self.wb.active)
        if company_name:
            self.COMPANY_NAME = company_name

    # ────────────────────────────────────────────────────────────────
    def write(self, altman_results, pnl_co_results, pnl_std_results):
        logger.info("Writing Excel with live formulas …")
        self._write_altman_sheet(altman_results)
        self._write_pnl_sheet("P&L CO Extract", pnl_co_results, "Consolidated Statement")
        self._write_pnl_sheet("P&L standalone Extract", pnl_std_results, "Standalone Statement")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(self.output_path)
        logger.info(f"Output saved to: {self.output_path}")

    # ════════════════════════════════════════════════════════════════
    # SHEET 1: ALTMAN Z SCORE
    # ════════════════════════════════════════════════════════════════

    def _write_altman_sheet(self, results):
        ws = self.wb.create_sheet("Altman Z Score")
        summary_df = results["summary"]
        zscore_df  = results["zscore_calc"]

        self._write_title_block(ws, 1)

        header_row = 5
        cols = ["Particulars", "Units"] + self.years
        self._write_header_row(ws, header_row, cols)

        data_start = header_row + 1
        row_idx = {}   # (Particulars, Units) → Excel row

        for i, row_data in summary_df.iterrows():
            row_idx[(row_data["Particulars"], row_data["Units"])] = data_start + i

        def col_for_year(yr): return 3 + self.years.index(yr)
        def cref(part, units, yr):
            r = row_idx.get((part, units))
            return f"{get_column_letter(col_for_year(yr))}{r}" if r else None

        for i, row_data in summary_df.iterrows():
            r = data_start + i
            part  = row_data["Particulars"]
            units = row_data["Units"]
            kind  = row_data["kind"]

            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, units)

            for yr in self.years:
                col = col_for_year(yr)
                cell = ws.cell(row=r, column=col)
                val, is_formula = self._altman_cell(part, units, kind, yr, row_data, cref)
                cell.value = val
                fmt = self._fmt_for_units(units)
                if fmt: cell.number_format = fmt
                cell.alignment = _align("right")
                cell.border    = _border()
                cell.font      = _font(color=(FONT_BLACK if is_formula else FONT_BLUE))
                if i % 2 == 0:
                    cell.fill = _fill(CLR_STRIPE)

        # Conditional formatting on Altman Z row
        z_r = row_idx.get(("Altman Z Score", "Ratio"))
        if z_r:
            sc = get_column_letter(col_for_year(self.years[0]))
            ec = get_column_letter(col_for_year(self.years[-1]))
            rng = f"{sc}{z_r}:{ec}{z_r}"
            ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["3"],    fill=_fill(CLR_GREEN)))
            ws.conditional_formatting.add(rng, CellIsRule(operator="between",     formula=["1.8","3"], fill=_fill(CLR_YELLOW)))
            ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan",    formula=["1.8"],  fill=_fill(CLR_RED)))

        # Z-score formula table
        last_row = data_start + len(summary_df) - 1
        sep_row  = last_row + 2
        self._write_section_header(ws, sep_row, "Altman Z-score Formula & Calculation", len(cols))

        zhdr = sep_row + 1
        zcols = ["Ratios", "Coefficient"] + self.years
        self._write_header_row(ws, zhdr, zcols, bg=CLR_HEADER_LIGHT, font_color="000000")

        for i, zr in zscore_df.iterrows():
            r = zhdr + 1 + i
            label = zr["Ratios"]
            lab_cell = ws.cell(row=r, column=1, value=label)
            lab_cell.border = _border()
            lab_cell.font   = _font(bold=True)

            coef_cell = ws.cell(row=r, column=2, value=zr.get("Coefficient"))
            coef_cell.border        = _border()
            coef_cell.number_format = NUM_FMT_RATIO
            coef_cell.alignment     = _align("center")
            coef_cell.font          = _font(color=FONT_BLUE)

            for yr in self.years:
                col = 3 + self.years.index(yr)
                cell = ws.cell(row=r, column=col)
                if label == "Working Capital / Total Assets":
                    cell.value = f"=IFERROR({cref('Working Capital','INR Million',yr)}/{cref('Total Assets','INR Million',yr)},0)"
                elif label == "Retained Earnings / Total Assets":
                    cell.value = f"=IFERROR({cref('Retained Earning','INR Million',yr)}/{cref('Total Assets','INR Million',yr)},0)"
                elif label == "EBIT / Total Assets":
                    cell.value = f"=IFERROR({cref('EBIT','INR Million',yr)}/{cref('Total Assets','INR Million',yr)},0)"
                elif label == "Market Value of Equity / Total Liabilities":
                    cell.value = f"=IFERROR({cref('Market Value','INR Million',yr)}/{cref('Total Liability','INR Million',yr)},0)"
                elif label == "Sales / Total Assets":
                    cell.value = f"=IFERROR({cref('Total Revenue','INR Million',yr)}/{cref('Total Assets','INR Million',yr)},0)"
                elif label == "Altman Z_Score":
                    z_top = zhdr + 1
                    contributions = [f"{get_column_letter(col)}{z_top+k}*$B${z_top+k}" for k in range(5)]
                    cell.value = f"=ROUND({'+'.join(contributions)},2)"
                cell.number_format = NUM_FMT_RATIO
                cell.alignment     = _align("right")
                cell.border        = _border()
                cell.font          = _font(color=FONT_BLACK)

        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 18
        for j in range(len(self.years)):
            ws.column_dimensions[get_column_letter(3+j)].width = 14
        ws.freeze_panes = f"C{header_row+1}"

    # ── Build one Altman cell ──

    def _altman_cell(self, part, units, kind, yr, row_data, cref):
        c_TR  = cref("Total Revenue",                  "INR Million", yr)
        c_EBI = cref("EBITDA",                          "INR Million", yr)
        c_PAT = cref("PAT",                             "INR Million", yr)
        c_TA  = cref("Total Assets",                    "INR Million", yr)
        c_TE  = cref("Total Equity",                    "INR Million", yr)
        c_CA  = cref("Current Assets",                  "INR Million", yr)
        c_CL  = cref("Current Liabilities",             "INR Million", yr)
        c_WC  = cref("Working Capital",                 "INR Million", yr)
        c_CFL = cref("Current Financial Liabilities",   "INR Million", yr)
        c_FC  = cref("Finance cost",                    "INR Million", yr)
        c_EBT = cref("EBIT",                            "INR Million", yr)
        c_DEP = cref("Depreciation & Amortisation",     "INR Million", yr)
        c_TL  = cref("Total Liability",                 "INR Million", yr)
        c_MV  = cref("Market Value",                    "INR Million", yr)
        c_OE  = cref("Other Equity (Includes Reserves)","INR Million", yr)
        c_RE  = cref("Retained Earning",                "INR Million", yr)
        c_CB  = cref("Current Borrowing",               "INR Million", yr)
        c_NCB = cref("Non Current Borrowing",           "INR Million", yr)

        idx = self.years.index(yr)
        prev_yr = self.years[idx-1] if idx > 0 else None   # years are ASC; prior year is to the left
        c_TR_p = cref("Total Revenue", "INR Million", prev_yr) if prev_yr else None
        c_TA_p = cref("Total Assets",  "INR Million", prev_yr) if prev_yr else None
        c_OE_p = cref("Other Equity (Includes Reserves)", "INR Million", prev_yr) if prev_yr else None

        val = row_data.get(yr)

        if kind == "value":
            return (val, False)
        if kind == "growth":
            if prev_yr and c_TR_p:
                return (f"=IFERROR(({c_TR}-{c_TR_p})/ABS({c_TR_p}),\"\")", True)
            return ("-", False)
        if kind == "ta_growth":
            if prev_yr and c_TA_p:
                return (f"=IFERROR(({c_TA}-{c_TA_p})/ABS({c_TA_p}),\"\")", True)
            return ("-", False)
        if kind == "ebitda_margin":  return (f"=IFERROR({c_EBI}/{c_TR},0)", True)
        if kind == "pat_margin":     return (f"=IFERROR({c_PAT}/{c_TR},0)", True)
        if kind == "dep_value":      return (val, False)   # D&A in INR Million (Altman Z input or P&L÷10)
        if kind == "ebit":
            # EBIT = EBITDA - D&A (both INR Million). This cell is referenced by zscore_calc X3 = EBIT / Total Assets
            if c_DEP:
                return (f"=IFERROR({c_EBI}-{c_DEP},0)", True)
            return (val, False)   # fallback if dep row missing
        if kind == "total_liability": return (f"=IFERROR({c_TA}-{c_TE},0)", True)
        if kind == "working_capital": return (f"=IFERROR({c_CA}-{c_CL},0)", True)
        if kind == "current_ratio":   return (f"=IFERROR({c_CA}/{c_CL},0)", True)
        if kind == "roe":             return (f"=IFERROR(ROUND({c_PAT}/{c_TE},2),0)", True)
        if kind == "dscr":            return (f"=IFERROR({c_PAT}/({c_CFL}+{c_FC}),0)", True)
        if kind == "book_value_debt": return (f"=IFERROR({c_CB}+{c_NCB},0)", True)
        if kind == "creditor_days":   return (val, False)
        if kind == "inventory_days":  return (val, False)
        if kind == "debtor_days":     return (val, False)
        if kind == "ccc":
            c_inv_d = cref("Inventory",              "Days", yr)
            c_deb_d = cref("Debtors (Receivables)",  "Days", yr)
            c_cre_d = cref("Creditors (Payables)",   "Days", yr)
            if c_inv_d and c_deb_d and c_cre_d:
                return (f"=IFERROR({c_inv_d}+{c_deb_d}-{c_cre_d},0)", True)
            return (val, False)
        if kind == "retained_earning":
            # Write the Python-computed RE value directly.
            # val = analyst RE (if entered) OR Other Equity (fallback only when RE not entered).
            # Do NOT reference c_OE here — that would always show OE regardless of RE input.
            return (val, False)
        if kind == "altman_z":
            return (
                f"=IFERROR(ROUND(1.2*({c_WC}/{c_TA})+1.4*({c_RE}/{c_TA})"
                f"+3.3*({c_EBT}/{c_TA})+0.6*({c_MV}/{c_TL})+1*({c_TR}/{c_TA}),2),0)",
                True
            )
        return (val, False)

    def _fmt_for_units(self, units):
        return {
            "INR Million": NUM_FMT_M,
            "% YoY":       NUM_FMT_PCT,
            "%":           NUM_FMT_PCT,
            "Ratio":       NUM_FMT_RATIO,
            "Days":        NUM_FMT_DAYS,
        }.get(units, None)

    # ════════════════════════════════════════════════════════════════
    # SHEETS 2 & 3: P&L
    # ════════════════════════════════════════════════════════════════

    INPUT_MILLION_ROWS = {
        "Cost of materials consumed","Purchases of stock-in-trade","Changes in inventories",
        "Employee benefit expenses","Finance costs","Depreciation & amortisation",
        "Other Expenses","Power, Fuel Electricity","Consumables","Cost transportation",
        "Rest in Other Expenses","Total Cost","Revenue from Ops","Total Income",
    }

    CRS_TO_MILLION = {
        "Raw Material Cost":           ["Cost of materials consumed","Purchases of stock-in-trade","Changes in inventories"],
        "Consumables":                 ["Consumables"],
        "Power & Fuel":                ["Power, Fuel Electricity"],
        "Transportation":              ["Cost transportation"],
        "Manpower":                    ["Employee benefit expenses"],
        "Rest in Other Expenses":      ["Rest in Other Expenses"],
        "Finance costs":               ["Finance costs"],
        "Depreciation & Amortization": ["Depreciation & amortisation"],
        "Remaining Expenses":          ["Remaining Expenses"],
        "Total Cost":                  ["Total Cost"],
        "Operational PBT":             ["Operational PBT"],
        "Revenue from Ops":            ["Revenue from Ops"],
        "Other Income":                ["Other Income"],
        "EBITDA":                      ["EBITDA"],
    }

    def _write_pnl_sheet(self, sheet_name, results, statement_label):
        ws = self.wb.create_sheet(sheet_name)
        self._write_title_block(ws, 1, extra_label=statement_label)

        pnl_cols = ["Particulars", "Units", "Last 5 Years"] + self.years
        title_row  = 5
        header_row = 6
        growth_col = len(pnl_cols) + 2

        # Growth title and headers
        ws.cell(row=title_row, column=growth_col, value="Growth Rate, YoY").font = _font(bold=True)
        for k, gh in enumerate(["CAGR"] + self.years):
            c = ws.cell(row=header_row, column=growth_col + k, value=gh)
            c.font = _font(bold=True, color=CLR_TITLE_FONT)
            c.fill = _fill(CLR_HEADER_MID)
            c.alignment = _align("center"); c.border = _border()

        self._write_header_row(ws, header_row, pnl_cols)
        current_row = header_row + 1

        direct_df = results["direct"]
        crs_df    = results["inr_crs"]
        pct_tc_df = results["pct_total_cost"]
        pct_or_df = results["pct_ops_rev"]
        summ_df   = results["pct_ops_summary"]

        # Years run left→right oldest→newest (e.g. FY20=D … FY25=I for 6 years)
        # "Last 5 Years" covers the 5 rightmost (most recent) year columns
        _n = len(self.years)
        L5_END   = get_column_letter(3 + _n)           # newest year column
        L5_START = get_column_letter(3 + max(_n - 4, 1))  # 5th-newest year column

        # ── Section 1: INR Million ──
        current_row = self._write_section_header(ws, current_row, "INR Million (Direct Financial Outputs)", len(pnl_cols))
        million_row_idx = {}
        sec_start = current_row
        for i, row in direct_df.iterrows():
            r = current_row + i
            part = row["Particulars"]
            million_row_idx[part] = r
            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, "INR Million")

            # Last 5 Years = SUM(FY25..FY21)
            l5 = ws.cell(row=r, column=3, value=f"=SUM({L5_START}{r}:{L5_END}{r})")
            l5.number_format = NUM_FMT_M
            l5.alignment = _align("right"); l5.border = _border()
            l5.font = _font(color=FONT_BLACK)

            is_input = part in self.INPUT_MILLION_ROWS
            for j, yr in enumerate(self.years):
                col = 4 + j
                cl  = get_column_letter(col)
                cell = ws.cell(row=r, column=col)
                v = row.get(yr)
                if is_input:
                    cell.value = v
                    cell.font  = _font(color=FONT_BLUE)
                else:
                    f = self._derived_million_formula(part, cl, million_row_idx)
                    if f:
                        cell.value = f
                        cell.font  = _font(color=FONT_BLACK)
                    else:
                        cell.value = v
                        cell.font  = _font(color=FONT_BLUE)
                cell.number_format = NUM_FMT_M
                cell.alignment = _align("right"); cell.border = _border()
                if i % 2 == 0:
                    cell.fill = _fill(CLR_STRIPE)
        current_row = sec_start + len(direct_df) + 1

        # ── Section 2: INR Crs ──
        current_row = self._write_section_header(ws, current_row, "INR Crores (Cost Breakdown)", len(pnl_cols))
        sec_start = current_row
        for i, row in crs_df.iterrows():
            r = current_row + i
            part = row["Particulars"]
            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, "INR Crs")

            l5 = ws.cell(row=r, column=3, value=f"=SUM({L5_START}{r}:{L5_END}{r})")
            l5.number_format = NUM_FMT_M
            l5.alignment = _align("right"); l5.border = _border()
            l5.font = _font(color=FONT_BLACK)

            sources = self.CRS_TO_MILLION.get(part, [])
            for j, yr in enumerate(self.years):
                col = 4 + j; cl = get_column_letter(col)
                cell = ws.cell(row=r, column=col)
                refs = [f"{cl}{million_row_idx[s]}" for s in sources if s in million_row_idx]
                if refs:
                    cell.value = f"=({'+'.join(refs)})/10"
                cell.number_format = NUM_FMT_M
                cell.alignment = _align("right"); cell.border = _border()
                cell.font = _font(color=FONT_BLACK)
                if i % 2 == 0:
                    cell.fill = _fill(CLR_STRIPE)

            # Growth columns (CAGR + YoY)
            # Years are ASC (oldest=col4, newest=last col) so:
            #   CAGR = (newest / oldest)^(1/n) - 1
            #   YoY  = (current - prior) / |prior|  where prior is one column to the LEFT
            oldest = get_column_letter(4)
            newest = get_column_letter(3 + len(self.years))
            n = len(self.years) - 1
            cagr_cell = ws.cell(row=r, column=growth_col,
                value=f"=IFERROR(({newest}{r}/{oldest}{r})^(1/{n})-1,\"\")")
            cagr_cell.number_format = NUM_FMT_PCT
            cagr_cell.alignment = _align("right"); cagr_cell.border = _border()
            cagr_cell.font = _font(color=FONT_BLACK)

            for k, yr in enumerate(self.years):
                gcell = ws.cell(row=r, column=growth_col + 1 + k)
                if k > 0:   # oldest year (k=0) has no prior year → leave blank
                    cc  = get_column_letter(4 + k)
                    pc  = get_column_letter(4 + k - 1)   # prior year is one column LEFT
                    gcell.value = f"=IFERROR(({cc}{r}-{pc}{r})/ABS({pc}{r}),\"\")"
                gcell.number_format = NUM_FMT_PCT
                gcell.alignment = _align("right"); gcell.border = _border()
                gcell.font = _font(color=FONT_BLACK)

        current_row = sec_start + len(crs_df) + 1

        # ── Section 3: % of Total Cost ──
        current_row = self._write_section_header(ws, current_row, "% of Total Cost", len(pnl_cols))
        sec_start = current_row
        tc_r = million_row_idx.get("Total Cost")
        for i, row in pct_tc_df.iterrows():
            r = current_row + i
            part = row["Particulars"]
            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, "% of Total Cost")
            self._write_pct_row(ws, r, part, million_row_idx, tc_r, L5_START, L5_END, "% of Total Cost", i)
        current_row = sec_start + len(pct_tc_df) + 1

        # ── Section 4: % of Ops Revenue ──
        current_row = self._write_section_header(ws, current_row, "% of Ops Revenue", len(pnl_cols))
        sec_start = current_row
        rev_r = million_row_idx.get("Revenue from Ops")
        for i, row in pct_or_df.iterrows():
            r = current_row + i
            part = row["Particulars"]
            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, "% of Ops Revenue")
            self._write_pct_row(ws, r, part, million_row_idx, rev_r, L5_START, L5_END, "% of Ops Revenue", i)
        current_row = sec_start + len(pct_or_df) + 1

        # ── Section 5: Summary % of Ops Revenue ──
        current_row = self._write_section_header(ws, current_row, "Summary % of Ops Revenue", len(pnl_cols))
        sec_start = current_row
        for i, row in summ_df.iterrows():
            r = current_row + i
            part = row["Particulars"]
            self._write_label_cell(ws, r, 1, part)
            self._write_label_cell(ws, r, 2, "% of Ops Revenue")

            for j, yr in enumerate(self.years):
                col = 4 + j; cl = get_column_letter(col)
                cell = ws.cell(row=r, column=col)
                num = self._summary_num(part, cl, million_row_idx)
                if num and rev_r:
                    cell.value = f"=IFERROR(({num})/{cl}{rev_r},0)"
                cell.number_format = NUM_FMT_PCT
                cell.alignment = _align("right"); cell.border = _border()
                cell.font = _font(color=FONT_BLACK)
                if i % 2 == 0:
                    cell.fill = _fill(CLR_STRIPE)

            l5 = ws.cell(row=r, column=3)
            num5 = self._summary_num_l5(part, million_row_idx, L5_START, L5_END)
            if num5 and rev_r:
                l5.value = f"=IFERROR(({num5})/SUM({L5_START}{rev_r}:{L5_END}{rev_r}),0)"
            l5.number_format = NUM_FMT_PCT
            l5.alignment = _align("right"); l5.border = _border()
            l5.font = _font(color=FONT_BLACK)

        # Column widths and freeze
        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 14
        for j in range(len(self.years)):
            ws.column_dimensions[get_column_letter(4+j)].width = 14
        for k in range(len(self.years) + 1):
            ws.column_dimensions[get_column_letter(growth_col + k)].width = 13
        ws.freeze_panes = f"D{header_row+1}"

    # ── Helpers ─────────────────────────────────────────────────────

    def _derived_million_formula(self, part, cl, mi):
        """Return formula for computed rows in Million section."""
        r_tc  = mi.get("Total Cost"); r_rev = mi.get("Revenue from Ops")
        r_ti  = mi.get("Total Income"); r_fc = mi.get("Finance costs")
        r_dep = mi.get("Depreciation & amortisation"); r_pbt = mi.get("Operational PBT")
        r_mat = mi.get("Cost of materials consumed"); r_pur = mi.get("Purchases of stock-in-trade")
        r_chg = mi.get("Changes in inventories"); r_emp = mi.get("Employee benefit expenses")
        r_oe  = mi.get("Other Expenses")

        if part == "Operational PBT" and r_rev and r_tc:
            return f"={cl}{r_rev}-{cl}{r_tc}"
        if part == "Other Income" and r_ti and r_rev:
            return f"={cl}{r_ti}-{cl}{r_rev}"
        if part == "EBITDA" and r_pbt and r_dep and r_fc:
            return f"={cl}{r_pbt}+{cl}{r_dep}+{cl}{r_fc}"
        if part == "Remaining Expenses" and all([r_tc, r_mat, r_pur, r_chg, r_emp, r_fc, r_dep, r_oe]):
            return (f"=IFERROR(MAX(0,{cl}{r_tc}-{cl}{r_mat}-{cl}{r_pur}-{cl}{r_chg}"
                    f"-{cl}{r_emp}-{cl}{r_fc}-{cl}{r_dep}-{cl}{r_oe}),0)")
        return None

    def _src_million_for_pct(self, part):
        return {
            "Consumables":                 "Consumables",
            "Power & Fuel":                "Power, Fuel Electricity",
            "Transportation":              "Cost transportation",
            "Manpower":                    "Employee benefit expenses",
            "Rest in Other Expenses":      "Rest in Other Expenses",
            "Finance costs":               "Finance costs",
            "Depreciation & Amortization": "Depreciation & amortisation",
            "Remaining Expenses":          "Remaining Expenses",
            "Total Cost":                  "Total Cost",
            "Operational PBT":             "Operational PBT",
            "Revenue from Ops":            "Revenue from Ops",
            "Other Income":                "Other Income",
            "EBITDA":                      "EBITDA",
        }.get(part, "")

    def _write_pct_row(self, ws, r, part, mi, denom_r, L5_START, L5_END, units, stripe_idx):
        """Write one row of % of Total Cost or % of Ops Revenue section."""
        # Last 5 Years
        l5 = ws.cell(row=r, column=3)
        if part == "Raw Material Cost":
            mat = mi["Cost of materials consumed"]; pur = mi["Purchases of stock-in-trade"]; chg = mi["Changes in inventories"]
            l5.value = (f"=IFERROR((SUM({L5_START}{mat}:{L5_END}{mat})+SUM({L5_START}{pur}:{L5_END}{pur})"
                        f"+SUM({L5_START}{chg}:{L5_END}{chg}))/SUM({L5_START}{denom_r}:{L5_END}{denom_r}),0)")
        else:
            src = self._src_million_for_pct(part)
            src_r = mi.get(src)
            if src_r and denom_r:
                l5.value = f"=IFERROR(SUM({L5_START}{src_r}:{L5_END}{src_r})/SUM({L5_START}{denom_r}:{L5_END}{denom_r}),0)"
        l5.number_format = NUM_FMT_PCT
        l5.alignment = _align("right"); l5.border = _border()
        l5.font = _font(color=FONT_BLACK)

        for j, yr in enumerate(self.years):
            col = 4 + j; cl = get_column_letter(col)
            cell = ws.cell(row=r, column=col)
            if part == "Raw Material Cost":
                mat = mi["Cost of materials consumed"]; pur = mi["Purchases of stock-in-trade"]; chg = mi["Changes in inventories"]
                cell.value = f"=IFERROR(({cl}{mat}+{cl}{pur}+{cl}{chg})/{cl}{denom_r},0)"
            else:
                src = self._src_million_for_pct(part)
                src_r = mi.get(src)
                if src_r and denom_r:
                    cell.value = f"=IFERROR({cl}{src_r}/{cl}{denom_r},0)"
            cell.number_format = NUM_FMT_PCT
            cell.alignment = _align("right"); cell.border = _border()
            cell.font = _font(color=FONT_BLACK)
            if stripe_idx % 2 == 0:
                cell.fill = _fill(CLR_STRIPE)

    def _summary_num(self, part, cl, mi):
        if part == "PBT":
            r = mi.get("Operational PBT"); return f"{cl}{r}" if r else None
        if part == "Interest & Depreciation":
            r1, r2 = mi.get("Finance costs"), mi.get("Depreciation & amortisation")
            return f"{cl}{r1}+{cl}{r2}" if r1 and r2 else None
        if part == "RM":
            a,b,c = mi.get("Cost of materials consumed"), mi.get("Purchases of stock-in-trade"), mi.get("Changes in inventories")
            return f"{cl}{a}+{cl}{b}+{cl}{c}" if all([a,b,c]) else None
        if part == "Power-Fuel":
            r = mi.get("Power, Fuel Electricity"); return f"{cl}{r}" if r else None
        if part == "Manpower":
            r = mi.get("Employee benefit expenses"); return f"{cl}{r}" if r else None
        if part == "Transportation":
            r = mi.get("Cost transportation"); return f"{cl}{r}" if r else None
        if part == "Others":
            a,b,c = mi.get("Rest in Other Expenses"), mi.get("Consumables"), mi.get("Remaining Expenses")
            return f"{cl}{a}+{cl}{b}+{cl}{c}" if all([a,b,c]) else None
        if part == "Revenue":
            r = mi.get("Revenue from Ops"); return f"{cl}{r}" if r else None
        return None

    def _summary_num_l5(self, part, mi, L5_START, L5_END):
        def sr(name):
            r = mi.get(name); return f"SUM({L5_START}{r}:{L5_END}{r})" if r else None
        if part == "PBT": return sr("Operational PBT")
        if part == "Interest & Depreciation":
            a, b = sr("Finance costs"), sr("Depreciation & amortisation")
            return f"{a}+{b}" if a and b else None
        if part == "RM":
            a, b, c = sr("Cost of materials consumed"), sr("Purchases of stock-in-trade"), sr("Changes in inventories")
            return f"{a}+{b}+{c}" if all([a,b,c]) else None
        if part == "Power-Fuel":    return sr("Power, Fuel Electricity")
        if part == "Manpower":      return sr("Employee benefit expenses")
        if part == "Transportation":return sr("Cost transportation")
        if part == "Others":
            a,b,c = sr("Rest in Other Expenses"), sr("Consumables"), sr("Remaining Expenses")
            return f"{a}+{b}+{c}" if all([a,b,c]) else None
        if part == "Revenue":       return sr("Revenue from Ops")
        return None

    # ── Common helpers ──────────────────────────────────────────────

    def _write_title_block(self, ws, row_start, extra_label=""):
        titles = [
            (self.COMPANY_NAME, True, 11),
            (self.UNIT_LABEL,   False, 10),
            (self.DATA_SOURCE,  False, 10),
        ]
        if extra_label:
            titles.append((extra_label, True, 10))
        for offset, (text, bold, size) in enumerate(titles):
            c = ws.cell(row=row_start + offset, column=1, value=text)
            c.font = _font(bold=bold, size=size)

    def _write_header_row(self, ws, row, cols, bg=None, font_color=None):
        bg_hex = bg or CLR_HEADER_MID
        fc_hex = font_color or CLR_TITLE_FONT
        for j, n in enumerate(cols):
            c = ws.cell(row=row, column=1+j, value=n)
            c.font      = _font(bold=True, color=fc_hex)
            c.fill      = _fill(bg_hex)
            c.alignment = _align("center", wrap=True)
            c.border    = _thick_bottom()
        ws.row_dimensions[row].height = 22

    def _write_section_header(self, ws, row, label, n_cols):
        c = ws.cell(row=row, column=1, value=label)
        c.font      = _font(bold=True, color=CLR_TITLE_FONT)
        c.fill      = _fill(CLR_HEADER_DARK)
        c.alignment = _align("left")
        c.border    = _thick_bottom()
        for j in range(1, n_cols):
            cc = ws.cell(row=row, column=1+j)
            cc.fill = _fill(CLR_HEADER_DARK); cc.border = _thick_bottom()
        ws.row_dimensions[row].height = 18
        return row + 1

    def _write_label_cell(self, ws, row, col, value):
        c = ws.cell(row=row, column=col, value=value)
        c.font      = _font(bold=(col == 1))
        c.alignment = _align("left")
        c.border    = _border()
        return c
