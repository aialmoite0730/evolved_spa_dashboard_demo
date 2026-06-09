import calendar
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Query, Request

from config import FULL_SALES, FULL_SCHEDULE, FULL_APPT
from db import run_query, serialize_rows
from utils.filters import (
    build_date_filter,
    build_sched_filter,
    build_join_where,
    merge_params,
)
from utils.errors import log_and_raise_from_request

router = APIRouter()

# ── Shared schedule + rev-by-role CTEs ────────────────────────────────────────
# Both endpoints need these; extracted to avoid duplication.

def _schedule_and_rev_ctEs(
    sched_block: str,
    join_where:  str,
    full_schedule: str,
    full_sales: str,
) -> str:
    """Return the schedule_agg and rev_by_role CTE bodies (without the WITH keyword)."""
    return f"""
    schedule_agg AS (
        SELECT
            center_name,
            SAFE_DIVIDE(
                SUM(CASE WHEN job_name = 'Treatment Provider' THEN booked_hours ELSE 0 END),
                NULLIF(SUM(CASE WHEN job_name = 'Treatment Provider' THEN scheduled_hours ELSE 0 END), 0)
            ) * 100 AS provider_utilization,
            SAFE_DIVIDE(
                SUM(CASE WHEN job_name = 'Esthetician' THEN booked_hours ELSE 0 END),
                NULLIF(SUM(CASE WHEN job_name = 'Esthetician' THEN scheduled_hours ELSE 0 END), 0)
            ) * 100 AS esthetician_utilization
        FROM {full_schedule}
        {sched_block}
        GROUP BY center_name
    ),
    rev_by_role AS (
        SELECT
            sa.center_name,
            SAFE_DIVIDE(
                SUM(CASE WHEN es.job_name = 'Treatment Provider' THEN sa.sales_exc_tax ELSE 0 END),
                NULLIF(SUM(CASE WHEN es.job_name = 'Treatment Provider' THEN es.booked_hours ELSE 0 END), 0)
            ) AS rev_per_provider,
            SAFE_DIVIDE(
                SUM(CASE WHEN es.job_name = 'Esthetician' THEN sa.sales_exc_tax ELSE 0 END),
                NULLIF(SUM(CASE WHEN es.job_name = 'Esthetician' THEN es.booked_hours ELSE 0 END), 0)
            ) AS rev_per_esthetician
        FROM {full_sales} sa
        JOIN {full_schedule} es
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        {join_where}
        GROUP BY sa.center_name
    )"""


