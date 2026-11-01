"""
cost_structure_analysis.py
All P&L cost structure analytics.

FORMULA REFERENCE (reverse-engineered from expected workbook):
  Other Income     = Total Income - Revenue from Ops
  Operational PBT  = Revenue from Ops - Total Cost
  EBITDA           = Operational PBT + Depreciation & amortisation + Finance costs
  Remaining Expenses = Total Cost - (Mat + Purchases + Changes + Employee + Finance + Dep + OtherExp)
  Raw Material Cost (Crs) = (Cost of materials + Purchases of stock-in-trade + Changes in inventories) / 10
  INR Crs table   = INR Million / 10
  % of Total Cost  = line / Total Cost
  % of Ops Revenue = line / Revenue from Ops
  CAGR             = (FY25/FY20)^(1/5) - 1   (5-period over 6 data points)
  YoY              = (current - prev) / |prev|
"""

import math
import pandas as pd
from input_processor import InputProcessor
from engine_utils import setup_logger, safe_div, cagr, yoy_growth

logger = setup_logger("cost_structure")
G = InputProcessor.get_val


class CostStructureAnalysis:

    def __init__(self, df: pd.DataFrame, years: list):
        self.df    = df
        self.years = years   # e.g. ["FY25","FY24","FY23","FY22","FY21","FY20"]
        self._computed: dict = {}

    # ── Public ───────────────────────────────────────────────────────────

    def run(self) -> dict:
        logger.info("Running cost structure analysis …")
        self._build_direct_outputs()
        self._build_inr_crs()
        self._build_pct_total_cost()
        self._build_pct_ops_revenue()
        self._build_pct_ops_revenue_summary()
        self._build_growth_rates()
        logger.info("Cost structure analysis complete.")
        return self._computed

    # ── Row accessors ─────────────────────────────────────────────────

    def _v(self, row: str, yr: str, default=0.0):
        val = G(self.df, row, yr)
        return val if val is not None else default

    def _other_income(self, yr):
        return self._v("Total Income", yr) - self._v("Revenue from Ops", yr)

    def _total_cost(self, yr) -> float:
        """Return Total Cost for the year.

        Prefers the explicit "Total Cost" warehouse row. When that row is absent
        (analyst entered individual line items but no total), synthesizes from the
        same major categories that _remaining_expenses subtracts — preventing the
        Operational PBT segment from incorrectly claiming 100 % of revenue.
        """
        tc = G(self.df, "Total Cost", yr)
        if tc is not None:
            try:
                f = float(tc)
                if not math.isnan(f) and f > 0:
                    return f
            except (TypeError, ValueError):
                pass
        # Synthesize from individual P&L cost items
        synth = (
            self._v("Cost of materials consumed", yr)
            + self._v("Purchases of stock-in-trade", yr)
            + self._v("Changes in inventories", yr)
            + self._v("Employee benefit expenses", yr)
            + self._v("Finance costs", yr)
            + self._v("Depreciation & amortisation", yr)
            + self._v("Other Expenses", yr)
        )
        return max(0.0, synth)

    def _operational_pbt(self, yr):
        return self._v("Revenue from Ops", yr) - self._total_cost(yr)

    def _ebitda(self, yr):
        return (self._operational_pbt(yr)
                + self._v("Depreciation & amortisation", yr)
                + self._v("Finance costs", yr))

    def _remaining_expenses(self, yr):
        """
        Remaining = Total Cost - tracked major P&L categories.

        Uses _total_cost() so that companies without an explicit "Total Cost" row
        still get a correct (near-zero) remainder rather than a negative that
        clamps to zero while Operational PBT silently absorbs 100 % of revenue.

        Clamped to 0 to absorb floating-point noise when all items sum
        precisely to Total Cost.
        """
        remaining = (
            self._total_cost(yr)
            - self._v("Cost of materials consumed", yr)
            - self._v("Purchases of stock-in-trade", yr)
            - self._v("Changes in inventories", yr)
            - self._v("Employee benefit expenses", yr)
            - self._v("Finance costs", yr)
            - self._v("Depreciation & amortisation", yr)
            - self._v("Other Expenses", yr)
        )
        return max(0.0, remaining)

    def _raw_material_cost(self, yr):
        """RM = Cost of materials + Purchases + Changes in inventories."""
        return (self._v("Cost of materials consumed", yr)
                + self._v("Purchases of stock-in-trade", yr)
                + self._v("Changes in inventories", yr))

    # ── Step 1: Direct Financial Outputs (INR Million) ────────────────

    def _build_direct_outputs(self):
        rows = [
            "Cost of materials consumed",
            "Purchases of stock-in-trade",
            "Changes in inventories",
            "Employee benefit expenses",
            "Finance costs",
            "Depreciation & amortisation",
            "Other Expenses",
            "Power, Fuel Electricity",
            "Consumables",
            "Cost transportation",
            "Rest in Other Expenses",
            "Remaining Expenses",
            "Total Cost",
            "Operational PBT",
            "Revenue from Ops",
            "Total Income",
            "Other Income",
            "EBITDA",
        ]

        records = []
        last5 = self.years[:5]

        for row in rows:
            rec = {"Particulars": row, "Units": "INR Million"}
            for yr in self.years:
                if row == "Operational PBT":
                    rec[yr] = self._operational_pbt(yr)
                elif row == "Total Cost":
                    # Use _total_cost() so synthesized value propagates to the lookup
                    # dict used by _compute_cost_trend_sync (prevents 100 % PBT bug).
                    rec[yr] = self._total_cost(yr)
                elif row == "Other Income":
                    rec[yr] = self._other_income(yr)
                elif row == "EBITDA":
                    rec[yr] = self._ebitda(yr)
                elif row == "Remaining Expenses":
                    rec[yr] = self._remaining_expenses(yr)
                else:
                    rec[yr] = self._v(row, yr)

            rec["Last 5 Years"] = sum(rec[y] or 0 for y in last5)
            records.append(rec)

        self._computed["direct"] = pd.DataFrame(records)

    # ── Step 2: INR Crores ────────────────────────────────────────────

    # Map: output row → source function
    # NOTE: Raw Material Cost = Mat + Purchases + Changes (NOT just mat)
    CRS_ROWS = [
        "Raw Material Cost",
        "Consumables",
        "Power & Fuel",
        "Transportation",
        "Manpower",
        "Rest in Other Expenses",
        "Finance costs",
        "Depreciation & Amortization",
        "Remaining Expenses",
        "Total Cost",
        "Operational PBT",
        "Revenue from Ops",
        "Other Income",
        "EBITDA",
    ]

    def _get_src_val(self, crs_row: str, yr: str) -> float:
        """Get source INR Million value for a CRS output row."""
        m = {
            "Raw Material Cost":          self._raw_material_cost(yr),
            "Consumables":                self._v("Consumables", yr),
            "Power & Fuel":               self._v("Power, Fuel Electricity", yr),
            "Transportation":             self._v("Cost transportation", yr),
            "Manpower":                   self._v("Employee benefit expenses", yr),
            "Rest in Other Expenses":     self._v("Rest in Other Expenses", yr),
            "Finance costs":              self._v("Finance costs", yr),
            "Depreciation & Amortization": self._v("Depreciation & amortisation", yr),
            "Remaining Expenses":         self._remaining_expenses(yr),
            "Total Cost":                 self._v("Total Cost", yr),
            "Operational PBT":            self._operational_pbt(yr),
            "Revenue from Ops":           self._v("Revenue from Ops", yr),
            "Other Income":               self._other_income(yr),
            "EBITDA":                     self._ebitda(yr),
        }
        return m.get(crs_row, 0.0)

    def _build_inr_crs(self):
        records = []
        last5 = self.years[:5]
        for row in self.CRS_ROWS:
            rec = {"Particulars": row, "Units": "INR Crs"}
            for yr in self.years:
                v = self._get_src_val(row, yr)
                rec[yr] = v / 10 if v is not None else None
            rec["Last 5 Years"] = sum((rec[y] or 0) for y in last5)
            records.append(rec)
        self._computed["inr_crs"] = pd.DataFrame(records)

    # ── Step 3: % of Total Cost ───────────────────────────────────────

    def _build_pct_total_cost(self):
        records = []
        last5 = self.years[:5]
        for row in self.CRS_ROWS:
            rec = {"Particulars": row, "Units": "% of Total Cost"}
            last5_tc  = sum(self._v("Total Cost", y) for y in last5) or None
            last5_val = sum(self._get_src_val(row, y) for y in last5)
            rec["Last 5 Years"] = safe_div(last5_val, last5_tc)
            for yr in self.years:
                tc  = self._v("Total Cost", yr)
                val = self._get_src_val(row, yr)
                rec[yr] = safe_div(val, tc)
            records.append(rec)
        self._computed["pct_total_cost"] = pd.DataFrame(records)

    # ── Step 4: % of Ops Revenue ──────────────────────────────────────

    def _build_pct_ops_revenue(self):
        records = []
        last5 = self.years[:5]
        for row in self.CRS_ROWS:
            rec = {"Particulars": row, "Units": "% of Ops Revenue"}
            last5_rev = sum(self._v("Revenue from Ops", y) for y in last5) or None
            last5_val = sum(self._get_src_val(row, y) for y in last5)
            rec["Last 5 Years"] = safe_div(last5_val, last5_rev)
            for yr in self.years:
                rev = self._v("Revenue from Ops", yr)
                val = self._get_src_val(row, yr)
                rec[yr] = safe_div(val, rev)
            records.append(rec)
        self._computed["pct_ops_rev"] = pd.DataFrame(records)

    # ── Step 5: Summary % of Ops Revenue ─────────────────────────────

    def _get_summary_val(self, summ_row: str, yr: str) -> float:
        if summ_row == "PBT":
            return self._operational_pbt(yr)
        elif summ_row == "Interest & Depreciation":
            return self._v("Finance costs", yr) + self._v("Depreciation & amortisation", yr)
        elif summ_row == "RM":
            return self._raw_material_cost(yr)
        elif summ_row == "Power-Fuel":
            return self._v("Power, Fuel Electricity", yr)
        elif summ_row == "Manpower":
            return self._v("Employee benefit expenses", yr)
        elif summ_row == "Transportation":
            return self._v("Cost transportation", yr)
        elif summ_row == "Others":
            # Others = Rest in OtherExp + Consumables + Remaining
            return (self._v("Rest in Other Expenses", yr)
                    + self._v("Consumables", yr)
                    + self._remaining_expenses(yr))
        elif summ_row == "Revenue":
            return self._v("Revenue from Ops", yr)
        return 0.0

    SUMMARY_ROWS = ["PBT","Interest & Depreciation","RM","Power-Fuel",
                    "Manpower","Transportation","Others","Revenue"]

    def _build_pct_ops_revenue_summary(self):
        records = []
        last5 = self.years[:5]
        for row in self.SUMMARY_ROWS:
            rec = {"Particulars": row, "Units": "% of Ops Revenue"}
            last5_rev = sum(self._v("Revenue from Ops", y) for y in last5) or None
            last5_val = sum(self._get_summary_val(row, y) for y in last5)
            rec["Last 5 Years"] = safe_div(last5_val, last5_rev)
            for yr in self.years:
                rev = self._v("Revenue from Ops", yr)
                val = self._get_summary_val(row, yr)
                rec[yr] = safe_div(val, rev)
            records.append(rec)
        self._computed["pct_ops_summary"] = pd.DataFrame(records)

    # ── Step 6: Growth Rates ──────────────────────────────────────────

    def _build_growth_rates(self):
        """CAGR = (FY_newest / FY_oldest)^(1/n) - 1 where n = len(years)-1"""
        records = []
        for row in self.CRS_ROWS:
            rec = {"Particulars": row, "Units": "INR Crs"}

            vals = {}
            for yr in self.years:
                v = self._get_src_val(row, yr)
                vals[yr] = v / 10 if v is not None else None

            # CAGR: newest year / oldest year, n periods
            n = len(self.years) - 1
            newest = self.years[0]
            oldest = self.years[-1]
            rec["CAGR"] = cagr(vals.get(oldest), vals.get(newest), n)

            # YoY: each year vs previous (next in list = older)
            for i, yr in enumerate(self.years):
                if i + 1 < len(self.years):
                    prev_yr = self.years[i + 1]
                    rec[yr] = yoy_growth(vals.get(yr), vals.get(prev_yr))
                else:
                    rec[yr] = None  # oldest year has no prior

            records.append(rec)
        self._computed["growth"] = pd.DataFrame(records)
