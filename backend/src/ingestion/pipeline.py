"""
Ingestion pipeline.
Chains adapter → validator → warehouse for a single source file.
"""

from __future__ import annotations
from pathlib import Path

from utils import get_logger, Paths
from standardization import Normalizer, RecordValidator
from storage import Warehouse
from ingestion.adapters import AdapterRegistry

logger = get_logger("pipeline")


class IngestionPipeline:
    """Orchestrates ingestion of a single source file into the warehouse."""

    def __init__(self, paths: Paths):
        self.paths = paths
        self.normalizer = Normalizer(paths.mapping_lineitem)
        self.registry   = AdapterRegistry(paths.mapping_adapters, self.normalizer)
        self.validator  = RecordValidator(strict=False)
        self.warehouse  = Warehouse(paths)

    def ingest(self, source_file: str | Path, company_id: str,
               company_name: str | None = None, ticker: str | None = None) -> dict:
        """
        Ingest a source file end-to-end.

        Args:
            source_file: path to Excel file
            company_id:  warehouse key (e.g. 'SUN')
            company_name: optional human-readable name (looked up from master if missing)
            ticker:      optional ticker to pick the adapter (looked up from master if missing)
        Returns:
            dict with ingestion summary
        """
        # ── Resolve company_name / ticker from master if not given ──
        cm_df = self.warehouse.read_company_master()
        if not cm_df.empty:
            row = cm_df[cm_df["company_id"] == company_id]
            if not row.empty:
                if company_name is None:
                    company_name = row.iloc[0]["company_name"]
                if ticker is None:
                    ticker = row.iloc[0]["ticker"]

        company_name = company_name or company_id
        logger.info(f"Ingesting: file={source_file}, company={company_id} ({company_name}), ticker={ticker}")

        # ── Read via adapter ──
        adapter = self.registry.get_adapter(source_file, company_id, company_name, ticker)
        records = adapter.read()
        if not records:
            logger.warning(f"Adapter returned 0 records for {source_file}")
            return {"rows_loaded": 0, "rows_revised": 0, "rows_new": 0}

        # ── Validate ──
        valid, rejected = self.validator.validate_batch(records)
        if rejected:
            logger.warning(f"{len(rejected)} records rejected by validator")

        # ── Write to warehouse with versioning ──
        summary = self.warehouse.ingest_financials(valid)
        summary["rejected"] = len(rejected)
        summary["adapter"]  = adapter.__class__.__name__
        return summary
