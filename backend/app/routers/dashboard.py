from fastapi import APIRouter, HTTPException, Query, Depends
from app.services.service_factory import get_service, get_fresh_service
from app.db.sqlite_db import get_db
import math
import asyncio
import time as _time
import logging as _logging
from concurrent.futures import ThreadPoolExecutor
_perf_log = _logging.getLogger("finintel.perf")

_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dash")

# ── Short-TTL response caches (cleared by cache_invalidate after Analyze) ─────
_COST_TREND_CACHE: dict = {}   # "{company_id}:{report_type}" → (timestamp, result)
_RATIOS_CACHE: dict     = {}   # "{company_id}:{report_type}" → (timestamp, result)
_CACHE_TTL = 90  # seconds — safe because data only changes after Analyze


def invalidate_dashboard_caches(company_id: str):
    """Call this after Analyze/Ingest so cost-trend and ratios refresh immediately."""
    for cache in (_COST_TREND_CACHE, _RATIOS_CACHE):
        stale = [k for k in cache if k.startswith(f"{company_id}:")]
        for k in stale:
            del cache[k]

router = APIRouter()

# ── RE aliases checked in priority order ─────────────────────────────────────
RE_ALIASES = [
    "Retained Earnings", "Reserves & Surplus",
    "Retained Profit", "Retained Earnings / Deficit",
]


async def _load_re_staging(db, company_id: str) -> dict:
    """Load Retained Earnings values from SQLite staging for all periods.
    Returns {period_label: {"value": float, "field": str}}.
    First alias match per period wins — same priority as the engine.
    Works WITHOUT re-running Analyze.
    """
    placeholders = ",".join("?" * len(RE_ALIASES))
    result: dict = {}
    async with db.execute(
        f"""SELECT period_label, financial_item, value
            FROM financial_inputs
            WHERE company_id = ?
              AND financial_item IN ({placeholders})
              AND value IS NOT NULL
            ORDER BY period_label""",
        (company_id, *RE_ALIASES)
    ) as cur:
        for row in await cur.fetchall():
            period_lbl, field, val = row
            if period_lbl not in result:          # first alias wins per period
                result[period_lbl] = {"value": float(val), "field": field}
    return result


async def _load_altman_staging(db, company_id: str) -> dict:
    """Load ALL Altman Z input rows from SQLite staging for all periods.
    Returns {period_label: {financial_item: float}}.
    Ensures the Altman Z decomposition reflects the latest Data Input values
    even when the warehouse is stale (user hasn't re-run Analyze).
    """
    result: dict = {}
    async with db.execute(
        """SELECT period_label, financial_item, value
           FROM financial_inputs
           WHERE company_id = ? AND category = 'Altman Z' AND value IS NOT NULL
           ORDER BY period_label""",
        (company_id,)
    ) as cur:
        for row in await cur.fetchall():
            period_lbl, item, val = row
            if period_lbl not in result:
                result[period_lbl] = {}
            result[period_lbl][item] = float(val)
    return result

def _clean(v):
    if v is None: return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return v

def _clean_records(records):
    return [{k: _clean(v) if isinstance(v, float) else v for k, v in r.items()} for r in records]


@router.get("/{company_id}")
async def get_dashboard(
    company_id: str,
    period: str = Query(None),
    report_type: str = Query("consolidated"),
    db=Depends(get_db),
):
    _d0 = _time.perf_counter()
    try:
        svc = get_service()
        re_staging     = await _load_re_staging(db, company_id)
        altman_staging = await _load_altman_staging(db, company_id)
        _perf_log.warning(f"[DASH] {company_id} staging loaded in {_time.perf_counter()-_d0:.3f}s")
        _dc = _time.perf_counter()
        data = svc.get_dashboard_data(
            company_id, period=period, report_type=report_type,
            re_staging=re_staging, altman_staging=altman_staging,
        )
        _perf_log.warning(f"[DASH] {company_id} get_dashboard_data done in {_time.perf_counter()-_dc:.3f}s, total {_time.perf_counter()-_d0:.3f}s")
        if not data:
            return {
                "company_id": company_id, "kpis": {}, "trend": {},
                "cost_structure": [], "years": [],
                "message": "No data — enter data in grid and click Analyze",
            }
        return data
    except Exception as e:
        # Surface the real error message (helps diagnose warehouse/view issues)
        import traceback as _tb
        detail = f"{e}\n{_tb.format_exc()}"
        raise HTTPException(500, detail)


