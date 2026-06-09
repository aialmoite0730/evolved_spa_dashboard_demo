from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, Request
from google.cloud import bigquery

from config import FULL_SALES, FULL_SCHEDULE
from db import run_query
from utils.errors import log_and_raise_from_request

router = APIRouter()


def _build_date_range(s: str, e: str) -> list:
    """Return list of date objects from s to e inclusive."""
    start_dt = datetime.strptime(s, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
    dates, d = [], start_dt
    while d <= end_dt:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def _rename_pivot_cols(rows: list[dict]) -> list[dict]:
    """Rename d_YYYYMMDD columns to d1, d2, ... preserving chronological order."""
    for row in rows:
        date_cols = sorted(k for k in row if k.startswith("d_"))
        for i, col in enumerate(date_cols, 1):
            row[f"d{i}"] = row.pop(col)
    return rows


@router.get("/api/employee-utilization")
def get_employee_utilization(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Per-employee daily utilization % (booked_hours / scheduled_hours × 100).
    Columns: center, role, name, tot (MTD), d1 … dN (one per calendar day).
    Role comes from employee_schedule.job_name.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        date_range = _build_date_range(s, e)
        pivot_cols = ",\n        ".join(
            f"SAFE_DIVIDE("
            f"SUM(CASE WHEN DATE(date) = '{d}' THEN booked_hours ELSE 0 END), "
            f"NULLIF(SUM(CASE WHEN DATE(date) = '{d}' THEN scheduled_hours ELSE 0 END), 0)"
            f") * 100 AS d_{d.strftime('%Y%m%d')}"
            for d in date_range
        )

        loc_filter = ""
        params     = []
        if locations:
            loc_filter = "AND center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            center_name                                                                     AS center,
            job_name                                                                        AS role,
            employee_name                                                                   AS name,
            SAFE_DIVIDE(SUM(booked_hours), NULLIF(SUM(scheduled_hours), 0)) * 100          AS tot,
            {pivot_cols}
        FROM {FULL_SCHEDULE}
        WHERE DATE(date) BETWEEN '{s}' AND '{e}'
          AND job_name IN ('Treatment Provider', 'Esthetician')
          AND scheduled_hours > 0
          {loc_filter}
        GROUP BY center_name, job_name, employee_name
        HAVING SUM(scheduled_hours) > 0
        ORDER BY job_name, center_name, employee_name
        """
        rows = run_query(sql, params)
        return _rename_pivot_cols(rows)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/employee-rph")
def get_employee_rph(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Per-employee daily revenue per utilized hour.
    Joins sales_accrual.serviced_by → employee_schedule.employee_name.
    Columns: center, role, name, tot (MTD), d1 … dN.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        date_range = _build_date_range(s, e)
        pivot_cols = ",\n        ".join(
            f"SAFE_DIVIDE("
            f"SUM(CASE WHEN DATE(es.date) = '{d}' THEN sa.sales_exc_tax ELSE 0 END), "
            f"NULLIF(SUM(CASE WHEN DATE(es.date) = '{d}' THEN es.booked_hours ELSE 0 END), 0)"
            f") AS d_{d.strftime('%Y%m%d')}"
            for d in date_range
        )

        loc_es = loc_sa = ""
        params = []
        if locations:
            loc_es = "AND es.center_name IN UNNEST(@locations)"
            loc_sa = "AND sa.center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            es.center_name                                                                  AS center,
            es.job_name                                                                     AS role,
            es.employee_name                                                                AS name,
            SAFE_DIVIDE(SUM(sa.sales_exc_tax), NULLIF(SUM(es.booked_hours), 0))            AS tot,
            {pivot_cols}
        FROM {FULL_SCHEDULE} es
        JOIN {FULL_SALES} sa
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        WHERE DATE(es.date) BETWEEN '{s}' AND '{e}'
          AND es.job_name IN ('Treatment Provider', 'Esthetician')
          AND es.booked_hours > 0
          {loc_es}
          {loc_sa}
        GROUP BY es.center_name, es.job_name, es.employee_name
        ORDER BY es.job_name, es.center_name, es.employee_name
        """
        rows = run_query(sql, params)
        return _rename_pivot_cols(rows)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/employee-scorecard")
def get_employee_scorecard(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Combined MTD scorecard per employee: utilization, rev/hr, total revenue.
    Used for the Employee Scorecard tab card grid.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        loc_es = loc_sa = ""
        params = []
        if locations:
            loc_es = "AND es.center_name IN UNNEST(@locations)"
            loc_sa = "AND sa.center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        WITH sched AS (
            SELECT
                center_name,
                job_name,
                employee_name,
                SUM(booked_hours)    AS booked_hours,
                SUM(scheduled_hours) AS scheduled_hours
            FROM {FULL_SCHEDULE}
            WHERE DATE(date) BETWEEN '{s}' AND '{e}'
              AND job_name IN ('Treatment Provider', 'Esthetician')
              AND scheduled_hours > 0
              {loc_es}
            GROUP BY center_name, job_name, employee_name
        ),
        rev AS (
            SELECT
                es.center_name,
                es.job_name,
                es.employee_name,
                SUM(sa.sales_exc_tax) AS total_revenue
            FROM {FULL_SCHEDULE} es
            JOIN {FULL_SALES} sa
              ON sa.serviced_by = es.employee_name
             AND DATE(sa.sale_date) = DATE(es.date)
             AND sa.center_name = es.center_name
            WHERE DATE(es.date) BETWEEN '{s}' AND '{e}'
              AND es.job_name IN ('Treatment Provider', 'Esthetician')
              AND es.booked_hours > 0
              {loc_es}
              {loc_sa}
            GROUP BY es.center_name, es.job_name, es.employee_name
        )
        SELECT
            s.center_name                                                                   AS center,
            s.job_name                                                                      AS role,
            s.employee_name                                                                 AS name,
            SAFE_DIVIDE(s.booked_hours, NULLIF(s.scheduled_hours, 0)) * 100                AS utilization,
            SAFE_DIVIDE(COALESCE(r.total_revenue, 0), NULLIF(s.booked_hours, 0))           AS rev_per_hr,
            COALESCE(r.total_revenue, 0)                                                    AS total_revenue,
            s.booked_hours,
            s.scheduled_hours
        FROM sched s
        LEFT JOIN rev r
          ON s.center_name  = r.center_name
         AND s.job_name     = r.job_name
         AND s.employee_name = r.employee_name
        ORDER BY s.job_name, COALESCE(r.total_revenue, 0) DESC
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)
