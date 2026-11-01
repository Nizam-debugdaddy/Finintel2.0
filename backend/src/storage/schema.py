"""
Parquet schemas for the financial data warehouse.

The warehouse uses LONG/VERTICAL format so the same table holds data for any
number of companies, years, and line items without schema changes.
"""

import pyarrow as pa


# ── Fact table: financials_long ─────────────────────────────────────
# One row per (company, year, item, version).
# Partitioned on disk by company_id then year for efficient pruning.
FINANCIALS_SCHEMA = pa.schema([
    ("company_id",         pa.string()),    # FK → company_master.company_id
    ("company_name",       pa.string()),    # denormalized for query convenience
    ("financial_item",     pa.string()),    # canonical name (e.g. "Revenue from Operations")
    ("financial_category", pa.string()),    # "P&L" | "Balance Sheet" | "Market" | "Altman Z"
    ("year",               pa.string()),    # "FY25", "FY24", … kept as string
    ("value",              pa.float64()),   # numeric value
    ("units",              pa.string()),    # "INR Million" | "INR Crs" | "%" | "Ratio" | "Days"
    ("source_file",        pa.string()),    # path of file ingested
    ("version",            pa.int32()),     # 1, 2, 3, … per (company, year, item)
    ("is_active",          pa.bool_()),     # only the newest version per key is active
    ("updated_on",         pa.timestamp("us")),
    ("ingestion_id",       pa.string()),    # unique id per ingestion run
])

# ── Company master ──────────────────────────────────────────────────
COMPANY_MASTER_SCHEMA = pa.schema([
    ("company_id",   pa.string()),
    ("company_name", pa.string()),
    ("ticker",       pa.string()),
    ("isin",         pa.string()),
    ("active_flag",  pa.bool_()),
])

# ── Sector mapping (many-to-many) ───────────────────────────────────
SECTOR_MAPPING_SCHEMA = pa.schema([
    ("company_id", pa.string()),
    ("sector",     pa.string()),
    ("sub_sector", pa.string()),
])

# ── Audit log ───────────────────────────────────────────────────────
AUDIT_SCHEMA = pa.schema([
    ("ingestion_id", pa.string()),
    ("company_id",   pa.string()),
    ("source_file",  pa.string()),
    ("rows_loaded",  pa.int64()),
    ("rows_revised", pa.int64()),
    ("status",       pa.string()),      # "success" | "failed" | "partial"
    ("notes",        pa.string()),
    ("timestamp",    pa.timestamp("us")),
])


# ── Convenience: dataclass-like row builder ─────────────────────────

def financials_record(
    company_id: str, company_name: str, financial_item: str,
    financial_category: str, year: str, value: float, units: str,
    source_file: str, version: int, is_active: bool, updated_on, ingestion_id: str,
) -> dict:
    """Build a single row conforming to FINANCIALS_SCHEMA."""
    return {
        "company_id":         company_id,
        "company_name":       company_name,
        "financial_item":     financial_item,
        "financial_category": financial_category,
        "year":               year,
        "value":              float(value) if value is not None else None,
        "units":              units,
        "source_file":        source_file,
        "version":            int(version),
        "is_active":          bool(is_active),
        "updated_on":         updated_on,
        "ingestion_id":       ingestion_id,
    }
