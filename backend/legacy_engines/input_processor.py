"""
input_processor.py
Reads and normalizes the analyst-provided financial input workbook.
Row name mapping uses the JSON alias dictionary.
"""

import json
import pandas as pd
from pathlib import Path
from engine_utils import setup_logger

logger = setup_logger("input_processor")


class InputProcessor:
    """Reads and normalizes the analyst-provided financial input workbook."""

    SHEET_PNL_CO  = "P&L Co Extract Sheet.in"
    SHEET_PNL_STD = "P&L std extract sheet.in "   # trailing space in source
    SHEET_ALTMAN  = "Altman Z score.in "           # trailing space in source

    def __init__(self, input_path: str, mapping_path: str = None):
        self.input_path   = Path(input_path)
        self.mapping_path = Path(mapping_path) if mapping_path else None
        self.mapping      = self._load_mapping()
        self.year_cols: list = []

    # ------------------------------------------------------------------
    def load(self) -> dict:
        """Return dict with pnl_co, pnl_std, altman DataFrames and years list."""
        logger.info(f"Loading input file: {self.input_path}")
        if not self.input_path.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_path}")

        xls = pd.ExcelFile(self.input_path)
        logger.info(f"Sheets found: {xls.sheet_names}")

        pnl_co  = self._read_sheet(xls, self.SHEET_PNL_CO,  "P&L CO")
        pnl_std = self._read_sheet(xls, self.SHEET_PNL_STD, "P&L Standalone")
        altman  = self._read_sheet(xls, self.SHEET_ALTMAN,  "Altman Z")

        # Detect year columns dynamically (any col starting with "FY")
        self.year_cols = [c for c in pnl_co.columns if str(c).startswith("FY")]
        logger.info(f"Year columns detected: {self.year_cols}")

        # Log all loaded row names so analysts can debug mapping issues
        logger.info(f"P&L CO rows: {list(pnl_co.index)}")
        logger.info(f"Altman rows: {list(altman.index)}")

        return {"pnl_co": pnl_co, "pnl_std": pnl_std, "altman": altman,
                "years": self.year_cols}

    # ------------------------------------------------------------------
    def _load_mapping(self) -> dict:
        if self.mapping_path and self.mapping_path.exists():
            with open(self.mapping_path) as f:
                raw = json.load(f)
            reverse = {}
            for canonical, aliases in raw.items():
                for alias in aliases:
                    reverse[alias.strip().lower()] = canonical
            logger.info(f"Loaded {len(reverse)} alias mappings")
            return reverse
        logger.warning("No mapping file found – using raw row names")
        return {}

    def _read_sheet(self, xls, sheet_name: str, label: str) -> pd.DataFrame:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, dtype={"Particulars": str})
        except Exception as e:
            logger.error(f"Could not read sheet '{sheet_name}': {e}")
            raise

        df = df.dropna(subset=["Particulars"]).copy()
        df["Particulars"] = df["Particulars"].astype(str).str.strip()

        # Log INPUT→MAPPED for every row
        for orig in df["Particulars"].tolist():
            mapped = self.mapping.get(orig.strip().lower(), orig)
            if mapped != orig:
                logger.info(f"  [{label}] MAPPED: '{orig}' → '{mapped}'")
            else:
                logger.debug(f"  [{label}] UNMAPPED: '{orig}' (using as-is)")

        df["Particulars"] = df["Particulars"].apply(self._normalize_name)
        df = df.drop_duplicates(subset=["Particulars"], keep="first")

        # Convert year columns safely
        year_cols = [c for c in df.columns if str(c).startswith("FY")]
        for col in year_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.set_index("Particulars")
        logger.info(f"[{label}] Loaded {len(df)} rows, columns: {list(df.columns)}")
        return df

    def _normalize_name(self, name: str) -> str:
        return self.mapping.get(name.strip().lower(), name)

    @staticmethod
    def get_val(df: pd.DataFrame, row: str, col: str, default=None):
        """Safely retrieve df.loc[row, col]."""
        try:
            val = df.loc[row, col]
            if pd.isna(val):
                return default
            return float(val)
        except (KeyError, TypeError, ValueError):
            return default
