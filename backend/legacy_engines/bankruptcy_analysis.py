"""
bankruptcy_analysis.py
Altman Z Score + financial health ratios.

This module returns BOTH:
  - Pre-computed values (for validation / debug)
  - A list of row definitions that the Excel writer uses to emit FORMULAS

FORMULAS:
  EBIT = EBITDA - Depreciation & Amortisation
        Both in INR Million. D&A source: Altman Z input preferred; P&L (Crores ÷ 10) fallback.
        EBIT is used for X3 component: X3 = EBIT / Total Assets
  Working Capital   = Current Assets - Current Liabilities
  Current Ratio     = Current Assets / Current Liabilities
  ROE               = ROUND(PAT / Net Worth, 2)
  EBITDA Margin     = EBITDA / Total Revenue
  PAT Margin        = PAT / Total Revenue
  Total Liability   = Total Assets - Net Worth
  Book Value of Debt= Short-Term Borrowings + Long-Term Debt
  DSCR              = PAT / (Current Financial Liabilities + Finance Cost)
  Creditor Days     = Trade Payables * 365 / RM Cost (fallback: CMC+PSIT when ΔInv makes RM ≤ 0)
  Inventory Days    = Inventory * 365 / RM_Cost
  Debtor Days       = Debtors * 365 / Revenue_from_Ops
  CCC               = Inv_Days + Debtor_Days - Creditor_Days
  X2 Retained Earning:
    Priority 1: Direct "Retained Earnings" row from Altman Z category
    Priority 2: Other Equity (Includes Reserves) used DIRECTLY (NOT delta)
  X3: EBIT used directly (not EBITDA)
  Altman Z          = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
"""

import pandas as pd
from input_processor import InputProcessor
from engine_utils import setup_logger, safe_div, yoy_growth

logger = setup_logger("bankruptcy")
G = InputProcessor.get_val

W1, W2, W3, W4, W5 = 1.2, 1.4, 3.3, 0.6, 1.0


# Row definitions used by both engine (for value computation) and Excel writer (for formula emission)
ALTMAN_ROWS = [
    # (display_name,                        units,           kind)
    ("Total Revenue",                       "INR Million",   "value"),
    ("Revenue Growth",                      "% YoY",         "growth"),
    ("EBITDA",                              "INR Million",   "value"),
    ("EBITDA Margin",                       "%",             "ebitda_margin"),
    ("Depreciation & Amortisation",         "INR Million",   "dep_value"),
    ("EBIT",                                "INR Million",   "ebit"),
    ("PAT",                                 "INR Million",   "value"),
    ("PAT Margin",                          "%",             "pat_margin"),
    ("Total Assets",                        "INR Million",   "value"),
    ("Total Equity",                        "INR Million",   "value"),
    ("Total Liability",                     "INR Million",   "total_liability"),
    ("Total Assets Growth",                 "% YoY",         "ta_growth"),
    ("Current Assets",                      "INR Million",   "value"),
    ("Current Liabilities",                 "INR Million",   "value"),
    ("Working Capital",                     "INR Million",   "working_capital"),
    ("Current Ratio",                       "Ratio",         "current_ratio"),
    ("ROE",                                 "Ratio",         "roe"),
    ("Current Financial Liabilities",       "INR Million",   "value"),
    ("Finance cost",                        "INR Million",   "value"),
    ("DSCR - On Interest Basis",            "Ratio",         "dscr"),
    ("Trade Receivables",                   "INR Million",   "value"),
    ("Trade Payables",                      "INR Million",   "value"),
    ("Inventory",                           "INR Million",   "value"),
    ("Cash Conversion Cycle",               "Days",          "ccc"),
    ("Creditors (Payables)",                "Days",          "creditor_days"),
    ("Inventory",                           "Days",          "inventory_days"),
    ("Debtors (Receivables)",               "Days",          "debtor_days"),
    ("Other Equity (Includes Reserves)",    "INR Million",   "value"),
    ("Retained Earning",                    "INR Million",   "retained_earning"),
    ("Current Borrowing",                   "INR Million",   "value"),
    ("Non Current Liability",               "INR Million",   "value"),
    ("Market Value",                        "INR Million",   "value"),
    ("Altman Z Score",                      "Ratio",         "altman_z"),
]


