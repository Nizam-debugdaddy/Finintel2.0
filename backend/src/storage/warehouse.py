"""
Warehouse storage layer.
Handles parquet writes for the long/vertical financials table,
with versioning, partitioning, and master-table maintenance.
"""

from __future__ import annotations
import shutil
import time as _time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from utils import get_logger, Paths
from storage.schema import (
    FINANCIALS_SCHEMA, COMPANY_MASTER_SCHEMA, SECTOR_MAPPING_SCHEMA, AUDIT_SCHEMA,
)

logger = get_logger("warehouse")


class Warehouse:
    """
    Manages the parquet warehouse.
    Tables:
      - company_master.parquet            (single file)
      - sector_mapping.parquet            (single file)
      - financials/                       (partitioned dataset by company_id/year)
      - audit_log.parquet                 (single file, append-only)
    """

    def __init__(self, paths: Paths):
        self.paths = paths
        self.paths.ensure()

    # ── Company master ──────────────────────────────────────────────

    def upsert_company_master(self, df: pd.DataFrame) -> None:
        """Replace company master from a DataFrame (company_id, company_name, ticker, isin, active_flag)."""
        # Coerce types to match schema
        df = df.copy()
        df["active_flag"] = df["active_flag"].astype(bool)
        tbl = pa.Table.from_pandas(df, schema=COMPANY_MASTER_SCHEMA, preserve_index=False)
        pq.write_table(tbl, self.paths.wh_company_master)
        logger.info(f"Wrote {len(df)} companies to {self.paths.wh_company_master.name}")

    def upsert_sector_mapping(self, df: pd.DataFrame) -> None:
        """Replace sector mapping (many-to-many) with provided DataFrame."""
        tbl = pa.Table.from_pandas(df, schema=SECTOR_MAPPING_SCHEMA, preserve_index=False)
        pq.write_table(tbl, self.paths.wh_sector_map)
        logger.info(f"Wrote {len(df)} sector mappings")

    def read_company_master(self) -> pd.DataFrame:
        if not self.paths.wh_company_master.exists():
            return pd.DataFrame(columns=[f.name for f in COMPANY_MASTER_SCHEMA])
        return pq.read_table(self.paths.wh_company_master).to_pandas()

    def read_sector_mapping(self) -> pd.DataFrame:
        if not self.paths.wh_sector_map.exists():
            return pd.DataFrame(columns=[f.name for f in SECTOR_MAPPING_SCHEMA])
        return pq.read_table(self.paths.wh_sector_map).to_pandas()

    # ── Financials (versioned fact table) ───────────────────────────

    def load_all_financials(self) -> pd.DataFrame:
        """Read the full financials dataset. Returns empty frame if none exist.
        Falls back to reading company-by-company if the full dataset read fails
        (handles cases where a bad/corrupt file is present in one partition).
        """
        if not self.paths.wh_financials.exists() or \
           not any(self.paths.wh_financials.rglob("*.parquet")):
            return pd.DataFrame(columns=[f.name for f in FINANCIALS_SCHEMA])
        # ── Primary: read all at once (fast) ──────────────────────────────────
        try:
            ds = pq.ParquetDataset(
                str(self.paths.wh_financials),
                use_legacy_dataset=False,
            )
            return ds.read().to_pandas()
        except Exception as e1:
            logger.warning(f"load_all_financials primary read failed: {e1}. "
                           f"Attempting per-company fallback read…")

        # ── Fallback: read each *.parquet individually, skip corrupted ones ──
        frames = []
        for pf in sorted(self.paths.wh_financials.rglob("*.parquet")):
            try:
                frames.append(pq.read_table(str(pf)).to_pandas())
            except Exception as e2:
                logger.warning(f"Skipping bad parquet {pf}: {e2}")
                # Quarantine it so it doesn't block again
                try:
                    pf.rename(pf.with_suffix(".bad"))
                    logger.warning(f"Quarantined: {pf}")
                except Exception:
                    pass

        if frames:
            return pd.concat(frames, ignore_index=True)
        return pd.DataFrame(columns=[f.name for f in FINANCIALS_SCHEMA])

    def load_company_financials(self, company_id: str) -> pd.DataFrame:
        """Read financials for a single company using hive partition pruning.
        Reads only company_id=X/ — much faster than loading all companies.
        """
        if not self.paths.wh_financials.exists() or \
           not any(self.paths.wh_financials.rglob("*.parquet")):
            return pd.DataFrame(columns=[f.name for f in FINANCIALS_SCHEMA])
        try:
            ds = pq.ParquetDataset(
                str(self.paths.wh_financials),
                use_legacy_dataset=False,
                filters=[("company_id", "=", company_id)],
            )
            df = ds.read().to_pandas()
            return df
        except Exception as e:
            logger.warning(f"load_company_financials({company_id}) failed: {e}. Falling back to full read.")
            full = self.load_all_financials()
            return full[full["company_id"] == company_id].copy() if not full.empty else full

    def ingest_financials(self, new_records: list[dict], ingestion_id: str | None = None) -> dict:
        """
        Ingest a batch of standardized records into the warehouse.

        Versioning algorithm:
          ROW KEY = (company_id, financial_category, financial_item, year)
          For each key:
            - Find max existing version V; new row gets V+1.
            - Mark all previously-active rows with that key as is_active=False.
            - The newest row is is_active=True.
          Within a single batch, if the same key appears more than once, keep
          the LAST occurrence (later = newer); earlier ones are dropped.

        Returns ingestion summary dict.
        """
        ingestion_id = ingestion_id or str(uuid.uuid4())

        # ── Dedup within batch: keep last occurrence per key ──
        deduped: dict = {}
        for r in new_records:
            k = (r["company_id"], r["financial_category"], r["financial_item"], r["year"])
            deduped[k] = r
        new_records = list(deduped.values())

        # All records must belong to the same company (normal usage).
        # Use company-scoped read for partition pruning — avoids loading ALL companies.
        company_id_scope = new_records[0]["company_id"] if new_records else None
        _tw0 = _time.perf_counter()
        existing = (self.load_company_financials(company_id_scope)
                    if company_id_scope else self.load_all_financials())
        logger.warning(f"[WH] load existing ({len(existing)} rows) in {_time.perf_counter()-_tw0:.3f}s")

        if not existing.empty:
            new_keys = {
                (r["company_id"], r["financial_category"], r["financial_item"], r["year"])
                for r in new_records
            }
            # Vectorized mask — much faster than apply(fn, axis=1) for large DataFrames
            _key_col = (existing["company_id"].astype(str) + "|" +
                        existing["financial_category"].astype(str) + "|" +
                        existing["financial_item"].astype(str) + "|" +
                        existing["year"].astype(str))
            _new_keys_str = {f"{k[0]}|{k[1]}|{k[2]}|{k[3]}" for k in new_keys}
            mask = _key_col.isin(_new_keys_str)
            # Compute max version BEFORE dropping replaced rows
            grp = (existing
                   .groupby(["company_id", "financial_category", "financial_item", "year"])
                   ["version"].max())
            max_versions = grp.to_dict()
            # Keep only rows NOT being replaced (discard replaced rows entirely).
            # This prevents accumulation of inactive version history which can grow
            # to hundreds of thousands of rows and make reads/writes very slow.
            existing_keep = existing[~mask].copy()
        else:
            max_versions = {}
            existing_keep = pd.DataFrame(columns=[f.name for f in FINANCIALS_SCHEMA])

        revised = 0
        for r in new_records:
            key = (r["company_id"], r["financial_category"], r["financial_item"], r["year"])
            prev = max_versions.get(key, 0)
            r["version"] = prev + 1
            if prev > 0:
                revised += 1
            r["is_active"] = True
            r["ingestion_id"] = ingestion_id
            if r.get("updated_on") is None:
                r["updated_on"] = datetime.utcnow()

        combined = pd.concat(
            [existing_keep, pd.DataFrame(new_records)],
            ignore_index=True,
        ) if not existing_keep.empty else pd.DataFrame(new_records)

        # ── Coerce types to match FINANCIALS_SCHEMA exactly ───────────────────
        # Without this, round-tripping through pandas can produce int64 for
        # version (schema expects int32), or tz-aware timestamps (schema expects
        # tz-naive us), causing pa.Table.from_pandas to fail.
        if "version" in combined.columns:
            combined["version"] = combined["version"].fillna(1).astype("int32")
        if "is_active" in combined.columns:
            combined["is_active"] = combined["is_active"].astype("bool")
        if "value" in combined.columns:
            combined["value"] = pd.to_numeric(combined["value"], errors="coerce")
        if "updated_on" in combined.columns:
            # pd.to_datetime with utc=True always produces tz-aware (UTC).
            # tz_convert(None) then strips the timezone, giving tz-naive UTC,
            # which matches pa.timestamp("us") in FINANCIALS_SCHEMA.
            combined["updated_on"] = (
                pd.to_datetime(combined["updated_on"], errors="coerce", utc=True)
                .dt.tz_convert(None)
                .astype("datetime64[us]")
            )

        # Delete only this company's partition — leaves other companies untouched.
        # This is the key optimization: previously rmtree deleted ALL companies' data
        # and rewrote the entire warehouse on every ingest call.
        _tw1 = _time.perf_counter()
        self.paths.wh_financials.mkdir(parents=True, exist_ok=True)
        if company_id_scope:
            company_dir = self.paths.wh_financials / f"company_id={company_id_scope}"
            if company_dir.exists():
                shutil.rmtree(company_dir)
        else:
            if self.paths.wh_financials.exists():
                shutil.rmtree(self.paths.wh_financials)
            self.paths.wh_financials.mkdir(parents=True, exist_ok=True)

        tbl = pa.Table.from_pandas(combined, schema=FINANCIALS_SCHEMA, preserve_index=False)
        pq.write_to_dataset(
            tbl,
            root_path=str(self.paths.wh_financials),
            partition_cols=["company_id", "year"],
        )
        logger.warning(f"[WH] write {len(combined)} rows to parquet in {_time.perf_counter()-_tw1:.3f}s")

        self._append_audit(
            ingestion_id=ingestion_id,
            company_id=new_records[0]["company_id"] if new_records else "",
            source_file=new_records[0]["source_file"] if new_records else "",
            rows_loaded=len(new_records),
            rows_revised=revised,
            status="success",
            notes=f"new={len(new_records)-revised}, revised={revised}",
        )

        summary = {
            "ingestion_id": ingestion_id,
            "rows_loaded":  len(new_records),
            "rows_revised": revised,
            "rows_new":     len(new_records) - revised,
        }
        logger.info(f"Ingested batch: {summary}")
        return summary

    # ── Audit ───────────────────────────────────────────────────────

    def _append_audit(self, **kw) -> None:
        kw.setdefault("timestamp", datetime.utcnow())
        row_df = pd.DataFrame([kw])
        if self.paths.wh_audit.exists():
            old = pq.read_table(self.paths.wh_audit).to_pandas()
            combined = pd.concat([old, row_df], ignore_index=True)
        else:
            combined = row_df
        tbl = pa.Table.from_pandas(combined, schema=AUDIT_SCHEMA, preserve_index=False)
        pq.write_table(tbl, self.paths.wh_audit)

    def read_audit_log(self) -> pd.DataFrame:
        if not self.paths.wh_audit.exists():
            return pd.DataFrame(columns=[f.name for f in AUDIT_SCHEMA])
        return pq.read_table(self.paths.wh_audit).to_pandas()

    def deactivate_period(self, company_id: str, period: str) -> int:
        """
        Mark ALL rows for (company_id, year=period) as is_active=False.
        Used when analyst deletes all data for a period.
        Returns the number of rows deactivated.
        """
        existing = self.load_company_financials(company_id)
        if existing.empty:
            return 0

        mask = existing["year"] == period
        n_deactivated = int(mask.sum())
        if n_deactivated == 0:
            return 0

        # Drop the rows for this period entirely (clean removal, no inactive accumulation)
        existing_keep = existing[~mask].copy()

        self.paths.wh_financials.mkdir(parents=True, exist_ok=True)
        company_dir = self.paths.wh_financials / f"company_id={company_id}"
        if company_dir.exists():
            shutil.rmtree(company_dir)

        if not existing_keep.empty:
            tbl = pa.Table.from_pandas(
                existing_keep, schema=FINANCIALS_SCHEMA, preserve_index=False
            )
            pq.write_to_dataset(
                tbl,
                root_path=str(self.paths.wh_financials),
                partition_cols=["company_id", "year"],
            )
        logger.info(f"Removed {n_deactivated} rows for {company_id}/{period}")
        return n_deactivated

    def deactivate_all(self, company_id: str) -> int:
        """Drop ALL warehouse rows for company_id by deleting its partition directory."""
        existing = self.load_company_financials(company_id)
        if existing.empty:
            return 0
        n = len(existing)
        company_dir = self.paths.wh_financials / f"company_id={company_id}"
        if company_dir.exists():
            shutil.rmtree(company_dir)
        logger.info(f"Removed all {n} rows for {company_id}")
        return n
