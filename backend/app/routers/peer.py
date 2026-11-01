"""
peer.py — Dedicated peer comparison endpoints.

POST /peer/cost-structure   → cost stack data for N companies
POST /peer/multi-metric     → KPI grid for N companies × M metrics
POST /export/peer/png       → PNG image of both charts
POST /export/peer/ppt       → PowerPoint with 4 slides
"""
from __future__ import annotations
import asyncio, math, io
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.service_factory import get_service, get_fresh_service
from analytics_integration.reshaper import WarehouseReshaper

router = APIRouter()

# ── Cost-stack segment definitions (matches Excel engine output) ──────────────
COST_SEGMENTS = [
    ("Raw Material Cost",           ["Cost of materials consumed",
                                     "Purchases of stock-in-trade",
                                     "Changes in inventories"]),
    ("Consumables",                 ["Consumables"]),
    ("Power & Fuel",                ["Power, Fuel Electricity"]),
    ("Transportation",              ["Cost transportation"]),
    ("Manpower",                    ["Employee benefit expenses"]),
    ("Rest in Other Expenses",      ["Rest in Other Expenses"]),
    ("Finance Costs",               ["Finance costs"]),
    ("Depreciation & Amortization", ["Depreciation & amortisation"]),
    ("Remaining Expenses",          ["Remaining Expenses"]),
    ("Operational PBT",             ["Operational PBT"]),
]

COST_COLORS = [
    "#1A56DB", "#0D9488", "#7C3AED", "#D97706",
    "#DC2626", "#059669", "#0891B2", "#EA580C",
    "#8B5CF6", "#64748B",
]

METRIC_MAP = {
    # KPI sub-key lookups: (kpi_dict_key, sub_key)
    # kpi_dict_key must match analytics_service.get_dashboard_data() kpis dict
    "Revenue":                 ("revenue",        "value"),
    "Revenue from Operations": ("revenue",        "value"),
    "Revenue Growth":          ("revenue",        "growth_pct"),   # FIX: was missing
    "Revenue Growth %":        ("revenue",        "growth_pct"),   # FIX: was missing
    "EBITDA":                  ("ebitda",         "value"),
    "EBITDA Margin":           ("ebitda",         "margin"),
    "EBITDA Margin %":         ("ebitda",         "margin"),
    "EBIT":                    ("ebit",           "value"),
    "EBIT Margin %":           ("ebit",           "margin"),
    "PAT":                     ("pat",            "value"),
    "PAT Margin":              ("pat",            "margin"),
    "PAT Margin %":            ("pat",            "margin"),
    "Total Assets":            ("total_assets",   "value"),
    "Net Worth":               ("net_worth",      "value"),
    "Total Equity":            ("net_worth",      "value"),
    "Current Ratio":           ("current_ratio",  "value"),
    "Working Capital":         ("working_capital","value"),
    "ROE":                     ("roe",            "value"),
    "ROE %":                   ("roe",            "value"),
    "Altman Z Score":          ("altman_z",       "value"),
    # Finance Costs is NOT a KPI — fetched directly from warehouse (see fallback below)
    "Finance Costs":           ("__warehouse__",  "Finance Costs"),
    "Finance Cost":            ("__warehouse__",  "Finance Costs"),
    "Total Liabilities":       ("__warehouse__",  "Total Liabilities"),
}

# Warehouse fallback: items that exist in warehouse but not as dashboard KPIs
_WAREHOUSE_ITEMS = {
    "Finance Costs":     "Finance Costs",
    "Finance Cost":      "Finance Costs",
    "Total Liabilities": "Total Liabilities",
}


def _clean(v):
    if v is None: return None
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return v


