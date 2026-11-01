"""
Postgres (Supabase) metadata layer.
Stores companies, sectors (many-to-many), financial input staging,
versions, and audit_log.

Keeps the same public interface the routers were written against
(aiosqlite-style: db.execute(sql, params) with `?` placeholders,
async-with cursors, db.commit() as a no-op) so router code needed no changes
when the backing store moved from SQLite to Postgres.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg
from app.config import settings

DB = settings.DATABASE_URL

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # statement_cache_size=0: Supavisor's transaction-mode pooler doesn't
        # support asyncpg's prepared-statement caching (classic pgbouncer issue) —
        # caching causes "prepared statement already exists" under concurrent use.
        _pool = await asyncpg.create_pool(DB, min_size=1, max_size=5, statement_cache_size=0)
    return _pool


def _translate(sql: str) -> str:
    """SQLite `?` placeholders -> Postgres `$1, $2, ...` (positional, in order)."""
    out = []
    n = 0
    for ch in sql:
        if ch == "?":
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ExecCtx:
    """Supports both `await db.execute(...)` and `async with db.execute(...) as cur:`."""

    def __init__(self, conn, sql, params):
        self._conn = conn
        self._sql = _translate(sql)
        self._params = tuple(params) if params else ()

    async def _run(self) -> _Cursor:
        rows = await self._conn.fetch(self._sql, *self._params)
        return _Cursor(rows)

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, *exc):
        return False


class PGConn:
    """Mimics the subset of aiosqlite.Connection the routers use."""

    def __init__(self, conn):
        self._conn = conn
        self.row_factory = None  # aiosqlite compat no-op; asyncpg.Record already supports dict()/[]

    def execute(self, sql, params=()):
        return _ExecCtx(self._conn, sql, params)

    async def commit(self):
        pass  # autocommit outside explicit transactions

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@asynccontextmanager
async def connect(_dsn=None):
    """Drop-in replacement for `aiosqlite.connect(DB)`."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        yield PGConn(conn)


async def get_db():
    async with connect() as db:
        yield db


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
    id           SERIAL PRIMARY KEY,
    company_id   TEXT NOT NULL REFERENCES companies(company_id),
    sector       TEXT NOT NULL,
    sub_sector   TEXT DEFAULT '',
    UNIQUE(company_id, sector)
);

CREATE TABLE IF NOT EXISTS financial_inputs (
    id             SERIAL PRIMARY KEY,
    company_id     TEXT NOT NULL,
    period_label   TEXT NOT NULL,
    financial_item TEXT NOT NULL,
    category       TEXT NOT NULL,
    value          DOUBLE PRECISION,
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
    id           SERIAL PRIMARY KEY,
    event_type   TEXT NOT NULL,
    company_id   TEXT DEFAULT '',
    period_label TEXT DEFAULT '',
    rows_affected INTEGER DEFAULT 0,
    detail       TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

EXTRA_TABLES = """
CREATE TABLE IF NOT EXISTS analyst_notes (
    id           SERIAL PRIMARY KEY,
    company_id   TEXT NOT NULL,
    period_label TEXT NOT NULL,
    page         TEXT DEFAULT 'general',
    note         TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS export_log (
    id           SERIAL PRIMARY KEY,
    company_id   TEXT NOT NULL,
    format       TEXT NOT NULL,
    status       TEXT DEFAULT 'pending',
    file_path    TEXT DEFAULT '',
    error_msg    TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES)
        await conn.execute(EXTRA_TABLES)
    await _seed_from_warehouse()


async def _seed_from_warehouse():
    """Populate companies/sectors from the Postgres warehouse tables if empty."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM companies")
        if count and count > 0:
            return  # already seeded

        if await conn.fetchval(
            "SELECT to_regclass('public.company_master')"
        ):
            rows = await conn.fetch("SELECT company_id, company_name, ticker, isin FROM company_master")
            for r in rows:
                await conn.execute(
                    "INSERT INTO companies(company_id,company_name,ticker,isin,active_flag) "
                    "VALUES($1,$2,$3,$4,1) ON CONFLICT (company_id) DO NOTHING",
                    str(r["company_id"] or ""), str(r["company_name"] or ""),
                    str(r["ticker"] or ""), str(r["isin"] or ""),
                )
        if await conn.fetchval(
            "SELECT to_regclass('public.sector_mapping')"
        ):
            rows = await conn.fetch("SELECT company_id, sector, sub_sector FROM sector_mapping")
            for r in rows:
                await conn.execute(
                    "INSERT INTO sectors(company_id,sector,sub_sector) VALUES($1,$2,$3) "
                    "ON CONFLICT (company_id, sector) DO NOTHING",
                    str(r["company_id"] or ""), str(r["sector"] or ""), str(r["sub_sector"] or ""),
                )