@router.get("/{company_id}/altman")
async def get_altman_detail_route(
    company_id: str,
    period: str = Query(None),
    db=Depends(get_db),
):
    _a0 = _time.perf_counter()
    try:
        svc = get_service()
        re_staging     = await _load_re_staging(db, company_id)
        altman_staging = await _load_altman_staging(db, company_id)
        result = svc.get_altman_detail(
            company_id, period=period,
            re_staging=re_staging, altman_staging=altman_staging,
        )
        _perf_log.warning(f"[ALTMAN] {company_id} get_altman_detail done in {_time.perf_counter()-_a0:.3f}s")
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/{company_id}/health-score")
async def health_score(company_id: str, period: str = Query(None)):
    try:
        svc = get_service()
        data = svc.get_dashboard_data(company_id, period=period)
        kpis = data.get("kpis", {})
        score = 0
        components = []
        yoy    = (kpis.get("revenue") or {}).get("yoy")
        g = min(max((yoy or 0) / 20 * 25, 0), 25)
        score += g
        components.append({"name": "Growth",             "score": round(g, 1), "max": 25, "value": yoy})
        margin = (kpis.get("ebitda") or {}).get("margin")
        p = min(max((margin or 0) / 40 * 35, 0), 35)
        score += p
        components.append({"name": "Profitability",      "score": round(p, 1), "max": 35, "value": margin})
        z = (kpis.get("altman_z") or {}).get("value")
        b = min(max((z or 0) / 5 * 40, 0), 40) if z else 0
        score += b
        components.append({"name": "Bankruptcy Safety",  "score": round(b, 1), "max": 40, "value": z})
        grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
        return {"company_id": company_id, "total_score": round(score, 1), "grade": grade, "components": components}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Peer endpoints — MUST come before /{company_id} routes ──────────

@router.get("/peer/multi")
async def multi_company_peer(
    companies: str = Query(...),
    metrics: str   = Query(...),
    period: str    = Query("FY25"),
    report_type: str = Query("consolidated"),
):
    """Compare multiple companies across metrics for a period.
    Computes derived metrics (EBIT, margins, ratios) server-side.
    """
    try:
        svc = get_service()
        co_list  = [c.strip() for c in companies.split(",") if c.strip()]
        met_list = [m.strip() for m in metrics.split(",") if m.strip()]

        METRIC_MAP = {
            "Revenue from Operations": ("revenue",    "value"),
            "Revenue Growth":          ("revenue",    "growth_pct"),
            "EBITDA":                  ("ebitda",     "value"),
            "EBITDA Margin":           ("ebitda",     "margin"),
            "EBIT":                    ("ebit",       "value"),
            "EBIT Margin":             ("ebit",       "margin"),
            "PAT":                     ("pat",        "value"),
            "PAT Margin":              ("pat",        "margin"),
            "Total Assets":            ("total_assets","value"),
            "Net Worth":               ("net_worth",  "value"),
            "Current Ratio":           ("current_ratio","value"),
            "Working Capital":         ("working_capital","value"),
            "ROE":                     ("roe",        "value"),
            "Altman Z Score":          ("altman_z",   "value"),
        }

        def _fetch_company(cid: str) -> dict | None:
            dash = svc.get_dashboard_data(cid, period=period, report_type=report_type)
            if not dash:
                return None
            kpis = dash.get("kpis", {})
            row: dict = {"company_id": cid}
            for m in met_list:
                if m in METRIC_MAP:
                    kpi_key, sub_key = METRIC_MAP[m]
                    row[m] = _clean((kpis.get(kpi_key) or {}).get(sub_key))
                else:
                    df_h = svc.engine.get_company_history(cid)
                    sub = df_h[(df_h["financial_item"] == m) & (df_h["year"] == period)]
                    row[m] = _clean(float(sub["value"].iloc[0])) if not sub.empty else None
            return row

        loop = asyncio.get_event_loop()
        rows = await asyncio.gather(
            *[loop.run_in_executor(_executor, _fetch_company, cid) for cid in co_list],
            return_exceptions=True,
        )
        return [r for r in rows if isinstance(r, dict)]
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/peer/{sector}/{item}/{period}")
async def peer_comparison(sector: str, item: str, period: str):
    try:
        svc = get_service()
        sector_clause = "" if sector.upper() == "ALL" else f"AND s.sector = '{sector}'"
        df = svc.engine.sql(f"""
            SELECT DISTINCT c.company_id, c.company_name, f.value, f.units
            FROM financials_latest f
            JOIN sector_mapping s ON f.company_id = s.company_id
            JOIN company_master c ON f.company_id = c.company_id
            WHERE f.financial_item = '{item}'
              AND f.year = '{period}'
              {sector_clause}
            ORDER BY f.value DESC
        """)
        return _clean_records(df.to_dict("records"))
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/sector/{sector}/ranking")
async def sector_ranking(sector: str, period: str = "FY25"):
    """sector='ALL' returns all companies across sectors."""
    try:
        svc  = get_service()
        sector_clause = "" if sector.upper() == "ALL" else f"AND s.sector = '{sector}'"
        df = svc.engine.sql(f"""
            SELECT c.company_id, c.company_name,
                MAX(CASE WHEN f.financial_item='Revenue from Operations' THEN f.value END) as revenue,
                MAX(CASE WHEN f.financial_item='EBITDA'                  THEN f.value END) as ebitda,
                MAX(CASE WHEN f.financial_item='PAT'                     THEN f.value END) as pat,
                MAX(CASE WHEN f.financial_item='Total Assets'            THEN f.value END) as total_assets
            FROM financials_latest f
            JOIN sector_mapping s ON f.company_id = s.company_id
            JOIN company_master c ON f.company_id = c.company_id
            WHERE f.year = '{period}' {sector_clause}
            GROUP BY c.company_id, c.company_name
            ORDER BY revenue DESC NULLS LAST
        """)
        # Compute Altman Z per company — run all in parallel (ThreadPoolExecutor)
        # Previously sequential: 4 companies × ~200ms each = ~800ms total
        # Now parallel: max(200ms each) ≈ 200ms total regardless of company count
        records = _clean_records(df.to_dict("records"))
        loop = asyncio.get_event_loop()

        def _enrich(r: dict) -> dict:
            try:
                dash = svc.get_dashboard_data(r["company_id"], period=period)
                r["altman_z"] = _clean((dash.get("kpis") or {}).get("altman_z", {}).get("value"))
            except Exception:
                r["altman_z"] = None
            ebitda = r.get("ebitda"); revenue = r.get("revenue")
            r["ebitda_margin"] = round(ebitda/revenue*100, 2) if (ebitda and revenue) else None
            return r

        enriched = await asyncio.gather(
            *[loop.run_in_executor(_executor, _enrich, r) for r in records],
            return_exceptions=True,
        )
        return [r for r in enriched if isinstance(r, dict)]
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Sync helpers (called directly or via thread executor) ─────────────────────

