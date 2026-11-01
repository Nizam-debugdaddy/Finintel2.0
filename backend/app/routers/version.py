from fastapi import APIRouter, Depends
from app.db.sqlite_db import get_db

router = APIRouter()

@router.get("/{company_id}")
async def list_versions(company_id: str, db=Depends(get_db)):
    async with db.execute(
        "SELECT * FROM versions WHERE company_id=? ORDER BY created_at DESC",
        (company_id,)
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]
