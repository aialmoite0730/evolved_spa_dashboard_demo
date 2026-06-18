from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, Request

from config import FULL_SALES
from db import run_query, serialize_rows
from utils.filters import build_date_filter
from utils.errors import log_and_raise_from_request

router = APIRouter()


@router.get("/api/category-breakdown")
def get_category_breakdown(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Revenue and transaction count by item_category — powers the donut chart."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = build_date_filter(s, e, locations)

        cat_guard = "AND item_category IS NOT NULL" if where else "WHERE item_category IS NOT NULL"

        sql = f"""
        SELECT
            item_category,
            SUM(sales_exc_tax) AS revenue,
            COUNT(*)           AS count
        FROM {FULL_SALES}
        {where}
        {cat_guard}
        GROUP BY item_category
        ORDER BY revenue DESC
        """
        return run_query(sql, params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/revenue-trend")
def get_revenue_trend(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Daily revenue and appointment count — powers the area trend chart."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = build_date_filter(s, e, locations)

        sql = f"""
        SELECT
            CAST(sale_date AS DATE)    AS sale_date,
            SUM(sales_exc_tax)         AS daily_revenue,
            COUNT(DISTINCT invoice_id) AS appointments
        FROM {FULL_SALES}
        {where}
        GROUP BY CAST(sale_date AS DATE)
        ORDER BY sale_date
        """
        return serialize_rows(run_query(sql, params or None))

    except Exception as exc:
        log_and_raise_from_request(exc, request)