def _compute_cost_trend_sync(svc, company_id: str, report_type: str) -> dict:
    """
    Compute multi-year cost-structure trend in ONE CostStructureAnalysis run.
    Previously called _get_cost_structure() once per year (N engine runs → slow).
    Now: load pnl_wide once, run CostStructureAnalysis once, slice each year.
    """
    from cost_structure_analysis import CostStructureAnalysis
    from app.routers.peer import COST_SEGMENTS, COST_COLORS

    cats_to_try = (["P&L Consolidated", "P&L"] if report_type == "consolidated"
                   else ["P&L Standalone", "P&L"])
    pnl, all_years = None, []
    for cat in cats_to_try:
        _pnl, _years = svc.reshaper.get_pnl_wide(company_id, cat)
        if not _pnl.empty:
            pnl = _pnl
            all_years = sorted([y for y in _years if y.startswith("FY")])
            break

    if pnl is None or pnl.empty or not all_years:
        return {"years": [], "revenue": {}, "segments": {}, "colors": {}, "ebitda_margin": {}}

    # Single engine run for ALL years at once
    cs_result = CostStructureAnalysis(pnl, all_years).run()
    direct_df = cs_result["direct"]

    yearly: dict = {}
    for yr in all_years:
        if yr not in direct_df.columns:
            continue
        lookup: dict = {}
        for _, row in direct_df.iterrows():
            lbl = str(row.get("Particulars", ""))
            v = row.get(yr)
            if v is not None:
                try:
                    lookup[lbl] = float(v)
                except (TypeError, ValueError):
                    pass

        result: dict = {}
        for seg_name, src_keys in COST_SEGMENTS:
            total = sum(lookup.get(k, 0) for k in src_keys)
            result[seg_name] = round(total, 2) if total else None
        result["_revenue"] = lookup.get("Revenue from Ops")
        tc = lookup.get("Total Cost")
        if not tc:
            tc = sum((result.get(seg) or 0) for seg, _ in COST_SEGMENTS
                     if seg != "Operational PBT") or None
        result["_total_cost"] = tc
        yearly[yr] = result

    if not yearly:
        return {"years": [], "revenue": {}, "segments": {}, "colors": {}, "ebitda_margin": {}}

    # 5Y average
    avg_years = all_years[-5:]
    avg_data: dict = {}
    for key in [s for s, _ in COST_SEGMENTS] + ["_revenue", "_total_cost"]:
        vals = [yearly[yr].get(key) for yr in avg_years
                if yr in yearly and yearly[yr].get(key) is not None]
        avg_data[key] = sum(vals) / len(vals) if vals else None

    display_years = all_years + ["5Y Avg"]
    yearly["5Y Avg"] = avg_data

    revenue: dict = {}
    segments: dict = {s: {} for s, _ in COST_SEGMENTS}
    for yr in display_years:
        d = yearly.get(yr, {})
        rv = d.get("_revenue") or 0
        revenue[yr] = round(rv, 0) if rv else None
        for seg, _ in COST_SEGMENTS:
            raw = d.get(seg) or 0
            pct = round(raw / rv * 100, 2) if rv and raw else 0
            segments[seg][yr] = pct

    colors = {seg: COST_COLORS[i % len(COST_COLORS)] for i, (seg, _) in enumerate(COST_SEGMENTS)}

    ebitda_margin: dict = {}
    for yr in all_years:
        d = yearly.get(yr, {})
        rv_raw = d.get("_revenue") or 0
        if rv_raw > 0:
            ebitda_raw = ((d.get("Operational PBT") or 0)
                          + (d.get("Finance Costs") or 0)
                          + (d.get("Depreciation & Amortization") or 0))
            # Show the margin for EVERY year with revenue — including loss years
            # where EBITDA is negative (e.g. ACCORDD ORGANICS FY23). Previously a
            # `> 0` guard silently dropped the badge for negative-EBITDA years.
            ebitda_margin[yr] = round(ebitda_raw / rv_raw * 100, 1)
    avg_em = [ebitda_margin[y] for y in all_years[-5:] if y in ebitda_margin]
    if avg_em:
        ebitda_margin["5Y Avg"] = round(sum(avg_em) / len(avg_em), 1)

    return {
        "years":         display_years,
        "revenue":       revenue,
        "segments":      segments,
        "colors":        colors,
        "ebitda_margin": ebitda_margin,
    }


