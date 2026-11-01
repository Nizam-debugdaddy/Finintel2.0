from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from app.db.sqlite_db import get_db

router = APIRouter()

class CompanyCreate(BaseModel):
    company_id: str
    company_name: str
    ticker: str = ""
    isin: str = ""
    sectors: List[dict] = []   # [{"sector": "Pharma", "sub_sector": "Generics"}, ...]
    # Legacy single-sector fields still supported
    sector: str = ""
    sub_sector: str = ""

class SectorAssign(BaseModel):
    sector: str
    sub_sector: str = ""

@router.get("")
async def list_companies(db=Depends(get_db)):
    async with db.execute("""
        SELECT c.company_id, c.company_name, c.ticker, c.active_flag,
               STRING_AGG(s.sector || '|' || COALESCE(s.sub_sector,''), ', ') as sectors_raw
        FROM companies c
        LEFT JOIN sectors s ON c.company_id = s.company_id
        WHERE c.active_flag = 1
        GROUP BY c.company_id ORDER BY c.company_name
    """) as cur:
        rows = await cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        raw = d.pop("sectors_raw", "") or ""
        sector_list = []
        for part in raw.split(", "):
            if "|" in part:
                sec, sub = part.split("|", 1)
                if sec.strip():
                    sector_list.append({"sector": sec.strip(), "sub_sector": sub.strip()})
        d["sectors"] = sector_list
        d["sectors_display"] = ", ".join(s["sector"] for s in sector_list)
        result.append(d)
    return result

@router.get("/{company_id}")
async def get_company(company_id: str, db=Depends(get_db)):
    async with db.execute("SELECT * FROM companies WHERE company_id=?", (company_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, f"Company {company_id} not found")
    company = dict(row)
    async with db.execute("SELECT sector, sub_sector FROM sectors WHERE company_id=?", (company_id,)) as cur:
        company["sectors"] = [dict(r) for r in await cur.fetchall()]
    return company

@router.post("", status_code=201)
async def create_company(data: CompanyCreate, db=Depends(get_db)):
    try:
        cid = data.company_id.strip().upper()
        await db.execute(
            "INSERT INTO companies(company_id,company_name,ticker,isin) VALUES(?,?,?,?)",
            (cid, data.company_name, data.ticker, data.isin)
        )
        # Collect all sectors (new list format + legacy single)
        all_sectors = list(data.sectors)
        if data.sector and not any(s["sector"] == data.sector for s in all_sectors):
            all_sectors.append({"sector": data.sector, "sub_sector": data.sub_sector})
        for s in all_sectors:
            if s.get("sector"):
                await db.execute(
                    "INSERT INTO sectors(company_id,sector,sub_sector) VALUES(?,?,?) ON CONFLICT (company_id, sector) DO NOTHING",
                    (cid, s["sector"], s.get("sub_sector", ""))
                )
        await db.commit()
        return {"company_id": cid, "status": "created"}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/{company_id}/sector")
async def assign_sector(company_id: str, data: SectorAssign, db=Depends(get_db)):
    await db.execute(
        "INSERT INTO sectors(company_id,sector,sub_sector) VALUES(?,?,?) ON CONFLICT (company_id, sector) DO NOTHING",
        (company_id, data.sector, data.sub_sector)
    )
    await db.commit()
    return {"status": "assigned"}

@router.delete("/{company_id}/sector/{sector}")
async def remove_sector(company_id: str, sector: str, db=Depends(get_db)):
    await db.execute("DELETE FROM sectors WHERE company_id=? AND sector=?", (company_id, sector))
    await db.commit()
    return {"status": "removed"}


@router.delete("/{company_id}")
async def delete_company(company_id: str, db=Depends(get_db)):
    """
    Permanently delete a company and ALL its data:
      - warehouse Parquet (deactivate all rows)
      - SQLite: financial_inputs, versions, audit_log, sectors, companies
    """
    from app.services.service_factory import get_fresh_service
    svc = get_fresh_service()

    # 1. Remove from warehouse (Parquet)
    wh_rows = svc.remove_all_from_warehouse(company_id)

    # 2. Purge SQLite staging + metadata
    await db.execute("DELETE FROM financial_inputs WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM versions       WHERE company_id=?", (company_id,))
    await db.execute("DELETE FROM sectors        WHERE company_id=?", (company_id,))
    await db.execute(
        "INSERT INTO audit_log(event_type,company_id,detail) VALUES('DELETE',?,?)",
        (company_id, f"Permanently deleted — {wh_rows} warehouse rows deactivated")
    )
    await db.execute("DELETE FROM companies WHERE company_id=?", (company_id,))
    await db.commit()

    return {
        "status":      "deleted",
        "company_id":  company_id,
        "warehouse_rows_removed": wh_rows,
    }


@router.get("/sectors/list")
async def list_sectors(db=Depends(get_db)):
    async with db.execute("SELECT DISTINCT sector FROM sectors ORDER BY sector") as cur:
        rows = await cur.fetchall()
    return [r[0] for r in rows]


@router.get("/sector/{sector}/companies")
async def companies_in_sector(sector: str, db=Depends(get_db)):
    async with db.execute("""
        SELECT c.company_id, c.company_name, s.sub_sector
        FROM companies c JOIN sectors s ON c.company_id=s.company_id
        WHERE s.sector=? AND c.active_flag=1
    """, (sector,)) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
