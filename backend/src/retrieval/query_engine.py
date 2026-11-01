"""
DuckDB query engine.
Provides a Python API + named query templates + arbitrary SQL execution
on top of the partitioned parquet warehouse.
"""

from __future__ import annotations
import json
import threading
import time
from pathlib import Path

import os
import duckdb
import pandas as pd

from utils import get_logger, Paths

logger = get_logger("query_engine")

_REFRESH_THROTTLE_SECS = 30  # re-register views at most once every 30 s
_HISTORY_CACHE_TTL     = 120 # company history cache TTL in seconds


class QueryEngine:
    """DuckDB façade over the parquet warehouse."""

    def __init__(self, paths: Paths):
        self.paths = paths
        self.con = duckdb.connect(database=":memory:")
        # A single DuckDB connection can only run ONE query at a time. The web
        # layer hammers this engine concurrently (the /dashboard/full endpoint
        # alone fires 4 parallel queries, plus peer/sector fan-outs on an 8-thread
        # pool). Without serialization those concurrent calls corrupt each other's
        # result buffers — returning another company's rows, empty frames, or
        # raising — which surfaced as blank/stale/partial dashboards. This re-entrant
        # lock serializes every actual DuckDB execute() (and view re-registration),
        # while the heavy pandas/engine compute still runs in parallel outside it.
        self._lock = threading.RLock()
        self._last_registered: float = 0.0
        self._history_cache: dict = {}   # {cache_key: (timestamp, DataFrame)}
        self._register_views()

    # ── View registration ──────────────────────────────────────────

    def _register_views(self):
        """Register parquet datasets as DuckDB views.
        If any parquet file is corrupted (empty / truncated), it is detected,
        quarantined (renamed .bad), and view registration retries with the
        remaining files. This prevents one bad file from blocking ALL companies.
        """
        with self._lock:
            self._register_views_locked()

    def _register_views_locked(self):
        """Attach the Postgres warehouse (Supabase) and expose the same view
        names callers always used (financials, financials_latest,
        company_master, sector_mapping, audit_log), now backed by Postgres
        tables instead of local parquet files.

        NOTE: pulling the full 567k-row `financials` table in one shot (either
        as a live SELECT * or materialized into a local table) is unreliable
        on Supabase's free tier — the pooler killed the connection mid-fetch
        in testing. Filtered, single-company/single-year queries (the normal
        access pattern) push their WHERE clause down to Postgres and return
        in a few seconds. Only unfiltered/wide fan-out queries (e.g. sector
        ranking across many companies) are at risk of being slow, since each
        company's query is a real network round-trip serialized through this
        connection's lock, where it used to be an instant local disk read."""
        database_url = os.environ.get("DATABASE_URL", "")
        try:
            self.con.execute("INSTALL postgres; LOAD postgres;")
            self.con.execute(
                "ATTACH IF NOT EXISTS ? AS pg (TYPE POSTGRES)", [database_url]
            )
            self.con.execute("CREATE OR REPLACE VIEW financials AS SELECT * FROM pg.financials")
            self.con.execute(
                "CREATE OR REPLACE VIEW financials_latest AS "
                "SELECT * FROM financials WHERE is_active = TRUE"
            )
            self.con.execute("CREATE OR REPLACE VIEW company_master AS SELECT * FROM pg.company_master")
            self.con.execute("CREATE OR REPLACE VIEW sector_mapping AS SELECT * FROM pg.sector_mapping")
            self.con.execute("CREATE OR REPLACE VIEW audit_log AS SELECT * FROM pg.wh_audit_log")
            logger.info("DuckDB views registered over Postgres: financials, financials_latest, "
                        "company_master, sector_mapping, audit_log")
        except Exception as e:
            logger.error(f"Postgres-backed view registration failed: {e}")

    def _quarantine_bad_parquets(self) -> list:
        """Scan every parquet file individually. Rename corrupted ones to .bad.
        Returns list of quarantined file paths."""
        bad = []
        with self._lock:
            for pf in sorted(self.paths.wh_financials.rglob("*.parquet")):
                try:
                    self.con.execute(f"SELECT COUNT(*) FROM read_parquet('{pf}')")
                except Exception:
                    bad_path = pf.with_suffix(".bad")
                    try:
                        pf.rename(bad_path)
                        bad.append(str(pf))
                        logger.warning(f"Quarantined: {pf} → {bad_path}")
                    except Exception as rename_err:
                        logger.error(f"Could not quarantine {pf}: {rename_err}")
        return bad

    def refresh(self, force: bool = False):
        """Re-register views after warehouse updates.
        Throttled to once per _REFRESH_THROTTLE_SECS unless force=True.
        Clears company history cache so stale data isn't served after an ingest.
        """
        if force or (time.monotonic() - self._last_registered) > _REFRESH_THROTTLE_SECS:
            self._register_views()
            with self._lock:
                self._history_cache.clear()  # invalidate after data changes

    # ── Generic SQL ────────────────────────────────────────────────

    def sql(self, query: str) -> pd.DataFrame:
        """Run an arbitrary SQL query and return a DataFrame.

        Serialized through self._lock: a single DuckDB connection is not safe for
        concurrent .execute() from multiple threads, and the web layer calls this
        from a thread pool. The lock is held only for the (fast) DuckDB scan; all
        downstream pandas work happens after it is released.
        """
        logger.debug(f"SQL: {query[:200].replace(chr(10), ' ')}…")
        with self._lock:
            return self.con.execute(query).df()

    # ── Built-in query methods ─────────────────────────────────────

    def get_company_history(self, company_id: str, category: str | None = None) -> pd.DataFrame:
        """All-latest financials for one company, optionally filtered by category.
        Results are cached for _HISTORY_CACHE_TTL seconds to avoid repeated DuckDB
        scans across multiple dashboard sub-requests (main, altman, cost-trend).
        """
        cache_key = f"{company_id}:{category or ''}"
        now = time.monotonic()
        if cache_key in self._history_cache:
            ts, cached_df = self._history_cache[cache_key]
            if now - ts < _HISTORY_CACHE_TTL:
                return cached_df.copy()

        where = f"company_id = '{company_id}' AND is_active = TRUE"
        if category:
            where += f" AND financial_category = '{category}'"
        result = self.sql(
            f"SELECT financial_item, financial_category, year, value, units, version "
            f"FROM financials WHERE {where} "
            f"ORDER BY year DESC, financial_item, version DESC"
        )
        self._history_cache[cache_key] = (now, result)
        return result.copy()

    def get_item_trend(self, company_id: str, financial_item: str,
                       category: str | None = None) -> pd.DataFrame:
        """Trend of one line item across years for one company.
        If the same canonical name lives in multiple categories (e.g. Altman Z vs P&L),
        all are returned unless `category` is provided."""
        where = (f"company_id = '{company_id}' "
                 f"AND financial_item = '{financial_item}' AND is_active = TRUE")
        if category:
            where += f" AND financial_category = '{category}'"
        return self.sql(
            f"SELECT year, financial_category, value, units, version, updated_on "
            f"FROM financials WHERE {where} "
            f"ORDER BY year DESC, financial_category"
        )

    def get_sector_companies(self, sector: str) -> pd.DataFrame:
        """List companies tagged with a given sector."""
        return self.sql(
            f"SELECT DISTINCT cm.company_id, cm.company_name, cm.ticker, sm.sub_sector "
            f"FROM company_master cm JOIN sector_mapping sm USING(company_id) "
            f"WHERE sm.sector = '{sector}'"
        )

    def get_peer_compare(self, sector: str, financial_item: str, year: str) -> pd.DataFrame:
        """All companies in `sector`: latest value of `financial_item` for `year`."""
        return self.sql(
            f"SELECT cm.company_id, cm.company_name, f.value, f.units "
            f"FROM company_master cm "
            f"JOIN sector_mapping sm USING(company_id) "
            f"JOIN financials f USING(company_id) "
            f"WHERE sm.sector = '{sector}' "
            f"  AND f.financial_item = '{financial_item}' "
            f"  AND f.year = '{year}' "
            f"  AND f.is_active = TRUE "
            f"ORDER BY f.value DESC"
        )

    def get_latest_filings(self, limit: int = 20) -> pd.DataFrame:
        """Most recent ingestion runs from audit log."""
        return self.sql(
            f"SELECT ingestion_id, company_id, source_file, rows_loaded, "
            f"rows_revised, status, timestamp "
            f"FROM audit_log ORDER BY timestamp DESC LIMIT {limit}"
        )

    def get_revision_history(self, company_id: str, financial_item: str, year: str) -> pd.DataFrame:
        """Full version history (active + inactive) for one cell of data."""
        return self.sql(
            f"SELECT version, value, units, is_active, source_file, updated_on "
            f"FROM financials WHERE company_id = '{company_id}' "
            f"AND financial_item = '{financial_item}' AND year = '{year}' "
            f"ORDER BY version"
        )

    # ── Saved query templates ──────────────────────────────────────

    def run_template(self, template_name: str, params: dict) -> pd.DataFrame:
        """
        Execute a saved .sql template from query_templates/.
        Template uses Python str.format() style placeholders: {company_id}, {year}, etc.
        """
        tpl = self.paths.query_dir / f"{template_name}.sql"
        if not tpl.exists():
            raise FileNotFoundError(f"Query template not found: {tpl}")
        with open(tpl) as f:
            sql = f.read()
        # Sanitise params (basic — caller is internal/analyst)
        safe = {k: str(v).replace("'", "''") for k, v in params.items()}
        return self.sql(sql.format(**safe))

    def list_templates(self) -> list:
        if not self.paths.query_dir.exists():
            return []
        return sorted([p.stem for p in self.paths.query_dir.glob("*.sql")])

    # ── Cleanup ────────────────────────────────────────────────────

    def close(self):
        self.con.close()