def _load_re_overrides_sync(company_id: str) -> dict:
    """Load analyst-entered Retained Earnings from SQLite staging (blocking, for threads)."""
    try:
        import sqlite3 as _sqlite3
        from app.config import settings as _settings
        _RE_FIELDS = [
            "Retained Earnings", "Reserves & Surplus",
            "Retained Profit", "Retained Earnings / Deficit",
        ]
        placeholders = ",".join("?" * len(_RE_FIELDS))
        with _sqlite3.connect(str(_settings.DB_PATH)) as _conn:
            rows = _conn.execute(
                f"""SELECT period_label, financial_item, value
                    FROM financial_inputs
                    WHERE company_id = ?
                      AND financial_item IN ({placeholders})
                      AND value IS NOT NULL
                    ORDER BY period_label""",
                (company_id, *_RE_FIELDS)
            ).fetchall()
        result: dict = {}
        for period_lbl, _field, val in rows:
            if period_lbl not in result:   # first alias wins
                result[period_lbl] = float(val)
        return result
    except Exception:
        return {}


def _compute_financial_ratios_sync(svc, company_id: str, report_type: str) -> dict:
    """Financial ratios helper — extracted so it can be called from /full."""
    import traceback
    from bankruptcy_analysis import BankruptcyAnalysis

    def _c(v):
        if v is None: return None
        try:
            f = float(v)
            return None if math.isnan(f) or math.isinf(f) else round(f, 2)
        except Exception:
            return None

    rspr    = svc.reshaper
    pnl_cat = "P&L Consolidated" if report_type == "consolidated" else "P&L Standalone"
    az_df,  az_years  = rspr.get_altman_wide(company_id)
    pnl_df, pnl_years = rspr.get_pnl_wide(company_id, pnl_cat)

    if az_df is None or az_df.empty:
        return {"company_id": company_id, "years": [], "rows": []}

    # Years that actually have warehouse data — the engine computes ratios for these.
    # (get_altman_wide drops FY19 from az_years because the engine uses it only as the
    # prior-year reference for FY20; az_df still carries an FY19 column when FY19 has
    # data, so derive the data years from the frame's real FY columns.)
    data_years = sorted(
        [c for c in az_df.columns if str(c).startswith("FY")], reverse=True
    ) or list(az_years)

    # Mirror generate_excel: pass staged RE so Altman Z matches the Excel output.
    re_overrides = _load_re_overrides_sync(company_id)
    ba      = BankruptcyAnalysis(az_df, pnl_df, data_years, re_overrides=re_overrides)
    summary = ba._build_summary()

    def _get(label, units):
        rows = summary[(summary["Particulars"] == label) & (summary["Units"] == units)]
        if rows.empty: return {}
        row = rows.iloc[0]
        return {yr: _c(row.get(yr)) for yr in data_years}

    # Always expose FY19 in the year dropdown even before its data is entered. FY19
    # then renders as "—" in the table, and fills in automatically once FY19 values
    # are entered in Data Input and Analyzed (it joins data_years above).
    years_sorted = sorted(
        set(data_years) | {"FY19"}, key=lambda y: int(y[2:]), reverse=True
    )

    RATIOS = [
        ("Current Ratio",              "Ratio", "Ratio"),
        ("DSCR - On Interest Basis",   "Ratio", "Ratio"),
        ("Debt to Asset Ratio",        "Ratio", "Ratio"),
        ("Interest Coverage Ratio",    "Ratio", "Ratio"),
        ("Cash Conversion Cycle",      "Days",  "Days"),
        ("Creditors (Payables) Days",  "Days",  "Days"),
        ("Debtors (Receivables) Days", "Days",  "Days"),
        ("Inventory Days",             "Days",  "Days"),
    ]
    LABEL_MAP = {
        "Current Ratio":              ("Current Ratio",            "Ratio"),
        "DSCR - On Interest Basis":   ("DSCR - On Interest Basis", "Ratio"),
        "Debt to Asset Ratio":        None,
        "Interest Coverage Ratio":    None,
        "Cash Conversion Cycle":      ("Cash Conversion Cycle",    "Days"),
        "Creditors (Payables) Days":  ("Creditors (Payables)",     "Days"),
        "Debtors (Receivables) Days": ("Debtors (Receivables)",    "Days"),
        "Inventory Days":             ("Inventory",                "Days"),
    }

    inline = {"Debt to Asset Ratio": {}, "Interest Coverage Ratio": {}}
    for yr in data_years:
        def A(k, d=0, _yr=yr):
            try:
                if k in az_df.index and _yr in az_df.columns:
                    v = az_df.loc[k, _yr]
                    return float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else d
            except Exception: pass
            return d
        ta  = A("Total Assets")
        nw  = A("Net Worth", None)
        ebitda = A("EBITDA");  dep_a = A("Depreciation and Amortisation")
        if dep_a:
            dep = dep_a
        else:
            try:
                dep = (float(pnl_df.loc["Depreciation & amortisation", yr]) / 10
                       if pnl_df is not None and "Depreciation & amortisation" in pnl_df.index
                       and yr in pnl_df.columns else 0)
            except Exception: dep = 0
        ebit = ebitda - dep
        fc   = A("Finance costs") or A("Finance Costs") or 0
        # Debt to Asset Ratio = Total Liabilities / Total Assets = (Total Assets - Net Worth) / Total Assets
        if ta and ta != 0 and nw is not None:
            inline["Debt to Asset Ratio"][yr] = round((ta - nw) / ta, 3)
        if fc and fc != 0 and ebit:
            inline["Interest Coverage Ratio"][yr] = round(ebit / fc, 2)

    rows = []
    for label, unit, _ in RATIOS:
        mapped = LABEL_MAP.get(label)
        if mapped is None:
            values = {yr: _c(inline.get(label, {}).get(yr)) for yr in years_sorted}
        else:
            part_vals = _get(*mapped)
            values = {yr: part_vals.get(yr) for yr in years_sorted}
        rows.append({"label": label, "unit": unit, "values": values})

    # years        = full dropdown list (includes FY19 even when empty)
    # data_years   = years that actually have data — used by the UI to default the
    #                "From" selector to the oldest NON-empty year (so FY19 stays
    #                selectable but isn't shown by default until it has values).
    return {"company_id": company_id, "years": years_sorted,
            "data_years": data_years, "rows": rows}


