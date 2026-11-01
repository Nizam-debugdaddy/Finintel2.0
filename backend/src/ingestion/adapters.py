"""
Source-file adapters.
Each adapter knows how to read one source-file format and yield
normalized records in canonical form.

Two adapters are supported as agreed:
  - StandardizedTemplateAdapter: the 3-sheet analyst template
  - RefinitivRawAdapter:         per-company raw Refinitiv Excel layouts
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from utils import get_logger
from standardization import Normalizer

logger = get_logger("adapters")


# ════════════════════════════════════════════════════════════════════
# Base
# ════════════════════════════════════════════════════════════════════

class SourceAdapter:
    """Abstract base. Subclasses implement read()."""

    def __init__(self, source_file: str | Path, company_id: str, company_name: str,
                 normalizer: Normalizer, adapter_cfg: dict):
        self.source_file  = str(source_file)
        self.company_id   = company_id
        self.company_name = company_name
        self.norm         = normalizer
        self.cfg          = adapter_cfg

    def read(self) -> list[dict]:
        """Return list of partially-built records (no version/ingestion_id yet)."""
        raise NotImplementedError

    # Shared helpers
    def _new_record(self, item: str, category: str, year: str, value, units: str) -> dict:
        return {
            "company_id":         self.company_id,
            "company_name":       self.company_name,
            "financial_item":     item,
            "financial_category": category,
            "year":               year,
            "value":              value,
            "units":              units,
            "source_file":        self.source_file,
            "version":            None,           # set during ingest
            "is_active":          True,
            "updated_on":         datetime.utcnow(),
            "ingestion_id":       None,
        }


# ════════════════════════════════════════════════════════════════════
# Standardized template adapter
# ════════════════════════════════════════════════════════════════════

class StandardizedTemplateAdapter(SourceAdapter):
    """
    Reads the analyst-validated 3-sheet workbook:
      - 'Altman Z score.in '
      - 'P&L Co Extract Sheet.in'
      - 'P&L std extract sheet.in '
    """

    def read(self) -> list[dict]:
        sheets_cfg = self.cfg["sheets"]
        particulars_col = self.cfg.get("particulars_col", "Particulars")
        units_col       = self.cfg.get("units_col", "Units")
        year_prefix     = self.cfg.get("year_col_prefix", "FY")

        xls = pd.ExcelFile(self.source_file)
        records: list[dict] = []

        for sheet_name, sheet_meta in sheets_cfg.items():
            if sheet_name not in xls.sheet_names:
                logger.warning(f"Sheet '{sheet_name}' not in {self.source_file}; skipping")
                continue

            df = pd.read_excel(xls, sheet_name=sheet_name)
            if particulars_col not in df.columns:
                logger.warning(f"Sheet '{sheet_name}' missing column '{particulars_col}'")
                continue

            category_override = sheet_meta.get("category", "Unknown")
            df[particulars_col] = df[particulars_col].astype(str).str.strip()
            df = df.dropna(subset=[particulars_col])
            year_cols = [c for c in df.columns if str(c).startswith(year_prefix)]

            for _, row in df.iterrows():
                raw_item = row[particulars_col]
                if not raw_item or raw_item == "nan":
                    continue
                canonical = self.norm.resolve(raw_item)
                if canonical is None:
                    logger.debug(f"Unmapped row '{raw_item}' in {sheet_name}")
                    canonical = raw_item
                    units = row.get(units_col, "INR Million")
                else:
                    units = row.get(units_col, self.norm.default_units(canonical))

                # IMPORTANT: For the standardized template, the category comes from
                # the source SHEET (P&L Consolidated, P&L Standalone, Altman Z), not
                # from the canonical mapping. The same canonical name can mean
                # different things on different sheets (e.g. "Revenue from Operations"
                # in Altman sheet = Total Revenue including other income, vs in the
                # P&L sheet = pure Revenue from Ops).
                category = category_override

                for yr in year_cols:
                    v = row[yr]
                    if pd.isna(v):
                        continue
                    try:
                        v_num = float(v)
                    except (TypeError, ValueError):
                        continue
                    records.append(self._new_record(
                        item=canonical, category=category, year=str(yr),
                        value=v_num, units=str(units),
                    ))

        logger.info(f"[standardized] Read {len(records)} records from {Path(self.source_file).name}")
        return records


# ════════════════════════════════════════════════════════════════════
# Refinitiv raw adapter
# ════════════════════════════════════════════════════════════════════

class RefinitivRawAdapter(SourceAdapter):
    """
    Reads a raw Refinitiv Eikon Excel export per a per-company sheet/column config.

    Example config entry (in mappings/refinitiv_adapters.json):

      "DRREDDY.NS": {
        "type": "refinitiv_raw",
        "sheets": {
          "Income Statement": {
            "category": "P&L Consolidated",
            "particulars_col": "Item",
            "year_cols_regex": "^\\d{4}-\\d{2}$"
          }
        }
      }

    The adapter normalizes Refinitiv year labels (e.g. "2024-03" → "FY24")
    so they conform to the warehouse's FYxx scheme.
    """

    YEAR_LABEL_PATTERN = re.compile(r"(\d{4})[-/](\d{2})")

    def read(self) -> list[dict]:
        sheets_cfg = self.cfg.get("sheets", {})
        records: list[dict] = []
        xls = pd.ExcelFile(self.source_file)

        for sheet_name, sheet_meta in sheets_cfg.items():
            if sheet_name not in xls.sheet_names:
                logger.warning(f"Refinitiv sheet '{sheet_name}' not in {self.source_file}")
                continue

            df = pd.read_excel(xls, sheet_name=sheet_name)
            part_col = sheet_meta.get("particulars_col", "Item")
            if part_col not in df.columns:
                logger.warning(f"Column '{part_col}' missing in sheet '{sheet_name}'")
                continue

            year_regex = re.compile(sheet_meta.get("year_cols_regex", r"^\d{4}-\d{2}$"))
            year_cols = [c for c in df.columns if year_regex.match(str(c))]
            df[part_col] = df[part_col].astype(str).str.strip()
            df = df.dropna(subset=[part_col])

            for _, row in df.iterrows():
                raw_item = row[part_col]
                canonical = self.norm.resolve(raw_item) or raw_item
                category = (self.norm.category_of(canonical) if self.norm.resolve(raw_item)
                            else sheet_meta.get("category", "Unknown"))
                units = self.norm.default_units(canonical) if self.norm.resolve(raw_item) else "INR Million"

                for yc in year_cols:
                    v = row[yc]
                    if pd.isna(v):
                        continue
                    try:
                        v_num = float(v)
                    except (TypeError, ValueError):
                        continue
                    fy = self._refinitiv_label_to_fy(str(yc))
                    records.append(self._new_record(
                        item=canonical, category=category, year=fy,
                        value=v_num, units=units,
                    ))
        logger.info(f"[refinitiv_raw] Read {len(records)} records from {Path(self.source_file).name}")
        return records

    @classmethod
    def _refinitiv_label_to_fy(cls, label: str) -> str:
        """Convert '2024-03' or '2024/03' → 'FY24' (Indian FY ending March)."""
        m = cls.YEAR_LABEL_PATTERN.search(label)
        if not m:
            return label
        year, month = int(m.group(1)), int(m.group(2))
        # Indian fiscal year: month >= 4 belongs to year+1's FY; FY24 = Apr23-Mar24
        if month <= 3:
            fy_end_year = year
        else:
            fy_end_year = year + 1
        return f"FY{fy_end_year % 100:02d}"


# ════════════════════════════════════════════════════════════════════
# Adapter factory
# ════════════════════════════════════════════════════════════════════

class AdapterRegistry:
    """Resolves the right adapter for a (company, file) pair."""

    def __init__(self, adapter_cfg_path: str | Path, normalizer: Normalizer):
        with open(adapter_cfg_path) as f:
            self.cfg = json.load(f)
        self.norm = normalizer

    def get_adapter(self, source_file: str | Path,
                    company_id: str, company_name: str,
                    ticker: str | None = None) -> SourceAdapter:
        """Pick adapter by ticker; fall back to STANDARDIZED."""
        chosen_cfg = None
        if ticker and ticker in self.cfg:
            chosen_cfg = self._resolve_inherits(self.cfg[ticker])
        if chosen_cfg is None:
            chosen_cfg = self.cfg.get("STANDARDIZED")
        if chosen_cfg is None:
            raise ValueError("No adapter config found and STANDARDIZED fallback missing")

        adapter_type = chosen_cfg.get("type", "standardized_template")
        if adapter_type == "standardized_template":
            return StandardizedTemplateAdapter(source_file, company_id, company_name,
                                               self.norm, chosen_cfg)
        elif adapter_type == "refinitiv_raw":
            return RefinitivRawAdapter(source_file, company_id, company_name,
                                       self.norm, chosen_cfg)
        else:
            raise ValueError(f"Unknown adapter type: {adapter_type}")

    def _resolve_inherits(self, cfg: dict) -> dict:
        """Resolve 'inherits' chain so per-company configs can extend STANDARDIZED."""
        if "inherits" not in cfg:
            return cfg
        parent = self.cfg.get(cfg["inherits"])
        if parent is None:
            return cfg
        merged = dict(parent)
        merged.update(cfg)
        return merged
