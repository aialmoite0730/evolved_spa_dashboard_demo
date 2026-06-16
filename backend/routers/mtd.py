import calendar
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, Request
from google.cloud import bigquery

from config import FULL_SALES, FULL_SCHEDULE, FULL_APPT
from db import run_query
from utils.filters import (
    build_date_filter,
    build_sched_filter,
    build_join_where,
    merge_params,
)
from utils.errors import log_and_raise_from_request

router = APIRouter()

# ── Shared sales-mix SELECT fragment (same logic in daily and MTD) ──────────
_MIX_COLS = """
    SUM(CASE WHEN item_category = 'Body Contouring'
              OR item_sub_category = 'Body Contouring'     THEN sales_exc_tax ELSE 0 END)  AS body_contouring,
    SUM(CASE WHEN item_category = 'Facials'                THEN sales_exc_tax ELSE 0 END)  AS facials,
    SUM(CASE WHEN item_sub_category = 'Filler'             THEN sales_exc_tax ELSE 0 END)  AS filler,
    SUM(CASE WHEN item_category = 'Laser Hair Removal'
              OR item_sub_category = 'Laser Hair Removal'  THEN sales_exc_tax ELSE 0 END)  AS laser_hair_removal,
    SUM(CASE WHEN item_category = 'Memberships'            THEN sales_exc_tax ELSE 0 END)  AS memberships,
    SUM(CASE WHEN item_sub_category = 'Toxin'              THEN sales_exc_tax ELSE 0 END)  AS neurotoxins,
    SUM(CASE WHEN
            item_category NOT IN (
                'Facials','Memberships','Injectables','Skin Rejuvenation',
                'Retail','Laser Hair Removal','Body Contouring'
            )
            AND item_sub_category NOT IN (
                'Body Contouring','Filler','Laser Hair Removal',
                'Toxin','Other Injectables','PRF'
            )
         THEN sales_exc_tax ELSE 0 END)                                                    AS other,
    SUM(CASE WHEN item_sub_category = 'Other Injectables'  THEN sales_exc_tax ELSE 0 END)  AS other_injectables,
    SUM(CASE WHEN item_sub_category = 'PRF'                THEN sales_exc_tax ELSE 0 END)  AS prf,
    SUM(CASE WHEN item_category = 'Retail'                 THEN sales_exc_tax ELSE 0 END)  AS retail,
    SUM(CASE WHEN item_category = 'Skin Rejuvenation'      THEN sales_exc_tax ELSE 0 END)  AS skin_rejuvenation,
    SUM(sales_exc_tax)                                                                      AS total
"""


