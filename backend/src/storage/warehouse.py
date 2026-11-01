"""
Warehouse storage layer.
Handles parquet writes for the long/vertical financials table,
with versioning, partitioning, and master-table maintenance.
"""

from __future__ import annotations
import os
import time as _time
import uuid
from contextlib import contextmanager
from datetime import datetime

import pandas as pd
import psycopg2
import psycopg2.extras
import pyarrow as pa
import pyarrow.parquet as pq

from utils import get_logger, Paths
from storage.schema import (
    FINANCIALS_SCHEMA, COMPANY_MASTER_SCHEMA, SECTOR_MAPPING_SCHEMA, AUDIT_SCHEMA,
)

logger = get_logger("warehouse")

FINANCIALS_COLUMNS = [f.name for f in FINANCIALS_SCHEMA]


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
        self._dsn = os.environ.get("DATABASE_URL", "")

    @contextmanager
    def _conn(self):
        """`with self._conn() as conn:` commits (or rolls back) AND closes —
        a bare psycopg2 connection used as a context manager commits but never
        closes, which would leak connections against the pooler over time."""
        conn = psycopg2.connect(self._dsn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

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
        """Read the full financials dataset from Postgres. Empty frame if none exist."""
        with self._conn() as conn:
            df = pd.read_sql(f"SELECT {','.join(FINANCIALS_COLUMNS)} FROM financials", conn)
        return df if not df.empty else pd.DataFrame(columns=FINANCIALS_COLUMNS)

    def load_company_financials(self, company_id: str) -> pd.DataFrame:
        """Read financials for a single company from Postgres (indexed on company_id)."""
        with self._conn() as conn:
            df = pd.read_sql(
                f"SELECT {','.join(FINANCIALS_COLUMNS)} FROM financials WHERE company_id = %(cid)s",
                conn, params={"cid": company_id},
            )
        return df if not df.empty else pd.DataFrame(columns=FINANCIALS_COLUMNS)

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

        # Delete only this company's rows — leaves other companies untouched.
        # Mirrors the old per-company parquet-partition rewrite, now as plain SQL.
        _tw1 = _time.perf_counter()
        with self._conn() as conn, conn.cursor() as cur:
            if company_id_scope:
                cur.execute("DELETE FROM financials WHERE company_id = %s", (company_id_scope,))
            else:
                cur.execute("DELETE FROM financials")
            self._insert_financials(cur, combined)
            conn.commit()
        logger.warning(f"[WH] write {len(combined)} rows to Postgres in {_time.perf_counter()-_tw1:.3f}s")

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

    # ── Bulk insert helper ────────────────────────────────────────────

    def _insert_financials(self, cur, df: pd.DataFrame) -> None:
        if df.empty:
            return
        df = df[FINANCIALS_COLUMNS].copy()
        df["version"] = df["version"].fillna(1).astype(int)
        df["is_active"] = df["is_active"].astype(bool)
        df["updated_on"] = pd.to_datetime(df["updated_on"], errors="coerce", utc=True).dt.tz_convert(None)
        rows = [tuple(None if pd.isna(v) else v for v in r) for r in df.itertuples(index=False, name=None)]
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO financials ({','.join(FINANCIALS_COLUMNS)}) VALUES %s",
            rows,
        )

    # ── Audit ───────────────────────────────────────────────────────

    def _append_audit(self, **kw) -> None:
        kw.setdefault("timestamp", datetime.utcnow())
        cols = ["ingestion_id", "company_id", "source_file", "rows_loaded",
                "rows_revised", "status", "notes", "timestamp"]
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO wh_audit_log ({','.join(cols)}) VALUES "
                f"({','.join(['%s']*len(cols))})",
                tuple(kw.get(c) for c in cols),
            )
            conn.commit()

    def read_audit_log(self) -> pd.DataFrame:
        if not self.paths.wh_audit.exists():
            return pd.DataFrame(columns=[f.name for f in AUDIT_SCHEMA])
        return pq.read_table(self.paths.wh_audit).to_pandas()

    def deactivate_period(self, company_id: str, period: str) -> int:
        """Delete all rows for (company_id, year=period). Used when an analyst
        deletes and saves — ensures the dashboard shows no data for that period
        instead of stale values. Returns the number of rows removed."""
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM financials WHERE company_id = %s AND year = %s",
                (company_id, period),
            )
            n = cur.rowcount
            conn.commit()
        logger.info(f"Removed {n} rows for {company_id}/{period}")
        return n

    def deactivate_all(self, company_id: str) -> int:
        """Delete ALL rows for company_id."""
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM financials WHERE company_id = %s", (company_id,))
            n = cur.rowcount
            conn.commit()
        logger.info(f"Removed all {n} rows for {company_id}")
        return n
