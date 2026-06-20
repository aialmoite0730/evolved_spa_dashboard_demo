from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, Request

from config import FULL_SALES, FULL_SCHEDULE
from db import run_query
from utils.filters import loc_in, hhmm_to_hours, is_positive_duration
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
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        date_range = _build_date_range(s, e)
        pivot_cols = ",\n        ".join(
            f"SUM(CASE WHEN CAST(date AS DATE) = '{d}' THEN {hhmm_to_hours('booked_hours')} ELSE 0 END)"
            f" * 1.0"
            f" / NULLIF(SUM(CASE WHEN CAST(date AS DATE) = '{d}' THEN {hhmm_to_hours('scheduled_hours')} ELSE 0 END), 0)"
            f" * 100 AS d_{d.strftime('%Y%m%d')}"
            for d in date_range
        )

        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            center_name                                                                     AS center,
            job_name                                                                        AS role,
            employee_name                                                                   AS name,
            SUM({hhmm_to_hours('booked_hours')}) * 1.0 / NULLIF(SUM({hhmm_to_hours('scheduled_hours')}), 0) * 100 AS tot,
            {pivot_cols}
        FROM {FULL_SCHEDULE}
        WHERE CAST(date AS DATE) BETWEEN '{s}' AND '{e}'
          AND job_name IN ('Treatment Provider', 'Esthetician')
          AND {is_positive_duration('scheduled_hours')}
          {loc_and}
        GROUP BY center_name, job_name, employee_name
        HAVING SUM({hhmm_to_hours('scheduled_hours')}) > 0
        ORDER BY job_name, center_name, employee_name
        """
        rows = run_query(sql, loc_params or None)
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
    """Per-employee daily revenue per utilized hour."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        date_range = _build_date_range(s, e)
        # Pivot columns now read off `daily` — a CTE where schedule and sales
        # have already been pre-aggregated to (center, employee, day) grain
        # and joined 1:1. No fan-out risk, so summing booked_hours per day
        # here is safe.
        pivot_cols = ",\n        ".join(
            f"SUM(CASE WHEN daily.work_date = '{d}' THEN daily.daily_revenue ELSE 0 END)"
            f" * 1.0"
            f" / NULLIF(SUM(CASE WHEN daily.work_date = '{d}' THEN daily.booked_hours ELSE 0 END), 0)"
            f" AS d_{d.strftime('%Y%m%d')}"
            for d in date_range
        )

        loc_and_es, loc_params_es = loc_in(locations, col="es.center_name")
        loc_and_sa, loc_params_sa = loc_in(locations, col="sa.center_name")

        sql = f"""
        WITH sched_by_day AS (
            -- Pre-aggregate to (center, employee, day) BEFORE joining to sales.
            -- Joining line-item-grain sales directly to raw schedule rows and
            -- summing booked_hours over the joined result re-adds the same
            -- day's hours once per sales line item (fan-out), understating
            -- rev/hr. Aggregating each side to matching grain first prevents
            -- that.
            SELECT
                center_name,
                employee_name,
                job_name,
                CAST(date AS DATE)                       AS work_date,
                SUM({hhmm_to_hours('booked_hours')})     AS booked_hours
            FROM {FULL_SCHEDULE} es
            WHERE CAST(date AS DATE) BETWEEN '{s}' AND '{e}'
              AND job_name IN ('Treatment Provider', 'Esthetician')
              AND {is_positive_duration('booked_hours')}
              {loc_and_es}
            GROUP BY center_name, employee_name, job_name, CAST(date AS DATE)
        ),
        sales_by_day AS (
            SELECT
                center_name,
                serviced_by,
                CAST(sale_date AS DATE) AS sale_date,
                SUM(sales_exc_tax)      AS daily_revenue
            FROM {FULL_SALES} sa
            WHERE CAST(sale_date AS DATE) BETWEEN '{s}' AND '{e}'
              {loc_and_sa}
            GROUP BY center_name, serviced_by, CAST(sale_date AS DATE)
        ),
        daily AS (
            SELECT
                sch.center_name,
                sch.employee_name,
                sch.job_name,
                sch.work_date,
                sch.booked_hours,
                COALESCE(sa.daily_revenue, 0) AS daily_revenue
            FROM sched_by_day sch
            LEFT JOIN sales_by_day sa
              ON sa.serviced_by = sch.employee_name
             AND sa.sale_date   = sch.work_date
             AND sa.center_name = sch.center_name
        )
        SELECT
            daily.center_name                                                                 AS center,
            daily.job_name                                                                     AS role,
            daily.employee_name                                                                AS name,
            SUM(daily.daily_revenue) * 1.0 / NULLIF(SUM(daily.booked_hours), 0)               AS tot,
            {pivot_cols}
        FROM daily
        GROUP BY daily.center_name, daily.job_name, daily.employee_name
        ORDER BY daily.job_name, daily.center_name, daily.employee_name
        """
        params = (loc_params_es + loc_params_sa) if (loc_params_es or loc_params_sa) else None
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
    """Combined MTD scorecard per employee: utilization, rev/hr, total revenue."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        loc_and_es, loc_params_es = loc_in(locations, col="es.center_name")
        loc_and_sa, loc_params_sa = loc_in(locations, col="sa.center_name")
        loc_and,    loc_params    = loc_in(locations)

        sql = f"""
        WITH sched AS (
            SELECT
                center_name,
                job_name,
                employee_name,
                SUM({hhmm_to_hours('booked_hours')})    AS booked_hours,
                SUM({hhmm_to_hours('scheduled_hours')}) AS scheduled_hours
            FROM {FULL_SCHEDULE}
            WHERE CAST(date AS DATE) BETWEEN '{s}' AND '{e}'
              AND job_name IN ('Treatment Provider', 'Esthetician')
              AND {is_positive_duration('scheduled_hours')}
              {loc_and}
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
             AND CAST(sa.sale_date AS DATE) = CAST(es.date AS DATE)
             AND sa.center_name = es.center_name
            WHERE CAST(es.date AS DATE) BETWEEN '{s}' AND '{e}'
              AND es.job_name IN ('Treatment Provider', 'Esthetician')
              AND {is_positive_duration('es.booked_hours')}
              {loc_and_es}
              {loc_and_sa}
            GROUP BY es.center_name, es.job_name, es.employee_name
        )
        SELECT
            s.center_name                                                                   AS center,
            s.job_name                                                                      AS role,
            s.employee_name                                                                 AS name,
            s.booked_hours * 1.0 / NULLIF(s.scheduled_hours, 0) * 100                     AS utilization,
            COALESCE(r.total_revenue, 0) * 1.0 / NULLIF(s.booked_hours, 0)                AS rev_per_hr,
            COALESCE(r.total_revenue, 0)                                                    AS total_revenue,
            s.booked_hours,
            s.scheduled_hours
        FROM sched s
        LEFT JOIN rev r
          ON s.center_name   = r.center_name
         AND s.job_name      = r.job_name
         AND s.employee_name = r.employee_name
        ORDER BY s.job_name, COALESCE(r.total_revenue, 0) DESC
        """
        params = loc_params + loc_params_es + loc_params_sa
        return run_query(sql, params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)