def _get_cost_structure(svc, company_id: str, period: str, report_type: str) -> dict:
    """
    Run the cost structure engine for one company and return segment values
    for the requested period (INR Mn).
    Tries multiple category names since different warehouse ingestions use
    different naming conventions (P&L Consolidated, P&L, P&L Standalone).
    """
    try:
        from cost_structure_analysis import CostStructureAnalysis
        # Try category names in priority order
        cats_to_try = (
            ["P&L Consolidated", "P&L"]
            if report_type == "consolidated"
            else ["P&L Standalone", "P&L"]
        )
        pnl, years = None, []
        for cat in cats_to_try:
            _pnl, _years = svc.reshaper.get_pnl_wide(company_id, cat)
            if not _pnl.empty and period in _years:
                pnl, years = _pnl, _years
                break
        if pnl is None or pnl.empty or period not in years:
            return {}
        cs = CostStructureAnalysis(pnl, years).run()

        # Build lookup: engine row label → value for requested period
        direct = cs["direct"]
        lookup: dict = {}
        for _, row in direct.iterrows():
            lbl = str(row.get("Particulars", ""))
            v = row.get(period)
            if v is not None:
                lookup[lbl] = float(v)

        result: dict = {}
        for seg_name, src_keys in COST_SEGMENTS:
            total = sum(lookup.get(k, 0) for k in src_keys)
            result[seg_name] = round(total, 2) if total else None

        result["_revenue"]    = lookup.get("Revenue from Ops")
        # Use engine's Total Cost if available; otherwise sum cost segments
        tc = lookup.get("Total Cost")
        if not tc:
            tc = sum(
                (result.get(seg) or 0)
                for seg, _ in COST_SEGMENTS
                if seg not in ("Operational PBT",)
            ) or None
        result["_total_cost"] = tc
        result["_company"]    = company_id
        result["_period"]     = period

        # Also fetch EBITDA directly from warehouse so the frontend can
        # render EBITDA % badges on the peer cost structure chart
        try:
            wh = svc.engine.get_company_history(company_id)
            cat_pref = "P&L Consolidated" if report_type == "consolidated" else "P&L Standalone"
            ebd_rows = wh[(wh["financial_item"] == "EBITDA") & (wh["year"] == period)]
            if not ebd_rows.empty:
                pref_rows = ebd_rows[ebd_rows["financial_category"] == cat_pref]
                ebd_val = float((pref_rows if not pref_rows.empty else ebd_rows)["value"].iloc[0])
                rv = result.get("_revenue") or 0
                result["EBITDA"] = round(ebd_val, 2)
                result["_ebitda_margin"] = round(ebd_val / rv * 100, 1) if rv else None
        except Exception:
            pass

        return result
    except Exception as e:
        return {"_error": str(e), "_company": company_id}


# ── Request models ────────────────────────────────────────────────────────────
class CostStructureRequest(BaseModel):
    companies:   List[str]
    period:      str = "FY25"
    report_type: str = "consolidated"
    unit:        str = "absolute"   # absolute | pct_revenue
    # company_modes: per-company override { "SUN": "standalone", "CIPLA": "5yr_consolidated" }
    company_modes: dict = {}

class MultiMetricRequest(BaseModel):
    companies:   List[str]
    metrics:     List[str]
    period:      str = "FY25"
    report_type: str = "consolidated"

class PeerExportRequest(BaseModel):
    companies:     List[str]
    metrics:       List[str]
    period:        str = "FY25"
    report_type:   str = "consolidated"
    cost_unit:     str = "absolute"
    format:        str = "png"   # png | ppt


_FY_ORDER = [f"FY{y}" for y in range(19, 31)]


def _compute_cost_structure_entry(svc, co: str, req: "CostStructureRequest") -> Optional[dict]:
    """Per-company body of peer_cost_structure's loop — run via asyncio.to_thread
    so N companies' blocking DuckDB/Postgres calls don't freeze the event loop."""
    co_mode = req.company_modes.get(co, req.report_type)

    if co_mode.startswith('5yr_'):
        rtype = 'consolidated' if co_mode == '5yr_consolidated' else 'standalone'
        try:
            idx = _FY_ORDER.index(req.period)
        except ValueError:
            idx = len(_FY_ORDER) - 1
        years_to_avg = _FY_ORDER[max(0, idx-4): idx+1]
        yearly = []
        for yr in years_to_avg:
            cs = _get_cost_structure(svc, co, yr, rtype)
            if cs and not cs.get('_error'):
                yearly.append(cs)
        if not yearly:
            return None
        avg_cs: dict = {}
        seg_keys = [s for s, _ in COST_SEGMENTS]
        for key in seg_keys + ['_revenue', '_total_cost']:
            vals = [y.get(key) for y in yearly if y.get(key) is not None]
            avg_cs[key] = sum(vals) / len(vals) if vals else None
        avg_cs['_company'] = co
        avg_cs['_period']  = f"5Y Avg ({req.period}→{years_to_avg[0]})"
        return {k: _clean(v) for k, v in avg_cs.items()}
    else:
        rtype = co_mode if co_mode in ('consolidated', 'standalone') else req.report_type
        cs = _get_cost_structure(svc, co, req.period, rtype)
        if cs and not cs.get('_error'):
            return {k: _clean(v) for k, v in cs.items()}
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/cost-structure")
async def peer_cost_structure(req: CostStructureRequest):
    """
    Returns cost stack data for each company in req.companies.
    Response shape:
    {
      companies: [...],
      segments:  [...],
      colors:    [...],
      data: { company_id: { segment: value_mn, _revenue, _total_cost } }
    }
    """
    svc = get_service()

    entries = await asyncio.gather(
        *(asyncio.to_thread(_compute_cost_structure_entry, svc, co, req) for co in req.companies)
    )
    result = {co: entry for co, entry in zip(req.companies, entries) if entry is not None}

    seg_names = [s[0] for s in COST_SEGMENTS]
    return {
        "companies": req.companies,
        "segments":  seg_names,
        "colors":    COST_COLORS,
        "period":    req.period,
        "unit":      req.unit,
        "data":      result,
    }


