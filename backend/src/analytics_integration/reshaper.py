"""
Reshapes warehouse data (long format) into the wide DataFrames that the
legacy cost-structure and bankruptcy engines expect (Particulars-indexed
with FY columns).
"""

from __future__ import annotations
import pandas as pd

from utils import get_logger
from retrieval import QueryEngine

logger = get_logger("reshaper")


# ── Reverse-map canonical names → labels used by legacy engines ─────
# The legacy engines (cost_structure_analysis.py, bankruptcy_analysis.py)
# were written before standardization, so their internal row names differ
# from the platform's canonical names. We bridge that here.

CANONICAL_TO_PNL_LABEL = {
    "Cost of Materials Consumed":   "Cost of materials consumed",
    "Purchases of Stock-in-Trade":  "Purchases of stock-in-trade",
    "Changes in Inventories":       "Changes in inventories",
    "Employee Benefit Expenses":    "Employee benefit expenses",
    "Finance Costs":                "Finance costs",
    "Depreciation and Amortisation":"Depreciation & amortisation",
    "Other Expenses":               "Other Expenses",
    "Power, Fuel and Electricity":  "Power, Fuel Electricity",
    "Consumables":                  "Consumables",
    "Transportation Cost":          "Cost transportation",
    "Rest in Other Expenses":       "Rest in Other Expenses",
    "Total Cost":                   "Total Cost",
    "Revenue from Operations":      "Revenue from Ops",
    "Total Income":                 "Total Income",
}

CANONICAL_TO_ALTMAN_LABEL = {
    "Revenue from Operations":      "Revenue from Operations",
    "EBITDA":                       "EBITDA",
    "Depreciation and Amortisation": "Depreciation and Amortisation",  # INR Million — EBIT = EBITDA - D&A
    "PAT":                          "PAT",
    "Total Assets":                 "Total Assets",
    "Current Assets":               "Current Assets",
    "Current Liabilities":          "Current Liabilities",
    "Short Term Borrowings":        "Short Term Borrowings",
    "Finance Costs":                "Finance costs",
    "Debtors (Receivables)":        "Debtors (Receivables)",
    "Creditors (Payables)":         "Creditors (Payables)",
    "Inventory":                    "Inventory",
    "Net Worth":                    "Net Worth",
    "Non Current Liability":        "Non Current Liability",
    "Long Term Debt":               "Long Term Debt",   # backward compat for older saved data
    "Market Capitalization":        "Market Capitalization",
    "Other Equity (Includes Reserves)": "Other Equity (Includes Reserves)",
}


class WarehouseReshaper:
    """Converts long-format warehouse data into wide DataFrames per category."""

    def __init__(self, engine: QueryEngine):
        self.engine = engine

    # ----------------------------------------------------------------

    def get_pnl_wide(self, company_id: str, category: str = "P&L Consolidated") -> tuple[pd.DataFrame, list]:
        try:
            df = self.engine.sql(
                f"SELECT financial_item, year, value, units, version "
                f"FROM financials "
                f"WHERE company_id = '{company_id}' "
                f"  AND financial_category = '{category}' "
                f"  AND is_active = TRUE"
            )
        except Exception as e:
            logger.warning(f"get_pnl_wide failed for {company_id}/{category}: {e}")
            return pd.DataFrame(), []
        if df.empty:
            logger.warning(f"No P&L data for {company_id}/{category}")
            return pd.DataFrame(), []
        # Deduplicate: when multiple Analyze runs produce duplicate active rows for
        # the same (financial_item, year), keep only the highest-version row so that
        # BankruptcyAnalysis and CostStructureAnalysis always see the latest values.
        df = (df.sort_values("version", ascending=False)
                .drop_duplicates(subset=["financial_item", "year"], keep="first"))
        # Map canonical → legacy label
        df["Particulars"] = df["financial_item"].map(
            lambda x: CANONICAL_TO_PNL_LABEL.get(x, x)
        )
        # Pivot
        wide = df.pivot_table(index="Particulars", columns="year", values="value", aggfunc="first")
        # Pull Units (most common per item)
        units = df.groupby("Particulars")["units"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else "INR Million"
        )
        wide.insert(0, "Units", units)
        # Re-sort year columns descending (FY25, FY24, …)
        year_cols = sorted([c for c in wide.columns if str(c).startswith("FY")], reverse=True)
        wide = wide[["Units"] + year_cols]
        return wide, year_cols

    # ----------------------------------------------------------------

    def get_altman_wide(self, company_id: str) -> tuple[pd.DataFrame, list]:
        items = list(CANONICAL_TO_ALTMAN_LABEL.keys())
        in_clause = ",".join(f"'{x}'" for x in items)
        try:
            df = self.engine.sql(
                f"SELECT financial_item, year, value, units, version "
                f"FROM financials "
                f"WHERE company_id = '{company_id}' "
                f"  AND financial_category = 'Altman Z' "
                f"  AND financial_item IN ({in_clause}) "
                f"  AND is_active = TRUE"
            )
        except Exception as e:
            logger.warning(f"get_altman_wide failed for {company_id}: {e}")
            return pd.DataFrame(), []
        if df.empty:
            logger.warning(f"No Altman data for {company_id}")
            return pd.DataFrame(), []
        # Deduplicate: keep only the highest-version row per (financial_item, year)
        df = (df.sort_values("version", ascending=False)
                .drop_duplicates(subset=["financial_item", "year"], keep="first"))
        df["Particulars"] = df["financial_item"].map(CANONICAL_TO_ALTMAN_LABEL)
        wide = df.pivot_table(index="Particulars", columns="year", values="value", aggfunc="first")
        units = df.groupby("Particulars")["units"].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else "INR Million"
        )
        wide.insert(0, "Units", units)
        year_cols = sorted([c for c in wide.columns if str(c).startswith("FY")], reverse=True)
        # FY19 stays in the wide frame so the engine can use it for FY20's Retained Earning
        wide = wide[["Units"] + year_cols]
        engine_years = [y for y in year_cols if y not in ("FY19",)]
        return wide, engine_years
