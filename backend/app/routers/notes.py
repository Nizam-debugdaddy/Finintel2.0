from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db.sqlite_db import get_db

router = APIRouter()

class NoteCreate(BaseModel):
    company_id: str
    period_label: str
    note: str
    page: str = "general"

@router.get("/{company_id}")
async def get_notes(company_id: str, period: Optional[str] = None, db=Depends(get_db)):
    if period:
        async with db.execute(
            "SELECT * FROM analyst_notes WHERE company_id=? AND period_label=? ORDER BY created_at DESC",
            (company_id, period)
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with db.execute(
            "SELECT * FROM analyst_notes WHERE company_id=? ORDER BY created_at DESC LIMIT 50",
            (company_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]

@router.post("")
async def save_note(data: NoteCreate, db=Depends(get_db)):
    await db.execute(
        "INSERT INTO analyst_notes(company_id,period_label,note,page) VALUES(?,?,?,?)",
        (data.company_id, data.period_label, data.note, data.page)
    )
    await db.commit()
    return {"status": "saved"}

@router.delete("/{note_id}")
async def delete_note(note_id: int, db=Depends(get_db)):
    await db.execute("DELETE FROM analyst_notes WHERE id=?", (note_id,))
    await db.commit()
    return {"status": "deleted"}