# ── Multi-year cost structure trend for dashboard ─────────────────────────────
@router.get("/{company_id}/cost-trend")
async def dashboard_cost_trend(
    company_id: str,
    report_type: str = "consolidated",
):
    """Cost structure trend — single CostStructureAnalysis run covers all years."""
    cache_key = f"{company_id}:{report_type}"
    now = _time.monotonic()
    if cache_key in _COST_TREND_CACHE:
        ts, val = _COST_TREND_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            return val
    svc = get_service()
    result = _compute_cost_trend_sync(svc, company_id, report_type)
    _COST_TREND_CACHE[cache_key] = (_time.monotonic(), result)
    return result


@router.get("/{company_id}/financial-ratios")
async def get_financial_ratios(
    company_id: str,
    report_type: str = "consolidated",
):
    """Financial Ratios table — delegates to helper, adds TTL cache."""
    cache_key = f"{company_id}:{report_type}"
    now = _time.monotonic()
    if cache_key in _RATIOS_CACHE:
        ts, val = _RATIOS_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            return val
    try:
        svc = get_service()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor,
            lambda: _compute_financial_ratios_sync(svc, company_id, report_type))
        _RATIOS_CACHE[cache_key] = (_time.monotonic(), result)
        return result
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500,
            detail=f"Financial ratios: {e}\n{traceback.format_exc()}")