def _compute_multi_metric_entry(svc, co: str, req) -> Optional[list]:
    """Per-company body of peer_multi_metric's loop — run via asyncio.to_thread.
    Returns a list of (metric, value) pairs, or None if the company has no data.
    Shared by peer_multi_metric and export_peer_ppt (same metric-table shape)."""
    dash = svc.get_dashboard_data(co, period=req.period, report_type=req.report_type)
    if not dash or dash.get("no_data"):
        return None
    kpis = dash.get("kpis", {})

    out = []
    for metric in req.metrics:
        val = None
        if metric in METRIC_MAP:
            kpi_key, sub_key = METRIC_MAP[metric]
            if kpi_key == "__warehouse__":
                try:
                    wh_df = svc.engine.get_company_history(co)
                    wh_row = wh_df[
                        (wh_df["financial_item"] == sub_key) &
                        (wh_df["year"] == req.period)
                    ]
                    val = _clean(float(wh_row["value"].iloc[0])) if not wh_row.empty else None
                except Exception:
                    val = None
            else:
                val = _clean((kpis.get(kpi_key) or {}).get(sub_key))
        out.append((metric, val))
    return out


@router.post("/multi-metric")
async def peer_multi_metric(req: MultiMetricRequest):
    """
    Returns KPI values for each company × metric combination.
    Response shape:
    {
      companies: [...],
      metrics: [...],
      data: [ { company_id, metric, value, label } ]
      table: { metric: { company_id: value } }
    }
    """
    svc = get_service()
    rows = []
    table: dict = {m: {} for m in req.metrics}

    entries = await asyncio.gather(
        *(asyncio.to_thread(_compute_multi_metric_entry, svc, co, req) for co in req.companies)
    )
    for co, entry in zip(req.companies, entries):
        if entry is None:
            continue
        for metric, val in entry:
            rows.append({"company_id": co, "metric": metric, "value": val})
            table[metric][co] = val

    return {
        "companies": req.companies,
        "metrics":   req.metrics,
        "period":    req.period,
        "data":      rows,
        "table":     table,
    }


@router.post("/export/png")
async def export_peer_png(req: PeerExportRequest):
    """
    Generate a cost structure PNG using matplotlib (no Chrome/kaleido required).
    """
    from fastapi.responses import Response
    from app.services.chart_builder import make_cost_structure_chart

    svc = get_service()
    cs_results = await asyncio.gather(
        *(asyncio.to_thread(_get_cost_structure, svc, co, req.period, req.report_type) for co in req.companies)
    )
    cost_data: dict = {
        co: {k: _clean(v) for k, v in cs.items()}
        for co, cs in zip(req.companies, cs_results) if cs and not cs.get("_error")
    }

    png = make_cost_structure_chart(
        cost_data, req.companies, req.period,
        unit=req.cost_unit, width_in=10, height_in=5.5, dpi=180
    )
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f"attachment; filename=cost_structure_{req.period}.png"})


