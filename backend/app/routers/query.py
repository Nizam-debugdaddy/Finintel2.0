from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.service_factory import get_service

router = APIRouter()

class SQLQuery(BaseModel):
    sql: str

@router.post("/sql")
async def run_sql(query: SQLQuery):
    try:
        df = get_service().engine.sql(query.sql)
        return df.to_dict("records")
    except Exception as e:
        raise HTTPException(400, str(e))

@router.get("/companies/{company_id}/history")
async def company_history(company_id: str):
    try:
        df = get_service().engine.get_company_history(company_id)
        return df.to_dict("records")
    except Exception as e:
        raise HTTPException(500, str(e))