@router.get("/api/mtd-kpi-header")
def get_mtd_kpi_header(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Single-row KPI banner shown on every tab.
    Returns both yesterday_revenue (end_date - 1) and last_month_revenue
    (full prior calendar month) so the frontend can choose which to display
    based on viewMode (day vs month).
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        where, params = build_date_filter(s, e, locations)

        # yesterday = end_date - 1 (not server today, so Day view works correctly)
        e_dt      = datetime.strptime(e, "%Y-%m-%d").date()
        s_dt      = datetime.strptime(s, "%Y-%m-%d").date()
        yesterday = e_dt - timedelta(days=1)
        y_param   = bigquery.ScalarQueryParameter("yesterday", "DATE", str(yesterday))
        y_loc     = "AND center_name IN UNNEST(@locations)" if locations else ""

        # Last full calendar month relative to end_date
        lm_end_dt   = e_dt.replace(day=1) - timedelta(days=1)
        lm_start_dt = lm_end_dt.replace(day=1)
        lm_start_p  = bigquery.ScalarQueryParameter("lm_start", "DATE", str(lm_start_dt))
        lm_end_p    = bigquery.ScalarQueryParameter("lm_end",   "DATE", str(lm_end_dt))

        # Prior-year comparison (same elapsed days, one year back)
        try:
            py_start = s_dt.replace(year=s_dt.year - 1)
            py_end   = e_dt.replace(year=e_dt.year - 1)
        except ValueError:
            py_start = s_dt - timedelta(days=365)
            py_end   = e_dt - timedelta(days=365)

        py_where = (
            f"WHERE DATE(sale_date) >= '{py_start}' AND DATE(sale_date) <= '{py_end}'"
            + (" AND center_name IN UNNEST(@locations)" if locations else "")
        )

        # Schedule filter block
        _, sched_raw         = build_date_filter(s, e, locations, date_col="date")
        sched_block, sched_x = build_sched_filter(s, e, locations, sched_raw)

        # Sales WHERE scoped to sa alias for JOIN CTE
        join_where = build_join_where(where)

        appt_loc = "AND center_name IN UNNEST(@locations)" if locations else ""

        all_params = merge_params(params, [y_param, lm_start_p, lm_end_p], sched_x)

        sql = f"""
        WITH mtd AS (
            SELECT
                SUM(sales_exc_tax)                                                                  AS mtd_revenue,
                SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))        AS avg_daily_revenue,
                COUNT(DISTINCT guest_id)                                                            AS total_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                    AS new_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = false
                                     AND member = false       THEN guest_id END)                    AS existing_client_count,
                COUNT(DISTINCT CASE WHEN member = true        THEN guest_id END)                    AS member_count,
                COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END)          AS new_members,
                SAFE_DIVIDE(
                    COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END),
                    NULLIF(COUNT(DISTINCT guest_id), 0)
                ) * 100                                                                             AS membership_adoption_rate,
                -- Blended ASP: all clients, excl. memberships
                SAFE_DIVIDE(
                    SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                   AS blended_asp,
                -- ── NEW: ASP segmented by new vs existing client ──────────────
                SAFE_DIVIDE(
                    SUM(CASE WHEN first_visit = true
                              AND item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN first_visit = true
                                               AND item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                   AS asp_new_clients,
                SAFE_DIVIDE(
                    SUM(CASE WHEN first_visit = false
                              AND item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN first_visit = false
                                               AND item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                   AS asp_existing_clients
            FROM {FULL_SALES}
            {where}
        ),
        yesterday_data AS (
            SELECT
                COALESCE(SUM(sales_exc_tax), 0)       AS yesterday_revenue,
                COALESCE(COUNT(DISTINCT guest_id), 0) AS yesterday_clients
            FROM {FULL_SALES}
            WHERE DATE(sale_date) = @yesterday
            {y_loc}
        ),
        last_month_data AS (
            SELECT
                COALESCE(SUM(sales_exc_tax), 0)       AS last_month_revenue,
                COALESCE(COUNT(DISTINCT guest_id), 0) AS last_month_clients
            FROM {FULL_SALES}
            WHERE DATE(sale_date) BETWEEN @lm_start AND @lm_end
            {y_loc}
        ),
        prior_year AS (
            SELECT COALESCE(SUM(sales_exc_tax), 0) AS py_revenue
            FROM {FULL_SALES}
            {py_where}
        ),
        schedule_util AS (
            SELECT
                LOWER(job_name)                                                                     AS role,
                SAFE_DIVIDE(SUM(booked_hours), NULLIF(SUM(scheduled_hours), 0)) * 100              AS utilization_pct
            FROM {FULL_SCHEDULE}
            {sched_block}
            GROUP BY job_name
        ),
        provider_rev AS (
            SELECT
                SAFE_DIVIDE(
                    SUM(CASE WHEN es.job_name = 'Treatment Provider' THEN sa.sales_exc_tax ELSE 0 END),
                    NULLIF(SUM(CASE WHEN es.job_name = 'Treatment Provider' THEN es.booked_hours ELSE 0 END), 0)
                ) AS rev_per_provider_hr,
                SAFE_DIVIDE(
                    SUM(CASE WHEN es.job_name = 'Esthetician' THEN sa.sales_exc_tax ELSE 0 END),
                    NULLIF(SUM(CASE WHEN es.job_name = 'Esthetician' THEN es.booked_hours ELSE 0 END), 0)
                ) AS rev_per_esthetician_hr
            FROM {FULL_SALES} sa
            LEFT JOIN {FULL_SCHEDULE} es
              ON sa.serviced_by = es.employee_name
             AND DATE(sa.sale_date) = DATE(es.date)
             AND sa.center_name = es.center_name
            {join_where}
        ),
        rebooking AS (
            SELECT
                SAFE_DIVIDE(COUNTIF(rebooked = true), NULLIF(COUNT(*), 0)) * 100 AS rebooking_rate
            FROM {FULL_APPT}
            WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
              AND status = 'Closed'
              AND add_on = 'No'
              {appt_loc}
        )
        SELECT
            m.mtd_revenue,
            m.avg_daily_revenue,
            m.total_client_count,
            m.new_client_count,
            m.existing_client_count,
            m.member_count,
            m.new_members,
            m.membership_adoption_rate,
            m.blended_asp,
            m.asp_new_clients,
            m.asp_existing_clients,
            y.yesterday_revenue,
            y.yesterday_clients,
            lm.last_month_revenue,
            lm.last_month_clients,
            p.py_revenue,
            SAFE_DIVIDE(m.mtd_revenue - p.py_revenue, NULLIF(p.py_revenue, 0)) * 100 AS same_store_yoy,
            (SELECT utilization_pct FROM schedule_util WHERE role = 'treatment provider' LIMIT 1) AS provider_utilization,
            (SELECT utilization_pct FROM schedule_util WHERE role = 'esthetician'        LIMIT 1) AS esthetician_utilization,
            pv.rev_per_provider_hr    AS rev_per_provider,
            pv.rev_per_esthetician_hr AS rev_per_esthetician,
            ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                                            AS gross_margin_pct,
            1950000.0                                                                               AS monthly_budget,
            rb.rebooking_rate
        FROM mtd m
        CROSS JOIN yesterday_data  y
        CROSS JOIN last_month_data lm
        CROSS JOIN prior_year      p
        CROSS JOIN provider_rev    pv
        CROSS JOIN rebooking       rb
        """
        rows = run_query(sql, all_params)
        return rows[0] if rows else {}

    except Exception as exc:
        log_and_raise_from_request(exc, request)

@router.get("/api/mtd-summary")
def get_mtd_summary(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Per-location MTD revenue vs prior week / prior month / prior year + membership stats."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))

        end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
        start_dt = datetime.strptime(s, "%Y-%m-%d").date()

        # Prior-week window (same number of days, 7 days earlier)
        pw_end   = end_dt   - timedelta(weeks=1)
        pw_start = start_dt - timedelta(weeks=1)

        # Prior-month window (same elapsed days, one month back)
        pm_s_month = start_dt.month - 1 or 12
        pm_s_year  = start_dt.year - (1 if start_dt.month == 1 else 0)
        pm_e_month = end_dt.month   - 1 or 12
        pm_e_year  = end_dt.year   - (1 if end_dt.month   == 1 else 0)
        pm_start = date(pm_s_year, pm_s_month, min(start_dt.day, calendar.monthrange(pm_s_year, pm_s_month)[1]))
        pm_end   = date(pm_e_year, pm_e_month, min(end_dt.day,   calendar.monthrange(pm_e_year, pm_e_month)[1]))

        # Prior-year window
        try:
            py_start = start_dt.replace(year=start_dt.year - 1)
            py_end   = end_dt.replace(year=end_dt.year - 1)
        except ValueError:
            py_start = start_dt - timedelta(days=365)
            py_end   = end_dt   - timedelta(days=365)

        where, params = build_date_filter(s, e, locations)
        days_in_month = calendar.monthrange(end_dt.year, end_dt.month)[1]

        def _period_where(ns, ne, suffix):
            extra = [
                bigquery.ScalarQueryParameter(f"{suffix}_start", "DATE", str(ns)),
                bigquery.ScalarQueryParameter(f"{suffix}_end",   "DATE", str(ne)),
            ]
            clause = (
                f"WHERE DATE(sale_date) >= @{suffix}_start"
                f"  AND DATE(sale_date) <= @{suffix}_end"
            )
            if locations:
                clause += " AND center_name IN UNNEST(@locations)"
            return extra, clause

        pw_x, pw_where = _period_where(pw_start, pw_end, "pw")
        pm_x, pm_where = _period_where(pm_start, pm_end, "pm")
        py_x, py_where = _period_where(py_start, py_end, "py")

        all_params = merge_params(params, pw_x, pm_x, py_x)

        # Days elapsed so far this month (for pro-rated budget)
        days_elapsed = (end_dt - end_dt.replace(day=1)).days + 1

        sql = f"""
        WITH budget_lookup AS (
            SELECT location, monthly_budget FROM UNNEST([
                STRUCT('Bel Air, MD'      AS location, 167500.0 AS monthly_budget),
                STRUCT('Bridgewater, NJ'  AS location,  50000.0 AS monthly_budget),
                STRUCT('Denville, NJ'     AS location, 165000.0 AS monthly_budget),
                STRUCT('Frederick, MD'    AS location, 147500.0 AS monthly_budget),
                STRUCT('Hoboken, NJ'      AS location, 267500.0 AS monthly_budget),
                STRUCT('Jersey City, NJ'  AS location, 250000.0 AS monthly_budget),
                STRUCT('Lancaster, PA'    AS location,  50000.0 AS monthly_budget),
                STRUCT('Montclair, NJ'    AS location, 192500.0 AS monthly_budget),
                STRUCT('Old Bridge, NJ'   AS location,  97500.0 AS monthly_budget),
                STRUCT('Red Bank, NJ'     AS location, 160000.0 AS monthly_budget),
                STRUCT('Ridgewood, NJ'    AS location, 150000.0 AS monthly_budget),
                STRUCT('Short Hills, NJ'  AS location, 167500.0 AS monthly_budget),
                STRUCT('Tribeca, NY'      AS location,  50000.0 AS monthly_budget),
                STRUCT('Waldorf, MD'      AS location,  35000.0 AS monthly_budget)
            ])
        ),
        current_period AS (
            SELECT
                center_name,
                SUM(sales_exc_tax)                                                                  AS cash_sales,
                SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))        AS avg_daily_sales,
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END)        AS cash_sales_excl_mbr,
                SUM(CASE WHEN DATE(sale_date)
                             BETWEEN DATE_SUB(@end_date, INTERVAL 6 DAY) AND @end_date
                         THEN sales_exc_tax ELSE 0 END)                                             AS current_week_revenue,
                COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END)          AS new_members,
                COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN guest_id END)         AS non_members,
                COUNT(DISTINCT guest_id)                                                            AS total_guests
            FROM {FULL_SALES}
            {where}
            GROUP BY center_name
        ),
        prior_week  AS (
            SELECT center_name, SUM(sales_exc_tax) AS pw_revenue
            FROM {FULL_SALES} {pw_where} GROUP BY center_name
        ),
        prior_month AS (
            SELECT center_name, SUM(sales_exc_tax) AS pm_revenue
            FROM {FULL_SALES} {pm_where} GROUP BY center_name
        ),
        prior_year  AS (
            SELECT center_name, SUM(sales_exc_tax) AS py_revenue
            FROM {FULL_SALES} {py_where} GROUP BY center_name
        )
        SELECT
            c.center_name                                                               AS location,
            c.cash_sales,
            c.avg_daily_sales,
            c.avg_daily_sales * {days_in_month}                                         AS trending,
            b.monthly_budget,
            c.cash_sales - b.monthly_budget                                             AS surplus_shortfall,
            SAFE_DIVIDE(c.cash_sales, NULLIF(b.monthly_budget, 0)) * 100               AS pct_to_goal_mtd,
            SAFE_DIVIDE(c.avg_daily_sales * {days_in_month}, NULLIF(b.monthly_budget, 0)) * 100
                                                                                        AS pct_to_goal_total,
            c.cash_sales_excl_mbr,
            c.current_week_revenue,
            COALESCE(pw.pw_revenue, 0)                                                   AS prior_week_revenue,
            c.current_week_revenue - COALESCE(pw.pw_revenue, 0)                         AS prior_week_variance,
            SAFE_DIVIDE(
                c.current_week_revenue - COALESCE(pw.pw_revenue, 0),
                NULLIF(COALESCE(pw.pw_revenue, 0), 0)
            ) * 100                                                                      AS prior_week_variance_pct,
            COALESCE(pm.pm_revenue, 0)                                                   AS pm_revenue,
            c.cash_sales - COALESCE(pm.pm_revenue, 0)                                   AS pm_variance,
            SAFE_DIVIDE(
                c.cash_sales - COALESCE(pm.pm_revenue, 0),
                NULLIF(COALESCE(pm.pm_revenue, 0), 0)
            ) * 100                                                                      AS pm_variance_pct,
            COALESCE(py.py_revenue, 0)                                                   AS py_revenue,
            c.cash_sales - COALESCE(py.py_revenue, 0)                                   AS py_variance,
            SAFE_DIVIDE(
                c.cash_sales - COALESCE(py.py_revenue, 0),
                NULLIF(COALESCE(py.py_revenue, 0), 0)
            ) * 100                                                                      AS py_variance_pct,
            c.new_members,
            c.non_members,
            SAFE_DIVIDE(c.new_members, NULLIF(c.total_guests, 0)) * 100                 AS membership_adoption
        FROM current_period c
        LEFT JOIN budget_lookup b  ON c.center_name = b.location
        LEFT JOIN prior_week  pw ON c.center_name = pw.center_name
        LEFT JOIN prior_month pm ON c.center_name = pm.center_name
        LEFT JOIN prior_year  py ON c.center_name = py.center_name
        ORDER BY c.center_name
        """
        return run_query(sql, all_params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/mtd-sales-mix")
def get_mtd_sales_mix(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Revenue by service category for the MTD window."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = build_date_filter(s, e, locations)

        sql = f"""
        SELECT
            center_name AS location,
            {_MIX_COLS}
        FROM {FULL_SALES}
        {where}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)