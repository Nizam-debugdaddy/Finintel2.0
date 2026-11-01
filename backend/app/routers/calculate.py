"""
calculate.py — ROUTE ORDER IS CRITICAL.
Static-prefix routes (/warehouse, /invalidate, /all-companies) MUST precede /{company_id}/{period}.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import time as _time
from app.db.sqlite_db import get_db
from app.services.service_factory import get_fresh_service, invalidate_service_cache
import logging as _logging
_perf_log = _logging.getLogger("finintel.perf")

router = APIRouter()


@router.post("/warehouse/repair")
async def repair_warehouse():
    """
    Scans the entire parquet warehouse for corrupted files,
    quarantines them (renames to .bad), refreshes DuckDB views,
    and returns a summary. Safe to call at any time.
    """
    svc = get_fresh_service()
    try:
        bad_files = svc.engine._quarantine_bad_parquets()
        svc.engine.refresh()
        return {
            "status":       "ok",
            "quarantined":  bad_files,
            "message":      f"Removed {len(bad_files)} corrupted file(s). Warehouse views refreshed." if bad_files
                            else "No corrupted files found. Warehouse is healthy.",
        }
    except Exception as e:
        raise HTTPException(500, f"Repair failed: {e}")


@router.post("/warehouse/{company_id}")
async def calculate_from_warehouse(company_id: str):
    """Run analysis directly from existing warehouse data."""
    svc = get_fresh_service()
    try:
        result = svc.run_analysis(company_id)
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/invalidate/{company_id}")
async def invalidate_cache(
    company_id: str,
    period: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """
    Hard invalidation: deactivates warehouse rows so dashboard shows empty.
    If period given: deactivate only that period.
    If no period: deactivate ALL periods for the company.

    This is called after analyst deletes values and saves — ensures the
    warehouse (Parquet) reflects the deletion, not just SQLite staging.
    """
    svc = get_fresh_service()

    if period:
        n = svc.remove_period_from_warehouse(company_id, period)
        detail = f"Deactivated {n} warehouse rows for {company_id}/{period}"
    else:
        n = svc.remove_all_from_warehouse(company_id)
        detail = f"Deactivated {n} warehouse rows for {company_id} (all periods)"

    await db.execute(
        "INSERT INTO audit_log(event_type,company_id,detail) VALUES('INVALIDATE',?,?)",
        (company_id, detail)
    )
    await db.execute(
        "UPDATE versions SET is_active=0 WHERE company_id=?",
        (company_id,)
    )
    await db.commit()

    return {
        "status":     "invalidated",
        "company_id": company_id,
        "period":     period,
        "rows_deactivated": n,
        "detail":     detail,
    }


async def _analyze_company_core(company_id: str, db) -> dict:
    """
    Core per-company analyze logic. Shared by /all/{company_id} and /all-companies.
    Returns a result dict. Raises Exception (not HTTPException) on failure so
    /all-companies can catch per-company errors without aborting the whole batch.
    """
    _t0 = _time.perf_counter()
    svc = get_fresh_service()

    async with db.execute(
        "SELECT DISTINCT period_label FROM financial_inputs "
        "WHERE company_id=? AND value IS NOT NULL ORDER BY period_label",
        (company_id,)
    ) as cur:
        periods = [r["period_label"] for r in await cur.fetchall()]
    _perf_log.warning(f"[ANALYZE] {company_id} — {len(periods)} staged periods in {_time.perf_counter()-_t0:.3f}s")

    if not periods:
        result = svc.run_analysis(company_id)
        return {"status": "ok", "source": "warehouse", "periods": [], "result": result}

    all_staged: dict = {}
    for period in periods:
        async with db.execute(
            "SELECT financial_item, category, value, units, parent_item "
            "FROM financial_inputs "
            "WHERE company_id=? AND period_label=? AND value IS NOT NULL",
            (company_id, period)
        ) as cur:
            staged = [dict(r) for r in await cur.fetchall()]
        if staged:
            all_staged[period] = staged

    if not all_staged:
        result = svc.run_analysis(company_id)
        return {"status": "ok", "source": "warehouse", "periods": [], "result": result}

    ingested: list = []
    try:
        svc.ingest_all_periods(company_id, all_staged)
        ingested = list(all_staged.keys())
    except Exception as e:
        raise RuntimeError(f"Ingest failed for {company_id}: {e}")

    _svc = invalidate_service_cache()
    _svc._cache_invalidate(company_id)
    from app.routers.dashboard import invalidate_dashboard_caches
    invalidate_dashboard_caches(company_id)

    result = svc.run_analysis(company_id)
    _perf_log.warning(f"[ANALYZE] {company_id} — done in {_time.perf_counter()-_t0:.3f}s ({len(ingested)} periods)")

    await db.execute(
        "INSERT INTO audit_log(event_type,company_id,detail) VALUES('CALCULATE_ALL',?,?)",
        (company_id, f"Ingested periods: {','.join(ingested)}")
    )
    await db.commit()

    return {"status": "ok", "source": "staged", "periods": ingested, "result": result}


@router.post("/all-companies")
async def calculate_all_companies(db=Depends(get_db)):
    """
    Analyze ALL active companies in one click.
    Saves staged data → ingests to warehouse → runs analysis for every company.
    Companies are processed sequentially (DuckDB file-lock safety).
    """
    _t0 = _time.perf_counter()
    async with db.execute(
        "SELECT company_id FROM companies WHERE active_flag=1 ORDER BY company_id"
    ) as cur:
        company_ids = [r["company_id"] for r in await cur.fetchall()]

    if not company_ids:
        raise HTTPException(404, "No active companies found in the database")

    analyzed: list = []
    failed:   dict = {}

    for cid in company_ids:
        try:
            r = await _analyze_company_core(cid, db)
            analyzed.append({"company_id": cid, "periods": r.get("periods", [])})
        except Exception as e:
            _perf_log.warning(f"[ANALYZE-ALL] {cid} failed: {e}")
            failed[cid] = str(e)

    total_s = _time.perf_counter() - _t0
    _perf_log.warning(f"[ANALYZE-ALL] Done: {len(analyzed)} ok, {len(failed)} failed in {total_s:.1f}s")

    return {
        "status":   "ok" if not failed else "partial",
        "analyzed": analyzed,
        "failed":   failed,
        "total":    len(company_ids),
        "elapsed_s": round(total_s, 1),
    }


@router.post("/all/{company_id}")
async def calculate_all_periods(company_id: str, db=Depends(get_db)):
    """
    Ingest ALL staged periods for a company in one shot, then run analysis once.
    Called when analyst clicks Analyze — ensures every year is computed, not
    just the currently selected period.
    """
    try:
        return await _analyze_company_core(company_id, db)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")


async def calculate(company_id: str, period: str, db=Depends(get_db)):
    """Ingest staged data and run Cost Structure + Altman Z analysis."""
    svc = get_fresh_service()
    async with db.execute(
        "SELECT financial_item, category, value, units, parent_item "
        "FROM financial_inputs "
        "WHERE company_id=? AND period_label=? AND value IS NOT NULL",
        (company_id, period)
    ) as cur:
        staged = [dict(r) for r in await cur.fetchall()]

    if staged:
        try:
            ingest_result = svc.ingest_from_staging(company_id, period, staged)
        except Exception as e:
            raise HTTPException(500, f"Ingest failed: {e}")
        source = "staged"
    else:
        ingest_result = {"rows_loaded": 0, "note": "using warehouse data"}
        source = "warehouse"

    try:
        result = svc.run_analysis(company_id)
        await db.execute(
            "INSERT INTO audit_log(event_type,company_id,period_label,rows_affected) "
            "VALUES('CALCULATE',?,?,?)",
            (company_id, period, ingest_result.get("rows_loaded", 0))
        )
        await db.commit()
        return {"status": "ok", "source": source, "ingest": ingest_result, "result": result}
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")
