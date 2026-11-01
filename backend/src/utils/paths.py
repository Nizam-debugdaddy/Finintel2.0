"""
Central path configuration for the financial data platform.
All other modules read paths from here so the platform is relocatable.
"""

from pathlib import Path


class Paths:
    """Resolved paths relative to the project root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

        # Top-level directories
        self.raw          = self.root / "raw"
        self.processed    = self.root / "processed"
        self.warehouse    = self.root / "warehouse"
        self.mappings     = self.root / "mappings"
        self.logs         = self.root / "logs"
        self.config       = self.root / "config"
        self.query_dir    = self.root / "query_templates"
        self.legacy       = self.root / "legacy_engines"
        self.output       = self.root / "output"

        # Parquet warehouse files
        self.wh_company_master = self.warehouse / "company_master.parquet"
        self.wh_sector_map     = self.warehouse / "sector_mapping.parquet"
        self.wh_financials     = self.warehouse / "financials"        # partitioned dataset
        self.wh_audit          = self.warehouse / "audit_log.parquet"

        # Mapping files
        self.mapping_lineitem  = self.mappings / "line_item_mapping.json"
        self.mapping_adapters  = self.mappings / "refinitiv_adapters.json"

    def ensure(self):
        """Make sure every required directory exists."""
        for p in [self.raw, self.processed, self.warehouse, self.mappings,
                  self.logs, self.config, self.query_dir, self.output,
                  self.wh_financials]:
            p.mkdir(parents=True, exist_ok=True)
        return self