class BankruptcyAnalysis:

    def __init__(self, df_altman: pd.DataFrame, df_pnl: pd.DataFrame, years: list,
                 re_overrides: dict = None):
        """
        re_overrides: {period_label: float} — analyst-entered Retained Earnings from
                      SQLite staging, keyed by year string (e.g. {"FY25": 578618.0}).
                      Takes priority over warehouse RE and OE fallback for X2.
        """
        self.df           = df_altman
        self.pnl          = df_pnl
        self.years        = years
        self.re_overrides = re_overrides or {}

    def _a(self, row, yr, default=None):
        return G(self.df, row, yr, default)

    def _p(self, row, yr, default=None):
        return G(self.pnl, row, yr, default)

    def _other_equity(self, yr):
        return G(self.df, "Other Equity (Includes Reserves)", yr)

    def _ebit(self, yr):
        ebitda = self._a("EBITDA", yr, 0) or 0
        # Prefer D&A from Altman Z input (INR Million) — no unit conversion needed
        dep = self._a("Depreciation and Amortisation", yr)
        if dep is None:
            # Fallback: P&L Depreciation is in INR Crores → divide by 10
            dep = (self._p("Depreciation & amortisation", yr, 0) or 0) / 10
        return round(ebitda - dep, 2)

    def _rm_cost(self, yr):
        return ((self._p("Cost of materials consumed", yr, 0) or 0)
                + (self._p("Purchases of stock-in-trade", yr, 0) or 0)
                + (self._p("Changes in inventories", yr, 0) or 0))

    def _get_input_value(self, display_name: str, yr: str):
        """
        Resolve the input value for an Altman row, used when kind='value'.
        Maps display name → actual altman input row name.
        """
        m = {
            "Total Revenue":               "Revenue from Operations",
            "EBITDA":                      "EBITDA",
            "PAT":                         "PAT",
            "Total Assets":                "Total Assets",
            "Total Equity":                "Net Worth",
            "Current Assets":              "Current Assets",
            "Current Liabilities":         "Current Liabilities",
            "Current Financial Liabilities": "Short Term Borrowings",
            "Finance cost":                "Finance costs",
            "Trade Receivables":           "Debtors (Receivables)",
            "Trade Payables":              "Creditors (Payables)",
            "Inventory":                   "Inventory",
            "Other Equity (Includes Reserves)": "Other Equity (Includes Reserves)",
            "Current Borrowing":           "Short Term Borrowings",
            "Non Current Borrowing":       "Long Term Debt",
            "Non Current Liability":       "Non Current Liability",
            "Market Value":                "Market Capitalization",
        }
        src_row = m.get(display_name)
        if src_row is None:
            return None
        return self._a(src_row, yr)

    # ── Public ───────────────────────────────────────────────────────

    def run(self) -> dict:
        logger.info("Running bankruptcy/Altman Z analysis …")
        # Compute numeric values (for verification only — writer emits formulas)
        summary = self._build_summary()
        zscore_calc = self._build_zscore_table(summary)
        return {"summary": summary, "zscore_calc": zscore_calc, "row_defs": ALTMAN_ROWS}

    def _build_summary(self) -> pd.DataFrame:
        # Key includes units so duplicate display names (e.g. "Inventory" appears
        # in both "INR Million" and "Days" rows) don't overwrite each other.
        data = {(p, u, y): None for p, u, k in ALTMAN_ROWS for y in self.years}

        for j, yr in enumerate(self.years):
            prev_yr = self.years[j+1] if j+1 < len(self.years) else None

            rev    = self._a("Revenue from Operations", yr)
            ebitda = self._a("EBITDA", yr)
            pat    = self._a("PAT", yr)
            ta     = self._a("Total Assets", yr)
            ca     = self._a("Current Assets", yr)
            cl     = self._a("Current Liabilities", yr)
            eq     = self._a("Net Worth", yr)
            stb    = self._a("Short Term Borrowings", yr, 0) or 0
            fc     = self._a("Finance costs", yr, 0) or 0
            rec_   = self._a("Debtors (Receivables)", yr)
            pay    = self._a("Creditors (Payables)", yr)
            inv    = self._a("Inventory", yr)
            mktcap = self._a("Market Capitalization", yr)
            oth_eq = self._other_equity(yr)
            rev_ops = self._p("Revenue from Ops", yr)
            dep_altman = self._a("Depreciation and Amortisation", yr)
            if dep_altman is not None:
                dep = dep_altman   # already INR Million
            else:
                dep = (self._p("Depreciation & amortisation", yr, 0) or 0) / 10

            ebit  = self._ebit(yr)
            tl    = (ta - eq) if (ta and eq) else None
            wc    = (ca - cl) if (ca and cl) else None
            rm    = self._rm_cost(yr)
            # Creditor Days denominator = net material cost (what generates trade payables).
            # If a large inventory build-up makes ΔInv large-negative so that rm ≤ 0,
            # fall back to (CMC + PSIT) without the volatile inventory-change component.
            cmc_pnl  = self._p("Cost of materials consumed",  yr, 0) or 0
            psit_pnl = self._p("Purchases of stock-in-trade", yr, 0) or 0
            cred_denom = rm if rm > 0 else (cmc_pnl + psit_pnl if (cmc_pnl + psit_pnl) > 0 else None)

            cred_days = safe_div((pay or 0) * 365, cred_denom) if cred_denom else None
            inv_days  = safe_div((inv or 0) * 365, rm) if rm else None
            deb_days  = safe_div((rec_ or 0) * 365, rev_ops) if rev_ops else None
            ccc       = ((inv_days or 0) + (deb_days or 0) - (cred_days or 0)
                         if (inv_days and deb_days and cred_days is not None) else None)

            # X2: Retained Earning — three-tier priority
            # Priority 1: SQLite staging override (analyst typed RE in Data Input, not yet Analyzed)
            # Priority 2: direct "Retained Earnings" row from Altman Z warehouse
            # Priority 3: Other Equity (Includes Reserves) used DIRECTLY — only if RE not entered
            re_staging_val = self.re_overrides.get(yr)
            re_direct      = self._a("Retained Earnings", yr)
            if re_staging_val is not None:
                re = re_staging_val   # analyst-entered RE from SQLite staging
            elif re_direct is not None:
                re = re_direct        # RE already in warehouse
            elif oth_eq is not None:
                re = oth_eq           # OE fallback — only when RE not entered at all
            else:
                re = None

            # DSCR = PAT / (CFL + Finance Cost)
            dscr_denom = (stb or 0) + (fc or 0)
            dscr = safe_div(pat, dscr_denom)

            # Altman Z
            z_score = None
            if all(v is not None for v in [wc, ta, re, ebit, mktcap, tl, rev]):
                x1 = safe_div(wc, ta)
                x2 = safe_div(re, ta)
                x3 = safe_div(ebit, ta)
                x4 = safe_div(mktcap, tl)
                x5 = safe_div(rev, ta)
                if all(v is not None for v in [x1, x2, x3, x4, x5]):
                    z_score = round(W1*x1 + W2*x2 + W3*x3 + W4*x4 + W5*x5, 2)

            roe_val = safe_div(pat, eq)
            # vals_map covers non-duplicate rows; duplicate "Inventory" is handled below
            vals_map = {
                "Total Revenue":              rev,
                "Revenue Growth":             yoy_growth(rev, self._a("Revenue from Operations", prev_yr)) if prev_yr else None,
                "EBITDA":                     ebitda,
                "EBITDA Margin":              safe_div(ebitda, rev),
                "Depreciation & Amortisation": round(dep, 2),
                "EBIT":                       ebit,
                "PAT":                        pat,
                "PAT Margin":                 safe_div(pat, rev),
                "Total Assets":               ta,
                "Total Equity":               eq,
                "Total Liability":            tl,
                "Total Assets Growth":        yoy_growth(ta, self._a("Total Assets", prev_yr)) if prev_yr else None,
                "Current Assets":             ca,
                "Current Liabilities":        cl,
                "Working Capital":            wc,
                "Current Ratio":              safe_div(ca, cl),
                "ROE":                        round(roe_val, 2) if roe_val is not None else None,
                "Current Financial Liabilities": stb,
                "Finance cost":               fc,
                "DSCR - On Interest Basis":   dscr,
                "Trade Receivables":          rec_,
                "Trade Payables":             pay,
                "Cash Conversion Cycle":      ccc,
                "Creditors (Payables)":       cred_days,
                "Debtors (Receivables)":      deb_days,
                "Other Equity (Includes Reserves)": oth_eq,
                "Retained Earning":           re,
                "Current Borrowing":          stb,
                "Non Current Liability":      self._a("Non Current Liability", yr),
                "Market Value":               mktcap,
                "Altman Z Score":             z_score,
            }

            for p, u, _ in ALTMAN_ROWS:
                if p == "Inventory":
                    # "Inventory" appears twice: once as INR Million (actual value),
                    # once as Days (calculated). Key by (p, u, yr) to keep them separate.
                    data[(p, u, yr)] = inv_days if u == "Days" else inv
                else:
                    data[(p, u, yr)] = vals_map.get(p)

        records = []
        for part, units, kind in ALTMAN_ROWS:
            rec = {"Particulars": part, "Units": units, "kind": kind}
            for yr in self.years:
                rec[yr] = data[(part, units, yr)]
            records.append(rec)
        return pd.DataFrame(records)

    def _build_zscore_table(self, summary_df: pd.DataFrame) -> pd.DataFrame:
        def g(row, units=None):
            s = summary_df[summary_df["Particulars"] == row]
            if units:
                s = s[s["Units"] == units]
            return s.iloc[0].to_dict() if not s.empty else {}

        z_r  = g("Altman Z Score")
        wc_r = g("Working Capital")
        ta_r = g("Total Assets")
        re_r = g("Retained Earning")
        eb_r = g("EBIT")
        mv_r = g("Market Value")
        tl_r = g("Total Liability")
        rv_r = g("Total Revenue")

        rows = [
            ("Working Capital / Total Assets",          1.2),
            ("Retained Earnings / Total Assets",         1.4),
            ("EBIT / Total Assets",                      3.3),
            ("Market Value of Equity / Total Liabilities", 0.6),
            ("Sales / Total Assets",                     1.0),
            ("Altman Z_Score",                           None),
        ]
        records = []
        for label, coef in rows:
            rec = {"Ratios": label, "Coefficient": coef}
            for yr in self.years:
                ta = ta_r.get(yr); tl = tl_r.get(yr)
                if label == "Working Capital / Total Assets":
                    rec[yr] = round(safe_div(wc_r.get(yr), ta) or 0, 2)
                elif label == "Retained Earnings / Total Assets":
                    rec[yr] = round(safe_div(re_r.get(yr), ta) or 0, 2)
                elif label == "EBIT / Total Assets":
                    rec[yr] = round(safe_div(eb_r.get(yr), ta) or 0, 2)
                elif label == "Market Value of Equity / Total Liabilities":
                    rec[yr] = round(safe_div(mv_r.get(yr), tl) or 0, 2)
                elif label == "Sales / Total Assets":
                    rec[yr] = round(safe_div(rv_r.get(yr), ta) or 0, 2)
                else:
                    rec[yr] = z_r.get(yr)
            records.append(rec)
        return pd.DataFrame(records)

    @staticmethod
    def z_category(z) -> str:
        if z is None: return "N/A"
        return "Safe" if z > 3 else ("Grey Zone" if z >= 1.8 else "Distress")
