"""
financial_input.py — ROUTE ORDER IS CRITICAL for FastAPI path matching.

FastAPI matches routes top-to-bottom. Static path segments MUST come before
parameterized ones. If /{company_id}/{period} appears before /workspace/{company_id},
FastAPI matches /workspace/SUN as company_id=workspace, period=SUN — returning [] silently.

Correct order:
  1. /template/{company_id}        ← static prefix "template"
  2. /workspace/{company_id}       ← static prefix "workspace" (was WRONG: after /{id}/{period})
  3. /bulk                         ← static
  4. POST /                        ← POST root
  5. DELETE /{company_id}/{period} ← parameterized (DELETE verb — no conflict with GET)
  6. GET /{company_id}/{period}    ← parameterized GET — MUST BE LAST among GETs
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from app.db.sqlite_db import get_db

router = APIRouter()

class InputRow(BaseModel):
    company_id: str
    period_label: str
    financial_item: str
    category: str
    value: Optional[float] = None
    units: str = "INR Million"
    parent_item: Optional[str] = None
    sort_order: Optional[float] = 0   # float accepted, stored as int via round()

    @property
    def sort_order_int(self) -> int:
        return round(self.sort_order or 0)

class BulkInput(BaseModel):
    rows: List[InputRow]

ALL_YEARS = ["FY25", "FY24", "FY23", "FY22", "FY21", "FY20", "FY19"]

# Historical item renames — applied when reading warehouse / staging so old
# parquet data still surfaces under the current display label.
ITEM_RENAMES = {
    "Long Term Debt": "Non Current Liability",
}

# Quarterly columns: Q4FY25 → Q1FY20 (latest first, 24 quarters)
QUARTERS = [
    f"Q{q}FY{fy}"
    for fy in range(25, 19, -1)      # FY25 down to FY20
    for q  in range(4,  0,  -1)      # Q4 down to Q1
]

ALTMAN_ITEMS = [
    "Revenue from Operations",
    "EBITDA",
    "Depreciation and Amortisation",   # INR Million — used to compute EBIT = EBITDA - D&A
    "PAT",
    "Total Assets",
    "Current Assets",
    "Current Liabilities",
    "Short Term Borrowings",
    "Finance Costs",
    "Debtors (Receivables)",
    "Creditors (Payables)",
    "Inventory",
    "Net Worth",
    "Non Current Liability",
    "Market Capitalization",
    "Other Equity (Includes Reserves)",
    "Retained Earnings",          # Optional direct input; if blank, derived from OE delta
]

# Parent-child relationships for the input grid
ITEM_PARENTS = {
    "Retained Earnings": "Other Equity (Includes Reserves)",
}

PNL_ITEMS = [
    "Cost of Materials Consumed",
    "Purchases of Stock-in-Trade",
    "Changes in Inventories",
    "Employee Benefit Expenses",
    "Finance Costs",
    "Depreciation and Amortisation",
    "Other Expenses",
    "Power, Fuel and Electricity",
    "Consumables",
    "Transportation Cost",
    "Rest in Other Expenses",
    "Total Cost",
    "Revenue from Operations",
    "Total Income",
]

def build_template_rows(years: list):
    """Build template rows for ALL years at once — multi-year grid."""
    rows = []
    sort = 0
    for item in ALTMAN_ITEMS:
        row = {"financial_item": item, "category": "Altman Z", "units": "INR Million",
               "parent_item": ITEM_PARENTS.get(item), "sort_order": sort}
        for y in years:
            row[y] = None
        rows.append(row)
        sort += 1
    for cat in ["P&L Consolidated", "P&L Standalone"]:
        for item in PNL_ITEMS:
            row = {"financial_item": item, "category": cat, "units": "INR Million",
                   "parent_item": None, "sort_order": sort}
            for y in years:
                row[y] = None
            rows.append(row)
            sort += 1
    return rows


# ════════════════════════════════════════════════════════════════════════════════
# STATIC-PREFIX ROUTES FIRST — before any /{param}/{param} routes
# ════════════════════════════════════════════════════════════════════════════════

@router.get("/template/{company_id}")
async def get_template(
    company_id: str,
    mode: str = "annual",
    db=Depends(get_db)
):
    """Legacy template endpoint — returns blank rows + any SQLite staging overlay."""
    years = QUARTERS if mode == "quarterly" else ALL_YEARS

    async with db.execute(
        """SELECT financial_item, category, period_label, value, units
           FROM financial_inputs WHERE company_id=?
           ORDER BY category, sort_order""",
        (company_id,)
    ) as cur:
        saved_rows = await cur.fetchall()

    template = build_template_rows(years)

    if saved_rows:
        saved_map: dict = {}
        for r in saved_rows:
            key = (r["financial_item"], r["category"])
            if key not in saved_map:
                saved_map[key] = {}
            saved_map[key][r["period_label"]] = r["value"]

        for row in template:
            key = (row["financial_item"], row["category"])
            if key in saved_map:
                for y in years:
                    if y in saved_map[key]:
                        row[y] = saved_map[key][y]

    return {"source": "template", "rows": template, "years": years, "mode": mode}


@router.get("/workspace/{company_id}")
async def get_workspace(
    company_id: str,
    mode: str = "annual",
    report_type: str = "consolidated",
    db=Depends(get_db)
):
    """
    Smart workspace load:
      1. Reads DuckDB warehouse for existing analysis data
      2. Overlays SQLite staging (analyst edits override warehouse values)
      3. Returns annotated rows: _source = 'warehouse' | 'staged' | 'empty'

    NOTE: This route MUST appear before /{company_id}/{period} in the file.
    FastAPI matches routes top-to-bottom; /workspace/{id} would otherwise be
    swallowed by /{id}/{period} with company_id='workspace'.
    """
    from app.services.service_factory import get_service
    import math

    years = QUARTERS if mode == "quarterly" else ALL_YEARS

    # ── 1. Warehouse data ────────────────────────────────────────────
    warehouse_data: dict = {}
    has_warehouse = False
    warehouse_error: str = ""

    try:
        svc = get_service()
        df  = svc.engine.get_company_history(company_id)

        if not df.empty:
            has_warehouse = True
            for _, row in df.iterrows():
                item = ITEM_RENAMES.get(row["financial_item"], row["financial_item"])
                cat  = row["financial_category"]
                yr   = row["year"]
                val  = row["value"]
                if isinstance(val, float) and math.isnan(val):
                    continue
                key = (item, cat)
                if key not in warehouse_data:
                    warehouse_data[key] = {}
                warehouse_data[key][yr] = val
    except Exception as e:
        warehouse_error = str(e)

    # ── 2. SQLite staging ────────────────────────────────────────────
    staged_data: dict = {}
    try:
        async with db.execute(
            "SELECT financial_item, category, period_label, value "
            "FROM financial_inputs WHERE company_id=?",
            (company_id,)
        ) as cur:
            staged = await cur.fetchall()

        for r in staged:
            item = ITEM_RENAMES.get(r["financial_item"], r["financial_item"])
            key = (item, r["category"])
            if key not in staged_data:
                staged_data[key] = {}
            staged_data[key][r["period_label"]] = r["value"]
    except Exception:
        pass

    # ── 3. Build merged template ─────────────────────────────────────
    template   = build_template_rows(years)
    has_any    = False

    for row in template:
        key = (row["financial_item"], row["category"])
        row["_source"] = "empty"

        # Warehouse values first
        wh = warehouse_data.get(key, {})
        for y in years:
            if y in wh:
                row[y]          = wh[y]
                row["_source"]  = "warehouse"
                has_any         = True

        # Staging overrides warehouse (analyst edits win).
        # NULL in staging = explicit tombstone: user deleted this cell.
        # We check `y in st` (not `st[y] is not None`) so that a NULL
        # tombstone beats a live warehouse value.
        st = staged_data.get(key, {})
        for y in years:
            if y in st:
                row[y] = st[y]          # may be None (tombstone = blank cell)
                # Only mark has_any for real values, not tombstones
                if st[y] is not None:
                    has_any = True
                row["_source"] = "staged"  # staged (even if None) = analyst chose this

    return {
        "source":              "workspace",
        "has_warehouse_data":  has_warehouse,
        "has_any_data":        has_any,
        "rows":                template,
        "years":               years,
        "mode":                mode,
        "report_type":         report_type,
        "company_id":          company_id,
        "warehouse_error":     warehouse_error,   # surfaced for debug panel
        "warehouse_keys":      len(warehouse_data),
        "staged_keys":         len(staged_data),
    }


@router.post("/bulk")
async def bulk_save(data: BulkInput, db=Depends(get_db)):
    """
    Bulk upsert — stores ALL rows including NULL tombstones.
    NULL value = explicit deletion. The workspace overlay reads NULL as
    'user deleted this cell' and ignores any warehouse value underneath.
    """
    import time as _t, logging as _lg
    _log = _lg.getLogger("finintel.perf")
    _t0 = _t.perf_counter()
    saved, rejected = 0, 0
    for row in data.rows:
        try:
            await db.execute(
                """INSERT INTO financial_inputs
                   (company_id,period_label,financial_item,category,value,units,parent_item,sort_order)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(company_id,period_label,financial_item,category)
                   DO UPDATE SET value=excluded.value, saved_at=CURRENT_TIMESTAMP""",
                (row.company_id, row.period_label, row.financial_item, row.category,
                 row.value,       # NULL is stored — this IS the tombstone
                 row.units, row.parent_item, row.sort_order_int)
            )
            saved += 1
        except Exception:
            rejected += 1
    await db.commit()
    _log.warning(f"[BULK_SAVE] {saved} rows saved in {_t.perf_counter()-_t0:.3f}s")
    if data.rows:
        await db.execute(
            "INSERT INTO audit_log(event_type,company_id,rows_affected) VALUES('BULK_SAVE',?,?)",
            (data.rows[0].company_id, saved)
        )
        await db.commit()
    return {"saved": saved, "rejected": rejected}


@router.post("")
async def save_row(row: InputRow, db=Depends(get_db)):
    """Save / update a single input row."""
    await db.execute(
        """INSERT INTO financial_inputs
           (company_id,period_label,financial_item,category,value,units,parent_item,sort_order)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(company_id,period_label,financial_item,category)
           DO UPDATE SET value=excluded.value, units=excluded.units, saved_at=CURRENT_TIMESTAMP""",
        (row.company_id, row.period_label, row.financial_item, row.category,
         row.value, row.units, row.parent_item, row.sort_order_int)
    )
    await db.commit()
    return {"status": "saved"}


# ════════════════════════════════════════════════════════════════════════════════
# PARAMETERIZED ROUTES LAST — these catch-all patterns must come after statics
# ════════════════════════════════════════════════════════════════════════════════

@router.delete("/{company_id}/{period}")
async def clear_input(company_id: str, period: str, db=Depends(get_db)):
    """Delete all staging rows for a specific company+period."""
    await db.execute(
        "DELETE FROM financial_inputs WHERE company_id=? AND period_label=?",
        (company_id, period)
    )
    await db.commit()
    return {"status": "cleared"}


@router.get("/{company_id}/{period}")
async def get_input_data(company_id: str, period: str, db=Depends(get_db)):
    """Get all staged input rows for a company+period."""
    async with db.execute(
        """SELECT financial_item, category, value, units, parent_item, sort_order
           FROM financial_inputs WHERE company_id=? AND period_label=?
           ORDER BY category, sort_order""",
        (company_id, period)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