@router.get("/api/operations-summary")
def get_operations_summary(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Per-location operational metrics table (Operations tab).
    Sales from sales_accrual; utilization from employee_schedule;
    Rev/Hr from sales JOIN schedule on serviced_by = employee_name.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        where, params         = build_date_filter(s, e, locations)
        _, sched_raw          = build_date_filter(s, e, locations, date_col="date")
        sched_block, sched_x  = build_sched_filter(s, e, locations, sched_raw)
        join_where            = build_join_where(where)
        all_params            = merge_params(params, sched_x)

        days_in_month = calendar.monthrange(
            datetime.strptime(e, "%Y-%m-%d").year,
            datetime.strptime(e, "%Y-%m-%d").month,
        )[1]

        appt_loc = "AND center_name IN UNNEST(@locations)" if locations else ""

        shared_ctes = _schedule_and_rev_ctEs(sched_block, join_where, FULL_SCHEDULE, FULL_SALES)

        sql = f"""
        WITH sales AS (
            SELECT
                center_name,
                SUM(sales_inc_tax)                                                                  AS recognized_revenue,
                SAFE_DIVIDE(SUM(sales_inc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))         AS avg_daily_revenue,
                SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT guest_id), 0))                AS asp,
                SAFE_DIVIDE(
                    SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                   AS asp_excl_memberships,
                COUNT(DISTINCT invoice_id)                                                          AS appointment_count,
                COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                    AS new_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = false THEN guest_id END)                    AS existing_client_count
            FROM {FULL_SALES}
            {where}
            GROUP BY center_name
        ),
        {shared_ctes},
        rebooking AS (
            SELECT
                center_name,
                SAFE_DIVIDE(COUNTIF(rebooked = true), NULLIF(COUNT(*), 0)) * 100 AS rebooking_rate
            FROM {FULL_APPT}
            WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
              AND status = 'Closed'
              AND add_on = 'No'
              {appt_loc}
            GROUP BY center_name
        )
        SELECT
            s.center_name                                       AS location,
            s.recognized_revenue,
            s.avg_daily_revenue,
            s.avg_daily_revenue * {days_in_month}               AS trending,
            ROUND(20.0,             1)                           AS cogs_pct,
            ROUND(22.0 * 1.12,      1)                           AS payroll_pct,
            ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)           AS gross_margin_pct,
            s.asp,
            s.asp_excl_memberships,
            s.appointment_count,
            s.new_client_count,
            s.existing_client_count,
            r.rev_per_provider,
            r.rev_per_esthetician,
            sch.provider_utilization,
            sch.esthetician_utilization,
            rb.rebooking_rate,
            CAST(NULL AS INT64)   AS review_count,
            CAST(NULL AS NUMERIC) AS avg_rating
        FROM sales s
        LEFT JOIN schedule_agg  sch ON s.center_name = sch.center_name
        LEFT JOIN rev_by_role   r   ON s.center_name = r.center_name
        LEFT JOIN rebooking     rb  ON s.center_name = rb.center_name
        ORDER BY s.center_name
        """
        return serialize_rows(run_query(sql, all_params))

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/monthly-trend")
def get_monthly_trend(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Monthly trend table — same operational metrics as operations-summary
    but with additional cost / margin breakdown columns.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        where, params         = build_date_filter(s, e, locations)
        _, sched_raw          = build_date_filter(s, e, locations, date_col="date")
        sched_block, sched_x  = build_sched_filter(s, e, locations, sched_raw)
        join_where            = build_join_where(where)
        all_params            = merge_params(params, sched_x)

        days_in_month = calendar.monthrange(
            datetime.strptime(e, "%Y-%m-%d").year,
            datetime.strptime(e, "%Y-%m-%d").month,
        )[1]

        appt_loc   = "AND center_name IN UNNEST(@locations)" if locations else ""
        shared_ctes = _schedule_and_rev_ctEs(sched_block, join_where, FULL_SCHEDULE, FULL_SALES)

        sql = f"""
        WITH sales AS (
            SELECT
                center_name,
                SUM(sales_inc_tax)                                                                  AS recognized_revenue,
                SAFE_DIVIDE(SUM(sales_inc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))         AS avg_daily_revenue,
                ROUND(SUM(sales_inc_tax) * 0.20, 2)                                                 AS cogs_est,
                ROUND(SUM(sales_inc_tax) * 0.22 * 1.12, 2)                                         AS payroll_costs_est,
                ROUND(SUM(sales_inc_tax) * (1 - 0.20 - 0.22 * 1.12), 2)                           AS gross_margin,
                20.0                                                                                 AS cogs_margin,
                ROUND(22.0 * 1.12, 1)                                                               AS payroll_margin,
                ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                                           AS gross_margin_pct,
                SAFE_DIVIDE(
                    SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                   AS asp_excl_memberships,
                COUNT(DISTINCT invoice_id)                                                          AS appointment_count,
                COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                    AS new_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = false THEN guest_id END)                    AS existing_client_count,
                COUNT(DISTINCT guest_id)                                                            AS total_client_count
            FROM {FULL_SALES}
            {where}
            GROUP BY center_name
        ),
        {shared_ctes},
        rebooking AS (
            SELECT
                center_name,
                SAFE_DIVIDE(COUNTIF(rebooked = true), NULLIF(COUNT(*), 0)) * 100 AS rebooking_rate
            FROM {FULL_APPT}
            WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
              AND status = 'Closed'
              AND add_on = 'No'
              {appt_loc}
            GROUP BY center_name
        )
        SELECT
            s.center_name                                       AS location,
            s.recognized_revenue,
            s.avg_daily_revenue,
            s.avg_daily_revenue * {days_in_month}               AS trending,
            s.cogs_est,
            s.payroll_costs_est,
            s.gross_margin,
            s.cogs_margin,
            s.payroll_margin,
            s.gross_margin_pct,
            s.asp_excl_memberships,
            s.appointment_count,
            s.new_client_count,
            s.existing_client_count,
            s.total_client_count,
            r.rev_per_provider,
            r.rev_per_esthetician,
            sch.provider_utilization,
            sch.esthetician_utilization,
            rb.rebooking_rate,
            CAST(NULL AS INT64)    AS review_count,
            CAST(NULL AS NUMERIC)  AS avg_rating
        FROM sales s
        LEFT JOIN schedule_agg  sch ON s.center_name = sch.center_name
        LEFT JOIN rev_by_role   r   ON s.center_name = r.center_name
        LEFT JOIN rebooking     rb  ON s.center_name = rb.center_name
        ORDER BY s.center_name
        """
        return serialize_rows(run_query(sql, all_params))

    except Exception as exc:
        log_and_raise_from_request(exc, request)
