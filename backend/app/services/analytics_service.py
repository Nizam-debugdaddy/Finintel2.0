"""
AnalyticsService — wraps existing legacy engines without modifying them.
"""
import sys, uuid, math, time as _time
from pathlib import Path
from datetime import datetime
from typing import Optional

_RESP_CACHE_TTL = 120  # seconds — dashboard response cache lifetime

from app.config import settings

sys.path.insert(0, str(settings.SRC_PATH))
sys.path.insert(0, str(settings.LEGACY_PATH))

from utils import Paths, get_logger
from storage import Warehouse
from retrieval import QueryEngine
from analytics_integration.reshaper import WarehouseReshaper
from standardization import Normalizer
from cost_structure_analysis import CostStructureAnalysis
from bankruptcy_analysis import BankruptcyAnalysis

logger = get_logger("analytics_service")

CAT_PRIORITY = {"P&L Consolidated": 0, "Altman Z": 1, "P&L Standalone": 2}


class AnalyticsService:
    def __init__(self):
        self.paths = Paths(settings.WAREHOUSE_PATH.parent).ensure()
        self.paths.warehouse          = settings.WAREHOUSE_PATH
        self.paths.mappings           = settings.MAPPINGS_PATH
        self.paths.legacy             = settings.LEGACY_PATH
        self.paths.output             = settings.OUTPUT_PATH
        self.paths.wh_company_master  = settings.WAREHOUSE_PATH / "company_master.parquet"
        self.paths.wh_sector_map      = settings.WAREHOUSE_PATH / "sector_mapping.parquet"
        self.paths.wh_financials      = settings.WAREHOUSE_PATH / "financials"
        self.paths.wh_audit           = settings.WAREHOUSE_PATH / "audit_log.parquet"
        self.paths.mapping_lineitem   = settings.MAPPINGS_PATH / "line_item_mapping.json"

        self.warehouse  = Warehouse(self.paths)
        self.engine     = QueryEngine(self.paths)
        self.reshaper   = WarehouseReshaper(self.engine)
        self.normalizer = Normalizer(self.paths.mapping_lineitem)
        self._resp_cache: dict = {}   # {cache_key: (timestamp, response_dict)}

    # ── Staging → Warehouse ──────────────────────────────────────────

    def ingest_from_staging(self, company_id: str, period: str, staged_rows: list) -> dict:
        ingestion_id = str(uuid.uuid4())
        records = []
        for row in staged_rows:
            if row.get("value") is None:
                continue
            try:
                v = float(row["value"])
            except (TypeError, ValueError):
                continue
            cat = row.get("category", "P&L Consolidated")
            if "Altman" in cat:
                cat = "Altman Z"
            elif "Standalone" in cat:
                cat = "P&L Standalone"
            else:
                cat = "P&L Consolidated"
            records.append({
                "company_id": company_id, "company_name": company_id,
                "financial_item": row["financial_item"],
                "financial_category": cat, "year": period,
                "value": v, "units": row.get("units", "INR Million"),
                "source_file": f"web_input:{company_id}/{period}",
                "version": None, "is_active": True,
                "updated_on": datetime.utcnow(), "ingestion_id": ingestion_id,
            })
        if not records:
            return {"rows_loaded": 0, "rows_revised": 0}
        result = self.warehouse.ingest_financials(records, ingestion_id)
        self.engine.refresh()
        return result

    def ingest_all_periods(self, company_id: str, periods_staged: dict) -> dict:
        """Ingest all periods in a single warehouse write — one read + one write instead of N.
        periods_staged: {period_label: [staged_rows]} collected from all periods up front.
        """
        ingestion_id = str(uuid.uuid4())
        all_records = []
        for period, staged_rows in periods_staged.items():
            for row in staged_rows:
                if row.get("value") is None:
                    continue
                try:
                    v = float(row["value"])
                except (TypeError, ValueError):
                    continue
                cat = row.get("category", "P&L Consolidated")
                if "Altman" in cat:
                    cat = "Altman Z"
                elif "Standalone" in cat:
                    cat = "P&L Standalone"
                else:
                    cat = "P&L Consolidated"
                all_records.append({
                    "company_id": company_id, "company_name": company_id,
                    "financial_item": row["financial_item"],
                    "financial_category": cat, "year": period,
                    "value": v, "units": row.get("units", "INR Million"),
                    "source_file": f"web_input:{company_id}/{period}",
                    "version": None, "is_active": True,
                    "updated_on": datetime.utcnow(), "ingestion_id": ingestion_id,
                })
        if not all_records:
            return {"rows_loaded": 0, "rows_revised": 0}
        result = self.warehouse.ingest_financials(all_records, ingestion_id)
        self.engine.refresh()
        self._cache_invalidate(company_id)
        return result

    def remove_period_from_warehouse(self, company_id: str, period: str) -> int:
        """
        Deactivate all warehouse rows for a specific (company, period).
        Called when analyst deletes and saves — ensures dashboard shows no data
        for that period instead of stale values.
        """
        n = self.warehouse.deactivate_period(company_id, period)
        self.engine.refresh()
        return n

    def remove_all_from_warehouse(self, company_id: str) -> int:
        """Deactivate ALL warehouse rows for a company."""
        n = self.warehouse.deactivate_all(company_id)
        self.engine.refresh()
        return n

    # ── Run engines ──────────────────────────────────────────────────

    def run_analysis(self, company_id: str) -> dict:
        self.engine.refresh()
        pnl_co,  years_co  = self.reshaper.get_pnl_wide(company_id, "P&L Consolidated")
        pnl_std, years_std = self.reshaper.get_pnl_wide(company_id, "P&L Standalone")
        altman,  years_alt = self.reshaper.get_altman_wide(company_id)

        years = years_co or years_alt or []
        if not years:
            raise ValueError(f"No data in warehouse for {company_id}")

        result = {"company_id": company_id, "years": years}
        if not pnl_co.empty:
            cs = CostStructureAnalysis(pnl_co, years).run()
            result["cost_structure"] = self._serialize_cs(cs, years)
        if not altman.empty:
            bk = BankruptcyAnalysis(altman, pnl_co if not pnl_co.empty else altman, years).run()
            result["bankruptcy"] = self._serialize_bk(bk, years)
        return result

    def generate_excel(self, company_id: str, report_type: str = "consolidated") -> Path:
        from excel_writer import ExcelWriter

        self.engine.refresh()
        pnl_co,  years_co  = self.reshaper.get_pnl_wide(company_id, "P&L Consolidated")
        pnl_std, years_std = self.reshaper.get_pnl_wide(company_id, "P&L Standalone")
        altman,  years_alt = self.reshaper.get_altman_wide(company_id)
        years = years_co or years_std or years_alt

        if not years:
            raise ValueError(f"No warehouse data for {company_id}. Run analysis first.")

        # Use the PnL that matches the user's current report_type selection.
        # Fall back to consolidated when standalone is empty (common for listed entities).
        if report_type == "standalone" and not pnl_std.empty:
            pnl_primary = pnl_std
        else:
            pnl_primary = pnl_co

        co_results  = CostStructureAnalysis(pnl_co,      years).run()
        std_results = CostStructureAnalysis(pnl_std,     years).run() if not pnl_std.empty else co_results

        # ── Load Retained Earnings from SQLite staging ───────────────────────
        # Analyst may have entered RE in Data Input without re-running Analyze.
        # Pass these values directly so the Excel output reflects the staged RE.
        re_overrides_for_excel: dict = {}
        try:
            import sqlite3 as _sqlite3
            from app.config import settings as _settings
            RE_ALIAS_FIELDS = [
                "Retained Earnings", "Reserves & Surplus",
                "Retained Profit", "Retained Earnings / Deficit",
            ]
            placeholders = ",".join("?" * len(RE_ALIAS_FIELDS))
            with _sqlite3.connect(str(_settings.DB_PATH)) as _conn:
                rows = _conn.execute(
                    f"""SELECT period_label, financial_item, value
                        FROM financial_inputs
                        WHERE company_id = ?
                          AND financial_item IN ({placeholders})
                          AND value IS NOT NULL
                        ORDER BY period_label""",
                    (company_id, *RE_ALIAS_FIELDS)
                ).fetchall()
            for period_lbl, field, val in rows:
                if period_lbl not in re_overrides_for_excel:   # first alias wins
                    re_overrides_for_excel[period_lbl] = float(val)
        except Exception:
            pass   # if staging unavailable, fall back to warehouse RE / OE

        bk_results  = BankruptcyAnalysis(altman, pnl_primary, years,
                                         re_overrides=re_overrides_for_excel).run()

        # ── Rebuild zscore_calc with the standard Altman formula ─────────────
        # X1=WC/TA, X2=RE/TA (direct RE; fallback: OE directly), X3=EBIT/TA (EBIT=EBITDA-D&A), X4=MktCap/TL, X5=Rev/TA
        try:
            import math as _math
            def _get_val_from_altman(row_name, yr):
                if altman.empty: return None
                sub = altman[(altman.iloc[:,0] == row_name)] if len(altman.columns) > 0 else pd.DataFrame()
                # altman is wide-format: rows=items, cols=years
                if not sub.empty and yr in sub.columns:
                    v = sub.iloc[0][yr]
                    return float(v) if v is not None and not (isinstance(v, float) and _math.isnan(v)) else None
                return None

            # Build corrected zscore_calc rows
            corrected_rows = []
            row_defs = [
                ("Working Capital / Total Assets",            1.2),
                ("Retained Earnings / Total Assets",           1.4),
                ("EBIT / Total Assets",                        3.3),
                ("Market Value of Equity / Total Liabilities", 0.6),
                ("Sales / Total Assets",                       1.0),
                ("Altman Z_Score",                             None),
            ]

            # Re-use the summary DataFrame (has all raw values per year)
            summary_df = bk_results.get("summary")
            if summary_df is not None and hasattr(summary_df, "iterrows"):
                def _sg(row_name, yr):
                    try:
                        sub = summary_df[summary_df["Particulars"] == row_name]
                        return sub.iloc[0][yr] if not sub.empty and yr in sub.columns else None
                    except Exception:
                        return None

                for label, coef in row_defs:
                    rec = {"Ratios": label, "Coefficient": coef}
                    for yr in years:
                        ta  = _sg("Total Assets",    yr)  or 1
                        tl  = _sg("Total Liability", yr)
                        if label == "Working Capital / Total Assets":
                            wc = _sg("Working Capital", yr)
                            rec[yr] = round(wc / ta, 4) if wc is not None else None
                        elif label == "Retained Earnings / Total Assets":
                            # X2: priority — staged RE → warehouse RE → OE fallback
                            # summary_df row is "Retained Earning" (no s) — that already
                            # has the correct value (re_overrides → warehouse RE → OE)
                            re_val = _sg("Retained Earning", yr)   # correct key, no trailing 's'
                            if re_val is None:
                                re_val = _sg("Other Equity (Includes Reserves)", yr) or 0
                            rec[yr] = round(re_val / ta, 4) if ta else None
                        elif label == "EBIT / Total Assets":
                            # X3: EBIT = EBITDA - D&A (both INR Million, no unit conversion)
                            ebit_v = _sg("EBIT", yr) or 0
                            rec[yr]  = round(ebit_v / ta, 4) if ta else None
                        elif label == "Market Value of Equity / Total Liabilities":
                            mv = _sg("Market Value", yr)
                            rec[yr] = round(mv / max(tl or 1, 1), 4) if mv is not None else None
                        elif label == "Sales / Total Assets":
                            rv = _sg("Total Revenue", yr)
                            rec[yr] = round(rv / ta, 4) if rv is not None else None
                        else:
                            # Z_Score row — recompute from corrected ratios
                            x_vals = [r.get(yr) for r in corrected_rows]
                            weights = [1.2, 1.4, 3.3, 0.6, 1.0]
                            if all(v is not None for v in x_vals):
                                rec[yr] = round(sum(x*w for x, w in zip(x_vals, weights)), 2)
                            else:
                                rec[yr] = None
                    corrected_rows.append(rec)

                import pandas as _pd
                bk_results["zscore_calc"] = _pd.DataFrame(corrected_rows)
        except Exception as _e:
            pass  # If correction fails, fall back to legacy engine values

        try:
            cm = self.engine.sql(f"SELECT company_name, ticker FROM company_master WHERE company_id='{company_id}'")
            co_label = f"{cm.iloc[0]['company_name']} ({cm.iloc[0]['ticker']})" if not cm.empty else company_id
        except Exception:
            co_label = company_id

        out_path = settings.OUTPUT_PATH / f"Output_Analysis_{company_id}.xlsx"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        writer = ExcelWriter(str(out_path), list(reversed(years)), company_name=co_label)
        writer.write(bk_results, co_results, std_results)
        return out_path

    # ── Dashboard data ───────────────────────────────────────────────

    def _cache_invalidate(self, company_id: str):
        """Remove all cached responses for a company (call after ingest/refresh)."""
        keys = [k for k in self._resp_cache if k.startswith(f"{company_id}:")]
        for k in keys:
            del self._resp_cache[k]

    def get_dashboard_data(
        self, company_id: str,
        period: Optional[str] = None,
        report_type: str = "consolidated",
        re_staging: Optional[dict] = None,
        altman_staging: Optional[dict] = None,
    ) -> dict:
        # Response-level cache — avoids full recompute on repeated requests
        # (e.g. sector_ranking loops, multi-company peer calls hitting same company)
        _cache_key = f"{company_id}:{period}:{report_type}:dash"
        _now = _time.monotonic()
        if not re_staging and not altman_staging and _cache_key in self._resp_cache:
            _ts, _val = self._resp_cache[_cache_key]
            if _now - _ts < _RESP_CACHE_TTL:
                return _val

        try:
            df = self.engine.get_company_history(company_id)
        except Exception:
            return {}
        if df.empty:
            return {"company_id": company_id, "no_data": True, "kpis": {}, "trend": {},
                    "cost_structure": [], "years": [], "message": "No warehouse data for this company"}

        # Apply report type filter for PnL items
        cat_filter = "P&L Consolidated" if report_type == "consolidated" else "P&L Standalone"

        years_sorted = sorted(df["year"].unique(), reverse=True)
        # If period specified, verify it has data
        latest_year = period if period and period in years_sorted else years_sorted[0] if years_sorted else None
        if not latest_year:
            return {"company_id": company_id, "no_data": True, "kpis": {}, "trend": {},
                    "cost_structure": [], "years": list(years_sorted), "message": "No data for selected period"}
        # Warn if requested period has no rows (even though other years exist)
        period_has_data = any(df["year"] == latest_year)
        if period and period not in years_sorted:
            return {"company_id": company_id, "no_data": True, "kpis": {}, "trend": {},
                    "cost_structure": [], "years": list(years_sorted),
                    "message": f"No data for {period}. Available: {', '.join(years_sorted)}"}
        prev_idx = years_sorted.index(latest_year) + 1 if latest_year in years_sorted else None
        prev_year = years_sorted[prev_idx] if prev_idx and prev_idx < len(years_sorted) else None

        def get_val(item, year=None, prefer_cat=None):
            y = year or latest_year
            sub = df[(df["financial_item"] == item) & (df["year"] == y)].copy()
            if sub.empty:
                return None
            if prefer_cat:
                sub_cat = sub[sub["financial_category"] == prefer_cat]
                if not sub_cat.empty:
                    return float(sub_cat["value"].iloc[0])
            sub["_p"] = sub["financial_category"].map(lambda c: CAT_PRIORITY.get(c, 9))
            return float(sub.sort_values("_p")["value"].iloc[0])

        def yoy(item):
            c = get_val(item, latest_year)
            p = get_val(item, prev_year) if prev_year else None
            if c is not None and p and p != 0:
                return round((c - p) / abs(p) * 100, 2)
            return None

        def margin(num, denom):
            n, d = get_val(num), get_val(denom)
            if n is not None and d and d != 0:
                return round(n / d * 100, 2)
            return None

        rev        = get_val("Revenue from Operations", prefer_cat=cat_filter)
        ebitda_val = get_val("EBITDA")
        # D&A: prefer Altman Z (INR Million, same units as EBITDA)
        # Altman Z has priority 1, P&L has priority 0 — need explicit Altman Z lookup
        dep_altman = get_val("Depreciation and Amortisation", prefer_cat="Altman Z")
        if dep_altman is not None:
            ebit_val = round(ebitda_val - dep_altman, 2) if ebitda_val is not None else None
        else:
            dep_pnl = get_val("Depreciation and Amortisation")
            dep_val_mn = round(dep_pnl / 10, 2) if dep_pnl is not None else None
            ebit_val = round(ebitda_val - dep_val_mn, 2) if (ebitda_val is not None and dep_val_mn is not None) else get_val("EBIT")

        kpis = {
            "revenue":        {"value": rev, "yoy": yoy("Revenue from Operations"), "unit": "INR Mn"},
            "ebitda":         {"value": ebitda_val, "margin": round(ebitda_val/rev*100,2) if (ebitda_val and rev) else None, "unit": "INR Mn"},
            "ebit":           {"value": ebit_val,   "margin": round(ebit_val/rev*100,2)   if (ebit_val and rev)   else None, "unit": "INR Mn"},
            "pat":            {"value": get_val("PAT"), "margin": margin("PAT","Revenue from Operations"), "unit": "INR Mn"},
            "total_assets":   {"value": get_val("Total Assets"), "yoy": yoy("Total Assets"), "unit": "INR Mn"},
            "net_worth":      {"value": get_val("Net Worth"), "unit": "INR Mn"},
            "current_ratio":  {"value": self._safe_div(get_val("Current Assets"), get_val("Current Liabilities"))},
            # ROE as a RATIO (PAT / Net Worth), not a percentage — dashboard shows
            # "Ratio", peer multi-metric reads this same value. (pct=False)
            "roe":            {"value": self._safe_div(get_val("PAT"), get_val("Net Worth"))},
            "working_capital":{"value": self._safe_sub(get_val("Current Assets"), get_val("Current Liabilities")), "unit":"INR Mn"},
        }
        # Revenue Growth %
        rev_prior = get_val("Revenue from Operations", year=prev_year, prefer_cat=cat_filter) if prev_year else None
        if rev and rev_prior and rev_prior != 0:
            kpis["revenue"]["growth_pct"] = round((rev - rev_prior) / abs(rev_prior) * 100, 2)

        # ── Altman Z — delegate to get_altman_detail (single source of truth) ──
        # get_altman_detail uses the Excel-matching formula and is what the
        # decomposition table displays. Calling it here ensures the gauge and
        # decomposition table always show the IDENTICAL value.
        # Never re-compute Z inline — that creates divergence due to category
        # priority differences in get_val vs the simple lookup in get_altman_detail.
        try:
            _altman = self.get_altman_detail(company_id, period=latest_year,
                                              re_staging=re_staging,
                                              altman_staging=altman_staging)
            if _altman and _altman.get("z_score") is not None:
                _z = _altman["z_score"]
                kpis["altman_z"] = {
                    "value": round(float(_z), 2),
                    "zone":  _altman.get("zone", "safe" if _z > 2.99 else "grey" if _z > 1.81 else "distress"),
                }
        except Exception:
            pass  # altman_z stays absent from kpis if data unavailable

        # Trend — deduplicated per year
        trend: dict = {}
        for item in ["Revenue from Operations", "PAT", "Total Assets"]:
            idf = df[df["financial_item"] == item].copy()
            if idf.empty:
                continue
            idf["_p"] = idf["financial_category"].map(lambda c: CAT_PRIORITY.get(c, 9))
            deduped = idf.sort_values("_p").groupby("year", as_index=False).first().sort_values("year")
            trend[item] = [{"year": r["year"], "value": r["value"]} for _, r in deduped.iterrows()]

        # EBITDA trend — direct warehouse lookup (EBITDA is a stored named item).
        # Avoids running the full CostStructureAnalysis engine (saves 300-800 ms per call).
        # Falls back to Revenue - Total Cost + FC + D&A if EBITDA not stored.
        ebitda_series = []
        _ebitda_rows = df[df["financial_item"] == "EBITDA"].copy()
        if not _ebitda_rows.empty:
            _ebitda_rows["_p"] = _ebitda_rows["financial_category"].map(
                lambda c: CAT_PRIORITY.get(c, 9)
            )
            _ebd_deduped = (
                _ebitda_rows.sort_values("_p")
                .groupby("year", as_index=False).first()
                .sort_values("year")
            )
            for _, _row in _ebd_deduped.iterrows():
                try:
                    ebitda_series.append({"year": _row["year"], "value": float(_row["value"])})
                except (TypeError, ValueError):
                    pass
        else:
            # Fallback: compute from Revenue - Cost components
            for yr in sorted(years_sorted):
                def _gvy(it, _yr=yr):
                    s = df[(df["financial_item"] == it) & (df["year"] == _yr)]
                    return float(s["value"].iloc[0]) if not s.empty else None
                rv_ = _gvy("Revenue from Operations")
                co_ = _gvy("Total Cost")
                fi_ = _gvy("Finance Costs") or 0
                de_ = _gvy("Depreciation and Amortisation") or 0
                if rv_ is not None and co_ is not None:
                    ebitda_series.append({"year": yr, "value": round(rv_ - co_ + fi_ + de_, 2)})
                elif _gvy("EBITDA") is not None:
                    ebitda_series.append({"year": yr, "value": _gvy("EBITDA")})

        if ebitda_series:
            trend["EBITDA"] = ebitda_series

        # EBIT trend: EBITDA - Depreciation per year
        ebit_series = []
        for pt in ebitda_series:
            yr = pt["year"]
            def _gvy2(it, cat=None, _yr=yr):
                s = df[(df["financial_item"]==it) & (df["year"]==_yr)]
                if cat:
                    s = s[s["financial_category"]==cat]
                return float(s["value"].iloc[0]) if not s.empty else None
            # Prefer Altman Z D&A (INR Million); fallback P&L (Crores ÷ 10)
            dep_ = _gvy2("Depreciation and Amortisation", cat="Altman Z")
            if dep_ is None:
                dep_pnl = _gvy2("Depreciation and Amortisation")
                dep_ = dep_pnl / 10 if dep_pnl is not None else None
            if dep_ is not None:
                ebit_series.append({"year": yr, "value": round(pt["value"] - dep_, 2)})
        if ebit_series:
            trend["EBIT"] = ebit_series

        z_trend_df = df[df["financial_item"] == "Altman Z Score"].sort_values("year")
        if not z_trend_df.empty:
            trend["Altman Z Score"] = [{"year": r["year"], "value": r["value"]}
                                        for _, r in z_trend_df.iterrows()]
        else:
            # Compute Z per year from Altman input components.
            # Pre-build two lookup structures once to avoid O(n) DataFrame filtering
            # inside the year loop (was 10+ filter calls × N years = very slow).
            #   _df_cat_idx: {(item, year, category): value}   for category-specific lookups
            #   _df_best:    {(item, year): value}              priority-resolved (Altman Z > P&L)
            _df_cat_idx: dict = {}
            _df_best: dict = {}
            for _, _r in df.iterrows():
                _item = str(_r["financial_item"])
                _yr   = str(_r["year"])
                _cat  = str(_r.get("financial_category", ""))
                _v    = _r["value"]
                if _v is None:
                    continue
                try:
                    _fv = float(_v)
                except (TypeError, ValueError):
                    continue
                _df_cat_idx[(_item, _yr, _cat)] = _fv
                _p = CAT_PRIORITY.get(_cat, 9)
                if (_item, _yr) not in _df_best or _p < _df_best[(_item, _yr)][1]:
                    _df_best[(_item, _yr)] = (_fv, _p)

            def _fast_gvy(item, yr_s, cat=None):
                if cat:
                    return _df_cat_idx.get((item, yr_s, cat))
                entry = _df_best.get((item, yr_s))
                return entry[0] if entry else None

            z_series = []
            for yr in sorted(years_sorted):
                yr_s = str(yr)
                gvy  = lambda item, cat=None, _ys=yr_s: _fast_gvy(item, _ys, cat)
                ta_  = gvy("Total Assets") or 1
                wc_  = (gvy("Current Assets") or 0) - (gvy("Current Liabilities") or 0)
                re_  = gvy("Retained Earnings") or gvy("Other Equity (Includes Reserves)") or 0
                _dep = gvy("Depreciation and Amortisation", cat="Altman Z")
                if _dep is None:
                    _dep_pnl = gvy("Depreciation and Amortisation")
                    _dep = (_dep_pnl / 10) if _dep_pnl is not None else 0
                eb_  = gvy("EBIT") or ((gvy("EBITDA") or 0) - _dep)
                mv_  = gvy("Market Capitalization") or 0
                rv_  = gvy("Revenue from Operations") or 0
                tl_  = ta_ - (gvy("Net Worth") or gvy("Total Equity") or 0)
                if ta_ > 0:
                    z_ = round(
                        1.2*(wc_/ta_) + 1.4*(re_/ta_) + 3.3*(eb_/ta_)
                        + 0.6*(mv_/max(tl_, 1)) + 1.0*(rv_/ta_), 2
                    )
                    z_series.append({"year": yr, "value": z_})
            if z_series:
                trend["Altman Z Score"] = z_series

        # Cost structure — use same canonical aggregation as Excel engine (source of truth)
        def gv_cost(item): return get_val(item, latest_year, prefer_cat=cat_filter) or 0

        raw_mat = (gv_cost("Cost of Materials Consumed")
                 + gv_cost("Purchases of Stock-in-Trade")
                 + gv_cost("Changes in Inventories"))

        cost_canonical = [
            ("Raw Material Cost",           raw_mat if raw_mat else None),
            ("Consumables",                 gv_cost("Consumables") or None),
            ("Power & Fuel",                gv_cost("Power, Fuel and Electricity") or None),
            ("Transportation",              gv_cost("Transportation Cost") or None),
            ("Manpower",                    gv_cost("Employee Benefit Expenses") or None),
            ("Rest in Other Expenses",      gv_cost("Rest in Other Expenses") or None),
            ("Finance Costs",               gv_cost("Finance Costs") or None),
            ("Depreciation & Amortization", gv_cost("Depreciation and Amortisation") or None),
        ]
        cost_data = [
            {"item": label, "value": val}
            for label, val in cost_canonical
            if val and val > 0
        ]

        _result = self._clean_nan({
            "company_id": company_id, "latest_year": latest_year,
            "years": years_sorted, "kpis": kpis,
            "trend": trend, "cost_structure": cost_data,
            "report_type": report_type,
        })
        if not re_staging and not altman_staging:
            self._resp_cache[_cache_key] = (_now, _result)
        return _result

    def get_altman_detail(self, company_id: str, period: Optional[str] = None,
                           re_staging: Optional[dict] = None,
                           altman_staging: Optional[dict] = None) -> dict:
        """Return full Altman Z decomposition for a specific period.

        re_staging:     {period: {"value": float, "field": str}}  — RE override from staging
        altman_staging: {period: {financial_item: float}}          — ALL Altman Z row overrides
                        Ensures decomposition matches Data Input immediately, even before Analyze.
        """
        _empty_components = {
            "X1": {"value": None, "weight": 1.2, "name": "Working Capital / Total Assets"},
            "X2": {"value": None, "weight": 1.4, "name": "Retained Earnings / Total Assets"},
            "X3": {"value": None, "weight": 3.3, "name": "EBIT / Total Assets"},
            "X4": {"value": None, "weight": 0.6, "name": "Market Value of Equity / Total Liabilities"},
            "X5": {"value": None, "weight": 1.0, "name": "Sales / Total Assets"},
        }
        # ── DATA SOURCE: identical to Excel/legacy path ────────────────────────
        # Uses reshaper.get_altman_wide (Altman Z category, FY years, active rows)
        # + get_pnl_wide for Depreciation — exactly what run_analysis feeds the
        # legacy BankruptcyAnalysis engine. Guarantees decomposition == gauge == Excel.
        try:
            wide, engine_years = self.reshaper.get_altman_wide(company_id)
            pnl_co,  _ = self.reshaper.get_pnl_wide(company_id, "P&L Consolidated")
            pnl_std, _ = self.reshaper.get_pnl_wide(company_id, "P&L Standalone")
        except Exception:
            return {"year": period, "z_score": None, "zone": "unknown",
                    "components": _empty_components, "z_trend": [], "error": "Warehouse unavailable"}
        if wide is None or wide.empty or not engine_years:
            return {"year": period, "z_score": None, "zone": "unknown",
                    "components": _empty_components, "z_trend": [],
                    "message": "No warehouse data for this company"}

        def W(label, yr):
            """Altman-wide lookup — same frame the legacy engine reads."""
            try:
                if label in wide.index and yr in wide.columns:
                    v = wide.loc[label, yr]
                    if v is not None and not (isinstance(v, float) and math.isnan(v)):
                        return float(v)
            except Exception:
                pass
            return None

        def WS(label, yr):
            """Staging-first lookup: checks altman_staging before warehouse.
            Fixes stale-warehouse bugs where Total Assets, Net Worth, etc.
            were re-entered in Data Input but not yet re-analyzed.
            """
            # Priority 1: fresh staging value
            if altman_staging:
                stg_yr = (altman_staging or {}).get(yr, {})
                if label in stg_yr:
                    return stg_yr[label]
            # Priority 2: warehouse
            return W(label, yr)

        def P(label, yr):
            """P&L-wide lookup: consolidated first, standalone fallback (legacy order)."""
            for frame in (pnl_co, pnl_std):
                try:
                    if frame is not None and not frame.empty \
                       and label in frame.index and yr in frame.columns:
                        v = frame.loc[label, yr]
                        if v is not None and not (isinstance(v, float) and math.isnan(v)):
                            return float(v)
                except Exception:
                    pass
            return None

        # Direct "Retained Earnings" rows (analyst-entered) — Altman Z category
        try:
            re_df = self.engine.get_company_history(company_id, category="Altman Z")
        except Exception:
            re_df = None

        def re_direct_lookup(yr):
            """Direct RE from warehouse (Altman Z category), checking aliases."""
            if re_df is None or re_df.empty:
                return None, None
            for field in ["Retained Earnings", "Reserves & Surplus",
                          "Retained Profit", "Retained Earnings / Deficit"]:
                sub = re_df[(re_df["financial_item"] == field) & (re_df["year"] == yr)]
                if not sub.empty:
                    return float(sub["value"].iloc[0]), field
            return None, None

        # engine_years are FY labels sorted DESC (newest first) — legacy ordering
        years_desc = engine_years
        year = period if period and period in years_desc else years_desc[0]

        def prev_year_of(yr):
            """Legacy prev-year rule: next item in DESC list; FY19 fallback for oldest."""
            try:
                k = years_desc.index(yr)
            except ValueError:
                return None
            return years_desc[k + 1] if k + 1 < len(years_desc) else "FY19"

        def compute_x2(yr):
            """X2 numerator with priority: staging → direct warehouse row → OE directly."""
            # 1. staging override (entered in Data Input, even before Analyze)
            if re_staging:
                stg = re_staging.get(yr)
                if stg is not None:
                    return stg["value"], "direct", stg.get("field", "Retained Earnings")
            # 2. direct warehouse row
            v, fld = re_direct_lookup(yr)
            if v is not None:
                return v, "direct", fld
            # 3. fallback: use Other Equity DIRECTLY (not delta vs prior year)
            oe_c = W("Other Equity (Includes Reserves)", yr)
            if oe_c is not None:
                return oe_c, "direct_oe", None
            return None, "not_available", None

        def compute_components(yr):
            """All five ratios for one year using staging-first inputs."""
            ta     = WS("Total Assets",         yr)
            ca     = WS("Current Assets",        yr)
            cl     = WS("Current Liabilities",   yr)
            nw     = WS("Net Worth",             yr)
            mv     = WS("Market Capitalization", yr)
            rev    = WS("Revenue from Operations", yr)
            ebitda = WS("EBITDA", yr) or 0
            # D&A: prefer Altman Z input (INR Million); fallback P&L (Crores ÷ 10)
            dep_altman = WS("Depreciation and Amortisation", yr)
            if dep_altman is not None:
                ebit = round(ebitda - dep_altman, 2)
            else:
                dep_pnl = P("Depreciation & amortisation", yr) or 0
                ebit = round(ebitda - dep_pnl / 10, 2)
            wc     = (ca - cl) if (ca is not None and cl is not None) else None
            tl     = (ta - nw) if (ta is not None and nw is not None) else None
            re_v, re_src, re_fld = compute_x2(yr)
            return ta, wc, re_v, re_src, re_fld, ebit, mv, tl, rev

        ta, wc, re, x2_source, re_field, ebit, mv, tl, rev = compute_components(year)

        # X2 source labelling + tooltip
        pyr_lbl = prev_year_of(year)
        if x2_source == "direct":
            x2_source_label = f"Retained Earnings / Total Assets\n(Source: Direct — {re_field})"
            x2_tooltip      = {
                "Source":               "Direct Retained Earnings",
                f"{year} {re_field}":   round(re, 2) if re is not None else None,
                "Priority":             "User-entered value — OE fallback bypassed",
            }
        elif x2_source == "direct_oe":
            oe_c = W("Other Equity (Includes Reserves)", year)
            x2_source_label = "Retained Earnings / Total Assets\n(Source: Other Equity — used directly)"
            x2_tooltip      = {
                f"{year} Other Equity":  oe_c,
                "Note": "No direct Retained Earnings row — Other Equity used as-is (not delta)",
            }
        else:
            x2_source_label = "Retained Earnings / Total Assets\n(Not Available)"
            x2_tooltip      = {"reason": f"No Retained Earnings or Other Equity data for {year}"}

        x1 = self._safe_div(wc,   ta)
        x2 = self._safe_div(re,   ta)
        x3 = self._safe_div(ebit, ta)
        x4 = self._safe_div(mv,   tl if tl else None)
        x5 = self._safe_div(rev,  ta)

        z = None
        if all(v is not None for v in [x1, x2, x3, x4, x5]):
            z = round(1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5, 2)

        # ── Z trend across all engine years (ascending for chart) ─────────────
        z_trend = []
        for _yr in sorted(years_desc):
            _ta, _wc, _re, _src, _fld, _eb, _mv, _tl, _rv = compute_components(_yr)
            _vals = [self._safe_div(_wc, _ta), self._safe_div(_re, _ta),
                     self._safe_div(_eb, _ta), self._safe_div(_mv, _tl if _tl else None),
                     self._safe_div(_rv, _ta)]
            if all(v is not None for v in _vals):
                _z = round(1.2*_vals[0] + 1.4*_vals[1] + 3.3*_vals[2]
                           + 0.6*_vals[3] + 1.0*_vals[4], 2)
                z_trend.append({"year": _yr, "value": _z})

        return self._clean_nan({
            "year": year, "z_score": z,
            "zone": "safe" if z and z > 2.99 else "grey" if z and z > 1.81 else "distress",
            "components": {
                "X1": {"value": x1, "weight": 1.2, "name": "Working Capital / Total Assets"},
                "X2": {
                    "value":        x2,
                    "weight":       1.4,
                    "name":         "Retained Earnings / Total Assets",
                    "source":       x2_source,
                    "source_label": x2_source_label,
                    "tooltip":      x2_tooltip,
                },
                "X3": {"value": x3, "weight": 3.3, "name": "EBIT / Total Assets"},
                "X4": {"value": x4, "weight": 0.6, "name": "Market Value of Equity / Total Liabilities"},
                "X5": {"value": x5, "weight": 1.0, "name": "Sales / Total Assets"},
            },
            "z_trend": z_trend,
        })

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _safe_div(n, d, pct=False):
        if n is None or not d or d == 0:
            return None
        r = n / d
        return round(r * 100, 2) if pct else round(r, 4)

    @staticmethod
    def _safe_sub(a, b):
        if a is None or b is None:
            return None
        return a - b

    @staticmethod
    def _clean_nan(obj):
        if isinstance(obj, float):
            return None if (math.isnan(obj) or math.isinf(obj)) else obj
        if isinstance(obj, dict):
            return {k: AnalyticsService._clean_nan(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [AnalyticsService._clean_nan(v) for v in obj]
        return obj

    @staticmethod
    def _serialize_cs(cs: dict, years: list) -> dict:
        result = {}
        for key, df in cs.items():
            if hasattr(df, "to_dict"):
                try:
                    result[key] = AnalyticsService._clean_nan(df.to_dict("records"))
                except Exception:
                    result[key] = str(df)
        return result

    @staticmethod
    def _serialize_bk(bk: dict, years: list) -> dict:
        result = {}
        for key, val in bk.items():
            if hasattr(val, "to_dict"):
                try:
                    result[key] = AnalyticsService._clean_nan(val.to_dict("records"))
                except Exception:
                    result[key] = str(val)
            else:
                result[key] = AnalyticsService._clean_nan(val)
        return result