@router.get("/{company_id}/full")
async def get_dashboard_full(
    company_id: str,
    period: str = Query(None),
    report_type: str = Query("consolidated"),
    db=Depends(get_db),
):
    """
    Single endpoint that returns dashboard + altman + cost_trend + financial_ratios.
    Runs all four computations in parallel via the thread executor, eliminating
    3 HTTP round-trips and sharing staging data across all four.

    The cost_trend computation uses a single CostStructureAnalysis.run() for all
    years instead of the previous per-year loop — the dominant bottleneck.
    """
    re_staging     = await _load_re_staging(db, company_id)
    altman_staging = await _load_altman_staging(db, company_id)
    svc  = get_service()
    loop = asyncio.get_event_loop()

    # Check caches for the two expensive computations
    ct_key = f"{company_id}:{report_type}"; now = _time.monotonic()
    cached_ct = ((_COST_TREND_CACHE[ct_key][1]) if ct_key in _COST_TREND_CACHE
                 and now - _COST_TREND_CACHE[ct_key][0] < _CACHE_TTL else None)
    cached_rt = ((_RATIOS_CACHE[ct_key][1]) if ct_key in _RATIOS_CACHE
                 and now - _RATIOS_CACHE[ct_key][0] < _CACHE_TTL else None)

    # Build futures — skip executor for cache hits
    dash_f   = loop.run_in_executor(_executor, lambda: svc.get_dashboard_data(
        company_id, period=period, report_type=report_type,
        re_staging=re_staging, altman_staging=altman_staging))
    altman_f = loop.run_in_executor(_executor, lambda: svc.get_altman_detail(
        company_id, period=period,
        re_staging=re_staging, altman_staging=altman_staging))
    ct_f     = (asyncio.get_event_loop().run_in_executor(None, lambda: cached_ct)
                if cached_ct is not None
                else loop.run_in_executor(_executor,
                    lambda: _compute_cost_trend_sync(svc, company_id, report_type)))
    rt_f     = (asyncio.get_event_loop().run_in_executor(None, lambda: cached_rt)
                if cached_rt is not None
                else loop.run_in_executor(_executor,
                    lambda: _compute_financial_ratios_sync(svc, company_id, report_type)))

    results = await asyncio.gather(dash_f, altman_f, ct_f, rt_f, return_exceptions=True)
    # Log (don't silently swallow) any sub-computation failure. A blank dashboard
    # section is almost always one of these four raising — surfacing it in the log
    # turns "sometimes I have to refresh" into a diagnosable error.
    for _name, _r in zip(("dashboard", "altman", "cost_trend", "financial_ratios"), results):
        if isinstance(_r, Exception):
            _perf_log.warning(f"[FULL] {company_id} {_name} failed: {_r!r}")
    dash, altman, cost_trend, fin_ratios = [
        ({} if isinstance(r, Exception) else (r or {})) for r in results
    ]

    # Populate caches from fresh results
    ts2 = _time.monotonic()
    if cached_ct is None and cost_trend:
        _COST_TREND_CACHE[ct_key] = (ts2, cost_trend)
    if cached_rt is None and fin_ratios:
        _RATIOS_CACHE[ct_key] = (ts2, fin_ratios)

    return {
        "dashboard":        dash,
        "altman":           altman,
        "cost_trend":       cost_trend,
        "financial_ratios": fin_ratios,
    }
