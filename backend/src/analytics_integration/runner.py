"""
Analytics integration.
Loads data from the warehouse, reshapes it, and feeds the existing
cost-structure + bankruptcy analytics engines to produce Output_Analysis.xlsx.
"""

from __future__ import annotations
import sys
from pathlib import Path

from utils import get_logger, Paths
from retrieval import QueryEngine
from analytics_integration.reshaper import WarehouseReshaper

logger = get_logger("analytics_runner")


class AnalyticsRunner:
    """End-to-end: warehouse → reshape → cost/bankruptcy engines → Excel output."""

    def __init__(self, paths: Paths):
        self.paths = paths
        # Make legacy engines importable
        sys.path.insert(0, str(paths.legacy))
        self.engine = QueryEngine(paths)
        self.reshaper = WarehouseReshaper(self.engine)

    # ----------------------------------------------------------------

    def run_for_company(self, company_id: str, output_filename: str | None = None) -> Path:
        """
        Generate Output_Analysis.xlsx for one company straight from the warehouse.
        Returns the output path.
        """
        # Imports the legacy modules added to sys.path
        from cost_structure_analysis import CostStructureAnalysis
        from bankruptcy_analysis import BankruptcyAnalysis
        from excel_writer import ExcelWriter

        # ── Pull wide DataFrames ──
        pnl_co, years_co   = self.reshaper.get_pnl_wide(company_id, "P&L Consolidated")
        pnl_std, years_std = self.reshaper.get_pnl_wide(company_id, "P&L Standalone")
        altman, years_alt  = self.reshaper.get_altman_wide(company_id)

        if pnl_co.empty or altman.empty:
            raise RuntimeError(f"Insufficient data in warehouse for {company_id}")

        years = years_co or years_alt
        logger.info(f"Running analytics for {company_id} over years {years}")

        # ── Run engines ──
        co_results  = CostStructureAnalysis(pnl_co, years).run()
        std_results = (CostStructureAnalysis(pnl_std, years).run()
                       if not pnl_std.empty else co_results)
        bk_results  = BankruptcyAnalysis(altman, pnl_co, years).run()

        # ── Write Excel ──
        out_name = output_filename or f"Output_Analysis_{company_id}.xlsx"
        out_path = self.paths.output / out_name
        writer = ExcelWriter(str(out_path), years)
        writer.write(bk_results, co_results, std_results)
        logger.info(f"Wrote analytics output: {out_path}")
        return out_path

    def close(self):
        self.engine.close()
