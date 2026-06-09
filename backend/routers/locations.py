from fastapi import APIRouter, Request
from config import FULL_SALES
from db import run_query
from utils.errors import log_and_raise_from_request

router = APIRouter()


@router.get("/api/locations")
def get_locations(request: Request):
    """Return distinct center_name values from sales_accrual, sorted."""
    try:
        sql = f"""
        SELECT DISTINCT center_name
        FROM {FULL_SALES}
        WHERE center_name IS NOT NULL
        ORDER BY center_name
        """
        rows = run_query(sql)
        return [r["center_name"] for r in rows]

    except Exception as exc:
        log_and_raise_from_request(exc, request)
