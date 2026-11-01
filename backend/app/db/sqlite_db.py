"""
SQLite metadata layer.
Stores companies, sectors (many-to-many), financial input staging,
versions, and audit_log.
"""
import aiosqlite
from app.config import settings

DB = settings.DB_PATH

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS companies (
    company_id   TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    ticker       TEXT DEFAULT '',
    isin         TEXT DEFAULT '',
    active_flag  INTEGER DEFAULT 1,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sectors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL REFERENCES companies(company_id),
    sector       TEXT NOT NULL,
    sub_sector   TEXT DEFAULT '',
    UNIQUE(company_id, sector)
);

CREATE TABLE IF NOT EXISTS financial_inputs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id     TEXT NOT NULL,
    period_label   TEXT NOT NULL,
    financial_item TEXT NOT NULL,
    category       TEXT NOT NULL,
    value          REAL,
    units          TEXT DEFAULT 'INR Million',
    parent_item    TEXT DEFAULT NULL,
    sort_order     INTEGER DEFAULT 0,
    is_derived     INTEGER DEFAULT 0,
    saved_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, period_label, financial_item, category)
);

CREATE INDEX IF NOT EXISTS idx_fi_company   ON financial_inputs(company_id);
CREATE INDEX IF NOT EXISTS idx_fi_period    ON financial_inputs(period_label);
CREATE INDEX IF NOT EXISTS idx_fi_category  ON financial_inputs(category);
CREATE INDEX IF NOT EXISTS idx_fi_co_period ON financial_inputs(company_id, period_label);
CREATE INDEX IF NOT EXISTS idx_sectors_co   ON sectors(company_id);

CREATE TABLE IF NOT EXISTS versions (
    version_id   TEXT PRIMARY KEY,
    company_id   TEXT NOT NULL,
    period_label TEXT NOT NULL,
    version_num  INTEGER NOT NULL,
    is_active    INTEGER DEFAULT 1,
    note         TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT NOT NULL,
    company_id   TEXT DEFAULT '',
    period_label TEXT DEFAULT '',
    rows_affected INTEGER DEFAULT 0,
    detail       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()
    # Seed companies and sectors from existing parquet warehouse
    await _seed_from_warehouse()
    await init_extra_tables()

async def _seed_from_warehouse():
    """Populate SQLite from existing Parquet warehouse if tables are empty."""
    import pandas as pd
    import pyarrow.parquet as pq
    from pathlib import Path

    cm_path = settings.WAREHOUSE_PATH / "company_master.parquet"
    sm_path = settings.WAREHOUSE_PATH / "sector_mapping.parquet"

    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM companies")
        row = await cursor.fetchone()
        if row[0] > 0:
            return  # already seeded

        if cm_path.exists():
            df = pq.read_table(str(cm_path)).to_pandas()
            for _, r in df.iterrows():
                await db.execute(
                    "INSERT OR IGNORE INTO companies(company_id,company_name,ticker,isin,active_flag) VALUES(?,?,?,?,?)",
                    (str(r.get("company_id","")), str(r.get("company_name","")),
                     str(r.get("ticker","")), str(r.get("isin","")), 1)
                )
        if sm_path.exists():
            df = pq.read_table(str(sm_path)).to_pandas()
            for _, r in df.iterrows():
                await db.execute(
                    "INSERT OR IGNORE INTO sectors(company_id,sector,sub_sector) VALUES(?,?,?)",
                    (str(r.get("company_id","")), str(r.get("sector","")), str(r.get("sub_sector","")))
                )
        await db.commit()

async def get_db():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        yield db

EXTRA_TABLES = """
CREATE TABLE IF NOT EXISTS analyst_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL,
    period_label TEXT NOT NULL,
    page         TEXT DEFAULT 'general',
    note         TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS export_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   TEXT NOT NULL,
    format       TEXT NOT NULL,
    status       TEXT DEFAULT 'pending',
    file_path    TEXT DEFAULT '',
    error_msg    TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

async def init_extra_tables():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(EXTRA_TABLES)
        await db.commit()