@router.post("/export/ppt")
async def export_peer_ppt(req: PeerExportRequest):
    """
    Generate a 5-slide peer comparison PPT matching the CIPLA template format.
    Uses matplotlib for chart images (no Chrome/kaleido required).
    """
    from fastapi.responses import Response
    from app.services.chart_builder import (
        make_cost_structure_chart, make_multi_metric_chart
    )
    from app.services.peer_ppt_builder import build_peer_ppt

    svc = get_service()

    # ── Gather cost structure data ─────────────────────────────────
    cs_results = await asyncio.gather(
        *(asyncio.to_thread(_get_cost_structure, svc, co, req.period, req.report_type) for co in req.companies)
    )
    cost_data: dict = {
        co: {k: _clean(v) for k, v in cs.items()}
        for co, cs in zip(req.companies, cs_results) if cs and not cs.get("_error")
    }

    # ── Gather metric table ────────────────────────────────────────
    metric_table: dict = {m: {} for m in req.metrics}
    mm_results = await asyncio.gather(
        *(asyncio.to_thread(_compute_multi_metric_entry, svc, co, req) for co in req.companies)
    )
    for co, entry in zip(req.companies, mm_results):
        if entry is None:
            continue
        for metric, val in entry:
            metric_table[metric][co] = val

    # ── Generate chart images ──────────────────────────────────────
    cost_png_abs = make_cost_structure_chart(
        cost_data, req.companies, req.period,
        unit="absolute", width_in=12, height_in=5.5, dpi=150
    )
    cost_png_pct = make_cost_structure_chart(
        cost_data, req.companies, req.period,
        unit="pct_revenue", width_in=12, height_in=5.5, dpi=150
    )
    metric_png = make_multi_metric_chart(
        metric_table, req.companies, req.metrics, req.period,
        width_in=8.5, height_in=5.5, dpi=150
    )

    # ── Build PPT ──────────────────────────────────────────────────
    ppt_bytes = build_peer_ppt(
        companies=req.companies,
        period=req.period,
        report_type=req.report_type,
        cost_data=cost_data,
        metric_table=metric_table,
        metrics=req.metrics,
        cost_png_abs=cost_png_abs,
        cost_png_pct=cost_png_pct,
        metric_png=metric_png,
    )
    filename = f"peer_comparison_{req.period}.pptx"
    return Response(
        ppt_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


class TrendRequest(BaseModel):
    companies:   List[str]
    metric:      str
    start_year:  str
    end_year:    str
    report_type: str = "consolidated"


# Direct warehouse item names for fast trend lookup — avoids calling get_dashboard_data per year.
# These mirror what get_dashboard_data computes, but read straight from the warehouse.
_TREND_DIRECT: dict = {
    # metric value → (financial_item in warehouse, prefer category)
    "Revenue from Operations": ("Revenue from Operations", None),
    "Revenue":                 ("Revenue from Operations", None),
    "EBITDA":                  ("EBITDA",                  None),
    "EBITDA Margin":           ("EBITDA",                  None),   # computed post-lookup
    "EBITDA Margin %":         ("EBITDA",                  None),
    "PAT":                     ("PAT",                     None),
    "PAT Margin":              ("PAT",                     None),   # computed post-lookup
    "PAT Margin %":            ("PAT",                     None),
    "Total Assets":            ("Total Assets",            None),
    "Net Worth":               ("Net Worth",               None),
    "Current Assets":          ("Current Assets",          None),
    "Current Liabilities":     ("Current Liabilities",     None),
    "Market Capitalization":   ("Market Capitalization",   None),
    "Finance Costs":           ("Finance Costs",           "P&L Consolidated"),
    "Altman Z Score":          ("__altman_z__",            None),   # handled separately
}

# Metrics computed inline from warehouse primitives — no KPI fallback needed
_RATIO_METRICS = {
    "Current Ratio",
    "DSCR - On Interest Basis",
    "Debt to Asset Ratio",
    "Interest Coverage Ratio",
    "Cash Conversion Cycle",
    "Creditors (Payables) Days",
    "Debtors (Receivables) Days",
    "Inventory Days",
    "ROE",   # Return on Equity = PAT / Net Worth, expressed as a ratio
}


def _compute_trend_one(svc, co: str, years: list, direct, is_margin: bool,
                        margin_num: str, metric: str, report_type: str) -> list:
    """Per-company body of peer_trend's loop — run via asyncio.to_thread."""
    values: list = []
    try:
        wh = svc.engine.get_company_history(co)
        if wh.empty:
            return [None] * len(years)
        if True:  # shortcut: keeps nested helpers' indentation unchanged from the original loop body

            def _pick(item, yr, prefer_cat=None):
                """Fetch one value from warehouse; prefer_cat for P&L items."""
                sub = wh[(wh["financial_item"] == item) & (wh["year"] == yr)]
                if sub.empty: return None
                if prefer_cat:
                    cat = sub[sub["financial_category"] == prefer_cat]
                    sub = cat if not cat.empty else sub
                return _clean(float(sub["value"].iloc[0]))

            def _pick_altman(yr):
                """Return Altman Z for one year.
                Priority 1: use the pre-computed score written to the warehouse by
                            Analyze (identical to the dashboard gauge and Excel).
                Priority 2: inline calculation as a fallback for years not yet analyzed.
                """
                stored = _pick("Altman Z Score", yr)
                if stored is not None:
                    return stored

                # ── Fallback inline calculation ─────────────────────────────────
                ta  = _pick("Total Assets", yr) or 1
                ca  = _pick("Current Assets", yr) or 0
                cl  = _pick("Current Liabilities", yr) or 0
                wc  = ca - cl
                mv  = _pick("Market Capitalization", yr) or 0
                rev = _pick("Revenue from Operations", yr) or 0
                nw  = _pick("Net Worth", yr) or 0
                tl  = ta - nw
                # X2: total Retained Earnings (balance sheet balance, not YoY change)
                re_ = (_pick("Retained Earnings", yr)
                       or _pick("Other Equity (Includes Reserves)", yr) or 0)
                ebitda_ = _pick("EBITDA", yr) or 0
                # Depreciation: prefer Altman Z category (same unit as EBITDA);
                # fall back to P&L value with /10 conversion (matches analytics_service)
                dep_az_rows = wh[
                    (wh["financial_item"] == "Depreciation and Amortisation") &
                    (wh["year"] == yr) &
                    (wh["financial_category"] == "Altman Z")
                ]
                if not dep_az_rows.empty:
                    ebit_ = ebitda_ - float(dep_az_rows["value"].iloc[0])
                else:
                    dep_pnl = _pick("Depreciation and Amortisation", yr) or 0
                    ebit_ = ebitda_ - (dep_pnl / 10)
                if ta > 0:
                    z = round(1.2*(wc/ta) + 1.4*(re_/ta) + 3.3*(ebit_/ta)
                              + 0.6*(mv/max(tl, 1)) + 1.0*(rev/ta), 2)
                    return z
                return None

            def _pick_ratio(metric: str, yr: str):
                """Compute a financial ratio from raw warehouse values."""
                ca   = _pick("Current Assets", yr) or 0
                cl   = _pick("Current Liabilities", yr) or 0
                ta   = _pick("Total Assets", yr) or 0
                pat  = _pick("PAT", yr) or 0
                stb  = _pick("Short Term Borrowings", yr) or 0
                ltd  = (_pick("Non Current Liability", yr, "Altman Z")
                        or _pick("Long Term Debt", yr, "Altman Z") or 0)
                fc   = (_pick("Finance Costs", yr, "Altman Z")
                        or _pick("Finance Costs", yr) or 0)
                ebitda = _pick("EBITDA", yr) or 0
                dep    = _pick("Depreciation and Amortisation", yr) or 0
                ebit   = ebitda - dep
                rev    = _pick("Revenue from Operations", yr) or 0
                rec    = _pick("Debtors (Receivables)", yr) or 0
                pay    = _pick("Creditors (Payables)", yr) or 0
                inv    = _pick("Inventory", yr) or 0
                nw     = _pick("Net Worth", yr) or 0
                # Raw-material cost: sum of P&L cost lines (all stored in Mn)
                cmc = _pick("Cost of Materials Consumed", yr, "P&L Consolidated") or 0
                sit = _pick("Purchases of Stock-in-Trade", yr, "P&L Consolidated") or 0
                chg = _pick("Changes in Inventories", yr, "P&L Consolidated") or 0
                rm  = cmc + sit + chg   # net raw-material cost (denominator for Inventory Days)
                # Creditor Days denominator = net material cost (CMC + PSIT + ΔInv).
                # If inventory build-up drives rm ≤ 0, fall back to (CMC + PSIT) alone.
                cred_denom = rm if rm > 0 else (cmc + sit if (cmc + sit) > 0 else None)

                if metric == "ROE":
                    return _clean(round(pat / nw, 2)) if nw else None
                if metric == "Current Ratio":
                    return _clean(round(ca / cl, 2)) if cl else None
                if metric == "DSCR - On Interest Basis":
                    denom = stb + fc
                    return _clean(round(pat / denom, 2)) if denom else None
                if metric == "Debt to Asset Ratio":
                    # Total Liabilities / Total Assets = (Total Assets - Net Worth) / Total Assets
                    nw_d = _pick("Net Worth", yr)
                    return _clean(round((ta - nw_d) / ta, 3)) if (ta and nw_d is not None) else None
                if metric == "Interest Coverage Ratio":
                    return _clean(round(ebit / fc, 2)) if fc else None
                if metric == "Debtors (Receivables) Days":
                    return _clean(round(rec * 365 / rev, 1)) if rev else None
                if metric == "Creditors (Payables) Days":
                    return _clean(round(pay * 365 / cred_denom, 1)) if cred_denom else None
                if metric == "Inventory Days":
                    return _clean(round(inv * 365 / rm, 1)) if rm else None
                if metric == "Cash Conversion Cycle":
                    ddays = (rec * 365 / rev)        if rev        else None
                    cdays = (pay * 365 / cred_denom) if cred_denom else None
                    idays = (inv * 365 / rm)         if rm         else None
                    if ddays is not None and cdays is not None and idays is not None:
                        return _clean(round(ddays + idays - cdays, 1))
                return None

            if metric in _RATIO_METRICS:
                for yr in years:
                    try:   values.append(_pick_ratio(metric, yr))
                    except Exception: values.append(None)
            elif direct and direct[0] == "__altman_z__":
                for yr in years:
                    try:   values.append(_pick_altman(yr))
                    except Exception: values.append(None)
            elif is_margin:
                for yr in years:
                    try:
                        num = _pick(margin_num, yr)
                        rv  = _pick("Revenue from Operations", yr)
                        values.append(_clean(round(num/rv*100, 2)) if num is not None and rv else None)
                    except Exception:
                        values.append(None)
            elif direct:
                item_name, pref_cat = direct
                for yr in years:
                    try:   values.append(_pick(item_name, yr, pref_cat))
                    except Exception: values.append(None)
            else:
                # Fallback: use get_dashboard_data kpi lookup for unmapped metrics
                kpi_key, sub_key = METRIC_MAP.get(metric, (None, None))
                for yr in years:
                    try:
                        dash = svc.get_dashboard_data(co, period=yr, report_type=report_type)
                        val  = _clean((dash.get("kpis", {}).get(kpi_key) or {}).get(sub_key)) \
                               if kpi_key and dash and not dash.get("no_data") else None
                        values.append(val)
                    except Exception:
                        values.append(None)

    except Exception:
        values = [None] * len(years)

    return values


@router.post("/trend")
async def peer_trend(req: TrendRequest):
    """
    Returns a single metric's value for each company across a year range.
    Uses direct warehouse reads (one query per company) for speed —
    avoids the overhead of calling get_dashboard_data per year.
    """
    svc = get_service()

    FY_ORDER = [f"FY{y}" for y in range(19, 31)]
    try:
        s_idx = FY_ORDER.index(req.start_year)
        e_idx = FY_ORDER.index(req.end_year)
        years = FY_ORDER[min(s_idx, e_idx): max(s_idx, e_idx) + 1]
    except ValueError:
        years = [req.start_year, req.end_year]

    direct = _TREND_DIRECT.get(req.metric)
    is_margin = req.metric in ("EBITDA Margin", "EBITDA Margin %", "PAT Margin", "PAT Margin %")
    margin_num = "EBITDA" if req.metric in ("EBITDA Margin", "EBITDA Margin %") else "PAT"

    results = await asyncio.gather(
        *(asyncio.to_thread(_compute_trend_one, svc, co, years, direct, is_margin,
                             margin_num, req.metric, req.report_type)
          for co in req.companies)
    )
    series = [{"company_id": co, "values": vals} for co, vals in zip(req.companies, results)]

    return {
        "companies":    req.companies,
        "years":        years,
        "metric":       req.metric,
        "series":       series,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SUPPLIER FINANCIAL DUE DILIGENCE ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════
class DueDiligenceRequest(BaseModel):
    companies:   list[str]
    period:      str  = "FY25"
    report_type: str  = "consolidated"


def _dd_gv(df, item, default=None):
    """Get value from a wide DataFrame by row label."""
    try:
        if df is None or df.empty: return default
        if item in df.index:
            v = df.loc[item]
            v = v.iloc[0] if hasattr(v, 'iloc') else v
            return float(v) if v is not None and not (isinstance(v, float) and math.isnan(v)) else default
    except Exception:
        pass
    return default


def _dd_sd(n, d, pct=False, decimals=2):
    """Safe divide."""
    try:
        if n is None or d is None or d == 0: return None
        r = float(n) / float(d)
        return round(r * 100, decimals) if pct else round(r, decimals)
    except Exception:
        return None


def _dd_classify(key, val):
    if val is None: return "na"
    THRESHOLDS = {
        "current_ratio":   ((1.5, float('inf')), (1.0, 1.5), (-float('inf'), 1.0)),
        "quick_ratio":     ((1.0, float('inf')), (0.7, 1.0), (-float('inf'), 0.7)),
        "cash_ratio":      ((0.5, float('inf')), (0.2, 0.5), (-float('inf'), 0.2)),
        "gross_margin":    ((30,  float('inf')), (15,  30),  (-float('inf'), 15)),
        "ebitda_margin":   ((20,  float('inf')), (10,  20),  (-float('inf'), 10)),
        "ebit_margin":     ((15,  float('inf')), (5,   15),  (-float('inf'), 5)),
        "net_margin":      ((10,  float('inf')), (3,   10),  (-float('inf'), 3)),
        "roa":             ((5,   float('inf')), (2,   5),   (-float('inf'), 2)),
        "roe":             ((15,  float('inf')), (8,   15),  (-float('inf'), 8)),
        "ocf_margin":      ((15,  float('inf')), (5,   15),  (-float('inf'), 5)),
        "cash_conv_ratio": ((1.0, float('inf')), (0.7, 1.0), (-float('inf'), 0.7)),
        "de_ratio":        ((-float('inf'), 0.5), (0.5, 1.5), (1.5, float('inf'))),
        "da_ratio":        ((-float('inf'), 0.3), (0.3, 0.6), (0.6, float('inf'))),
        "interest_cov":    ((4,   float('inf')), (2,   4),   (-float('inf'), 2)),
        "fin_leverage":    ((-float('inf'), 2.0), (2.0, 3.5), (3.5, float('inf'))),
        "inventory_days":  ((-float('inf'), 60),  (60,  90),  (90, float('inf'))),
        "receivable_days": ((-float('inf'), 45),  (45,  75),  (75, float('inf'))),
        "payable_days":    ((30, float('inf')),  (15,  30),  (-float('inf'), 15)),
        "ccc":             ((-float('inf'), 60),  (60, 120),  (120, float('inf'))),
    }
    thresh = THRESHOLDS.get(key)
    if not thresh: return "green"
    g_lo, g_hi = thresh[0]
    y_lo, y_hi = thresh[1]
    if g_lo <= val < g_hi: return "green"
    if y_lo <= val < y_hi: return "yellow"
    return "red"


def _compute_due_diligence_one(rspr, co: str, period: str) -> dict:
    """Per-company body of peer_due_diligence's loop — run via asyncio.to_thread."""
    gv, sd, classify = _dd_gv, _dd_sd, _dd_classify
    try:
            # ── Fetch wide DataFrames from warehouse ──────────────────────────
            pnl_df, years_pnl = rspr.get_pnl_wide(co, "P&L Consolidated")
            az_df,  years_az  = rspr.get_altman_wide(co)

            yr = period

            # Helper to get from either df
            def P(item):   return gv(pnl_df, item)
            def A(item):   return gv(az_df,  item)

            # ── Raw values ────────────────────────────────────────────────────
            rev      = A("Revenue from Operations") or P("Revenue from Ops") or 0
            ebitda   = A("EBITDA") or P("EBITDA") or 0
            dep_a    = A("Depreciation and Amortisation")
            dep_p    = P("Depreciation & amortisation")
            dep      = dep_a if dep_a is not None else (round(dep_p / 10, 2) if dep_p else 0)
            ebit     = round(ebitda - dep, 2)
            fc       = A("Finance costs") or P("Finance Costs") or 0
            pat      = A("PAT") or P("PAT") or 0
            ta       = A("Total Assets") or 0
            ca       = A("Current Assets") or 0
            cl       = A("Current Liabilities") or 0
            inv      = A("Inventory") or 0
            rec      = A("Debtors (Receivables)") or 0
            pay      = A("Creditors (Payables)") or 0
            nw       = A("Net Worth") or 0
            ltd      = A("Long Term Debt") or 0
            stb      = A("Short Term Borrowings") or A("Current Financial Liabilities") or 0
            bvd      = stb + ltd
            tl       = ta - nw if (ta and nw) else 0
            wc       = ca - cl
            mat      = (P("Cost of materials consumed") or 0) + \
                       (P("Purchases of stock-in-trade") or 0) + \
                       (P("Changes in inventories") or 0)
            # Gross profit proxy: Revenue - COGS (mat cost)
            gross_p  = rev - mat if (rev and mat) else None
            # OCF proxy: PAT + D&A (simplified)
            ocf      = pat + dep if (pat is not None and dep is not None) else pat
            fcf      = ocf - (dep * 0.5) if ocf is not None else None  # simplified capex proxy

            # ── Compute all 20 metrics ────────────────────────────────────────
            metrics = {
                # 1. Liquidity
                "current_ratio":      sd(ca, cl),
                "quick_ratio":        sd(ca - inv, cl),
                "cash_ratio":         sd(ca - inv - rec, cl),
                # 2. Profitability
                "gross_margin":       sd(gross_p, rev, pct=True),
                "ebitda_margin":      sd(ebitda, rev, pct=True),
                "ebit_margin":        sd(ebit, rev, pct=True),
                "net_margin":         sd(pat, rev, pct=True),
                "roa":                sd(pat, ta, pct=True),
                "roe":                sd(pat, nw, pct=True),
                # 3. Cash Flow
                "ocf":                round(ocf, 2) if ocf is not None else None,
                "fcf":                round(fcf, 2) if fcf is not None else None,
                "ocf_margin":         sd(ocf, rev, pct=True),
                "cash_conv_ratio":    sd(ocf, pat) if pat else None,
                # 4. Leverage
                "de_ratio":           sd(bvd, nw),
                "da_ratio":           sd(bvd, ta),
                "interest_cov":       sd(ebit, fc) if fc else None,
                "fin_leverage":       sd(ta, nw),
                # 5. Working Capital
                "working_capital":    round(wc, 2),
                "inventory_days":     round(sd(inv, mat) * 365, 1) if (mat and inv) else None,
                "receivable_days":    round(sd(rec, rev) * 365, 1) if (rev and rec) else None,
                "payable_days":       round(sd(pay, mat) * 365, 1) if (mat and pay) else None,
                "ccc":                None,
            }
            # CCC = Inv Days + Rec Days - Pay Days
            if all(metrics.get(k) is not None for k in ["inventory_days","receivable_days","payable_days"]):
                metrics["ccc"] = round(
                    metrics["inventory_days"] + metrics["receivable_days"] - metrics["payable_days"], 1)

            # ── Health classification ─────────────────────────────────────────
            health = {k: classify(k, v) for k, v in metrics.items()}

            # ── Risk Score (0–100) ────────────────────────────────────────────
            score_map = {"green": 10, "yellow": 5, "red": 0, "na": 3}
            scored_keys = [k for k in health if k not in ("working_capital","ocf","fcf")]
            raw_score = sum(score_map[health[k]] for k in scored_keys)
            max_score = 10 * len(scored_keys)
            risk_score = round(raw_score / max_score * 100) if max_score else 0

            # ── Rating ────────────────────────────────────────────────────────
            if   risk_score >= 80: rating = "A"
            elif risk_score >= 65: rating = "B"
            elif risk_score >= 50: rating = "C"
            elif risk_score >= 35: rating = "D"
            else:                  rating = "E"

            return {
                "metrics": metrics,
                "health":  health,
                "risk_score": risk_score,
                "rating":     rating,
                "period":     yr,
            }

    except Exception as e:
        return {"error": str(e), "metrics": {}, "health": {},
                "risk_score": 0, "rating": "E", "period": period}


@router.post("/due-diligence")
async def peer_due_diligence(req: DueDiligenceRequest):
    """
    Compute a full 20-metric financial due diligence table for N supplier companies.
    Returns per-company values, health status (green/yellow/red), score, and rating.
    """
    svc  = get_service()
    rspr = WarehouseReshaper(svc.engine)

    entries = await asyncio.gather(
        *(asyncio.to_thread(_compute_due_diligence_one, rspr, co, req.period) for co in req.companies)
    )
    results = dict(zip(req.companies, entries))

    return {"companies": req.companies, "period": req.period, "results": results}
