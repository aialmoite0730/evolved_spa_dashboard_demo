import calendar
from datetime import date, datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Query, Request

from config import FULL_SALES, FULL_CASH, FULL_SCHEDULE, FULL_APPT
from db import run_query, serialize_rows
from utils.filters import build_date_filter, build_sched_filter, merge_params, loc_in, hhmm_to_hours
from utils.errors import log_and_raise_from_request

router = APIRouter()

# Cash collections payment-type filter: restrict to recognized collection types.
#
# The payment_type column stores a comma-separated string of ALL payment methods
# used on a single invoice (e.g. " Card, Custom - Aspire, Gift Card(12345)").
# The FIRST value in the list determines whether the row should be counted —
# matching the UI filter which INCLUDES Cash, Card, Check, Custom-Financial,
# Custom-Non-Financial and EXCLUDES rows that start with:
#   Gift Cards, Prepaid Cards, Packages, Memberships, Loyalty Points, Cashback.
#
# NOTE: payment_type values have a leading space (e.g. " Card", " Gift Card(...)").
# LTRIM() is required so the LIKE patterns match correctly against the actual data.
# All valid rows start with: 'card', 'cash', 'check', or 'custom - *'.
# Excluded rows start with:  'gift card', 'prepaid card', 'package - ', 'membership - '.
_CASH_PAY_FILTER = (
    "AND LOWER(LTRIM(payment_type)) NOT LIKE 'gift card%'"
    " AND LOWER(LTRIM(payment_type)) NOT LIKE 'prepaid card%'"
    " AND LOWER(LTRIM(payment_type)) NOT LIKE 'package -%'"
    " AND LOWER(LTRIM(payment_type)) NOT LIKE 'membership -%'"
    " AND LOWER(LTRIM(payment_type)) NOT LIKE 'loyalty%'"
    " AND LOWER(LTRIM(payment_type)) NOT LIKE 'cashback%'"
)

# ── Shared sales-mix SELECT fragment ─────────────────────────────────────────
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

# Budget lookup as a SQL Server VALUES table
_BUDGET_VALUES = """(VALUES
    ('Bel Air, MD',      167500.0),
    ('Bridgewater, NJ',   50000.0),
    ('Denville, NJ',     165000.0),
    ('Frederick, MD',    147500.0),
    ('Hoboken, NJ',      267500.0),
    ('Jersey City, NJ',  250000.0),
    ('Lancaster, PA',     50000.0),
    ('Montclair, NJ',    192500.0),
    ('Old Bridge, NJ',    97500.0),
    ('Red Bank, NJ',     160000.0),
    ('Ridgewood, NJ',    150000.0),
    ('Short Hills, NJ',  167500.0),
    ('Tribeca, NY',       50000.0),
    ('Waldorf, MD',       35000.0)
) AS budget_lookup(location, monthly_budget)"""


@router.get("/api/mtd-kpi-header")
def get_mtd_kpi_header(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Single-row KPI banner shown on every tab."""
    try:
        if not end_date:
            r = run_query(f"SELECT MAX(CAST(payment_date AS DATE)) AS d FROM {FULL_CASH}")
            end_date = str(r[0]["d"]) if r and r[0].get("d") else str(datetime.utcnow().date())
        e = end_date
        e_dt_tmp = datetime.strptime(e, "%Y-%m-%d").date()
        s = start_date or str(e_dt_tmp.replace(day=1))

        where, params = build_date_filter(s, e, locations, date_col="payment_date")
        where_sales, params_sales = build_date_filter(s, e, locations, date_col="sale_date")
        e_dt      = datetime.strptime(e, "%Y-%m-%d").date()
        s_dt      = datetime.strptime(s, "%Y-%m-%d").date()
        yesterday = str(e_dt - timedelta(days=1))

        lm_end_dt   = e_dt.replace(day=1) - timedelta(days=1)
        lm_start_dt = lm_end_dt.replace(day=1)

        try:
            py_start = str(s_dt.replace(year=s_dt.year - 1))
            py_end   = str(e_dt.replace(year=e_dt.year - 1))
        except ValueError:
            py_start = str(s_dt - timedelta(days=365))
            py_end   = str(e_dt - timedelta(days=365))

        sched_block, sched_x = build_sched_filter(s, e, locations)
        appt_loc, appt_loc_p = loc_in(locations)
        y_loc,    y_loc_p    = loc_in(locations)

        sql = f"""
        WITH guest_classification AS (
            -- One row per guest_name: is_new=1 if ANY row in period has first_visit='yes'.
            -- Ensures new+existing always partitions total exactly (no double-count).
            SELECT
                guest_name,
                MAX(CASE WHEN LOWER(first_visit) = 'yes' THEN 1 ELSE 0 END) AS is_new
            FROM {FULL_CASH}
            {where}
            {_CASH_PAY_FILTER}
            GROUP BY guest_name
        ),
        mtd AS (
            SELECT
                SUM(c.sales_collected_exc_tax)                                                                AS mtd_revenue,
                SUM(c.sales_collected_exc_tax) * 1.0
                    / NULLIF(COUNT(DISTINCT CAST(c.payment_date AS DATE)), 0)                                 AS avg_daily_revenue,
                COUNT(DISTINCT CASE WHEN c.sales_collected_exc_tax > 0
                                     THEN CONCAT(c.guest_name, '|', CAST(c.payment_date AS DATE)) END)        AS total_customer_visits,
                COUNT(DISTINCT CASE WHEN gc.is_new = 1 THEN c.guest_name END)                                 AS new_client_count,
                COUNT(DISTINCT CASE WHEN gc.is_new = 0 THEN c.guest_name END)                                 AS existing_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(c.member) = 'yes'        THEN c.guest_name END)                AS member_count,
                COUNT(DISTINCT CASE WHEN c.item_category = 'Memberships' THEN c.guest_name END)               AS new_members,
                COUNT(DISTINCT CASE WHEN c.item_category = 'Memberships' THEN c.guest_name END) * 1.0
                    / NULLIF(COUNT(DISTINCT c.guest_name), 0) * 100                                            AS membership_adoption_rate,
                SUM(CASE WHEN c.item_category != 'Memberships' THEN c.sales_collected_exc_tax ELSE 0 END) * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN c.item_category != 'Memberships'
                                                  AND c.sales_collected_exc_tax > 0
                                                  THEN CONCAT(c.guest_name, '|', CAST(c.payment_date AS DATE)) END), 0)
                                                                                                              AS blended_asp,
                -- ASP = cash sales / visits (unique guest_name per day, invoice value > 0)
                SUM(CASE WHEN gc.is_new = 1 AND c.item_category != 'Memberships'
                          THEN c.sales_collected_exc_tax ELSE 0 END) * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN gc.is_new = 1 AND c.item_category != 'Memberships'
                                                  AND c.sales_collected_exc_tax > 0
                                                  THEN CONCAT(c.guest_name, '|', CAST(c.payment_date AS DATE)) END), 0)
                                                                                                              AS asp_new_clients,
                SUM(CASE WHEN gc.is_new = 0 AND c.item_category != 'Memberships'
                          THEN c.sales_collected_exc_tax ELSE 0 END) * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN gc.is_new = 0 AND c.item_category != 'Memberships'
                                                  AND c.sales_collected_exc_tax > 0
                                                  THEN CONCAT(c.guest_name, '|', CAST(c.payment_date AS DATE)) END), 0)
                                                                                                              AS asp_existing_clients
            FROM {FULL_CASH} c
            JOIN guest_classification gc ON gc.guest_name = c.guest_name
            {where}
            {_CASH_PAY_FILTER}
        ),
        yesterday_data AS (
            SELECT
                COALESCE(SUM(sales_collected_exc_tax), 0)       AS yesterday_revenue,
                COALESCE(COUNT(DISTINCT guest_name), 0)         AS yesterday_clients
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) = '{yesterday}'
            {y_loc}
            {_CASH_PAY_FILTER}
        ),
        last_month_data AS (
            SELECT
                COALESCE(SUM(sales_collected_exc_tax), 0)  AS last_month_revenue,
                COALESCE(COUNT(DISTINCT guest_name), 0)    AS last_month_clients
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) BETWEEN '{lm_start_dt}' AND '{lm_end_dt}'
            {y_loc}
            {_CASH_PAY_FILTER}
        ),
        prior_year AS (
            SELECT COALESCE(SUM(sales_collected_exc_tax), 0) AS py_revenue
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) >= '{py_start}'
              AND CAST(payment_date AS DATE) <= '{py_end}'
            {y_loc}
            {_CASH_PAY_FILTER}
        ),
        schedule_util AS (
            SELECT
                LOWER(job_name)                                                                     AS role,
                SUM({hhmm_to_hours('booked_hours')}) * 1.0
                    / NULLIF(SUM({hhmm_to_hours('scheduled_hours')}), 0) * 100                      AS utilization_pct
            FROM {FULL_SCHEDULE}
            {sched_block}
            GROUP BY job_name
        ),
        provider_rev AS (
            -- Pre-aggregate schedule and accrual sales to (center, employee, day) grain
            -- before joining to avoid fan-out multiplying booked_hours per sales row.
            SELECT
                SUM(CASE WHEN sch.job_name = 'Treatment Provider' THEN COALESCE(sa.daily_revenue, 0) ELSE 0 END) * 1.0
                    / NULLIF(SUM(CASE WHEN sch.job_name = 'Treatment Provider' THEN sch.booked_hours ELSE 0 END), 0)
                    AS rev_per_provider_hr,
                SUM(CASE WHEN sch.job_name = 'Esthetician' THEN COALESCE(sa.daily_revenue, 0) ELSE 0 END) * 1.0
                    / NULLIF(SUM(CASE WHEN sch.job_name = 'Esthetician' THEN sch.booked_hours ELSE 0 END), 0)
                    AS rev_per_esthetician_hr
            FROM (
                SELECT
                    center_name,
                    employee_name,
                    job_name,
                    CAST(date AS DATE)                   AS work_date,
                    SUM({hhmm_to_hours('booked_hours')}) AS booked_hours
                FROM {FULL_SCHEDULE}
                {sched_block}
                GROUP BY center_name, employee_name, job_name, CAST(date AS DATE)
            ) sch
            LEFT JOIN (
                SELECT
                    center_name,
                    serviced_by,
                    CAST(sale_date AS DATE) AS sale_date,
                    SUM(sales_exc_tax) AS daily_revenue
                FROM {FULL_SALES}
                {where_sales}
                GROUP BY center_name, serviced_by, CAST(sale_date AS DATE)
            ) sa
              ON sa.serviced_by  = sch.employee_name
             AND sa.sale_date    = sch.work_date
             AND sa.center_name  = sch.center_name
        ),
        rebooking AS (
            SELECT
                SUM(CASE WHEN LOWER(rebooked) = 'yes' THEN 1.0 ELSE 0 END)
                    / NULLIF(COUNT(*), 0) * 100 AS rebooking_rate
            FROM {FULL_APPT}
            WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
              AND LOWER(status) = 'closed'
              AND add_on = 'No'
              {appt_loc}
        )
        SELECT
            m.mtd_revenue,
            m.avg_daily_revenue,
            m.total_customer_visits,
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
            (m.mtd_revenue - p.py_revenue) * 1.0 / NULLIF(p.py_revenue, 0) * 100 AS same_store_yoy,
            (SELECT TOP 1 utilization_pct FROM schedule_util WHERE role = 'treatment provider') AS provider_utilization,
            (SELECT TOP 1 utilization_pct FROM schedule_util WHERE role = 'esthetician')        AS esthetician_utilization,
            pv.rev_per_provider_hr    AS rev_per_provider,
            pv.rev_per_esthetician_hr AS rev_per_esthetician,
            ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                                          AS gross_margin_pct,
            1950000.0                                                                             AS monthly_budget,
            rb.rebooking_rate
        FROM mtd m
        CROSS JOIN yesterday_data  y
        CROSS JOIN last_month_data lm
        CROSS JOIN prior_year      p
        CROSS JOIN provider_rev    pv
        CROSS JOIN rebooking       rb
        """
        # params order: guest_classification where, mtd where, yesterday_data y_loc,
        # last_month_data y_loc, prior_year y_loc, sched_block (provider_rev sch),
        # where_sales (provider_rev accrual sales), appt_loc
        all_params = merge_params(params, params, y_loc_p, y_loc_p, y_loc_p, sched_x, params_sales, appt_loc_p)
        rows = run_query(sql, all_params or None)
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
        if not end_date:
            r = run_query(f"SELECT MAX(CAST(payment_date AS DATE)) AS d FROM {FULL_CASH}")
            end_date = str(r[0]["d"]) if r and r[0].get("d") else str(datetime.utcnow().date())
        e = end_date
        e_dt_fix = datetime.strptime(e, "%Y-%m-%d").date()
        s = start_date or str(e_dt_fix.replace(day=1))

        end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
        start_dt = datetime.strptime(s, "%Y-%m-%d").date()

        pw_end   = str(end_dt   - timedelta(weeks=1))
        pw_start = str(start_dt - timedelta(weeks=1))

        pm_s_month = start_dt.month - 1 or 12
        pm_s_year  = start_dt.year - (1 if start_dt.month == 1 else 0)
        pm_e_month = end_dt.month   - 1 or 12
        pm_e_year  = end_dt.year   - (1 if end_dt.month   == 1 else 0)
        pm_start = str(date(pm_s_year, pm_s_month, min(start_dt.day, calendar.monthrange(pm_s_year, pm_s_month)[1])))
        pm_end   = str(date(pm_e_year, pm_e_month, min(end_dt.day,   calendar.monthrange(pm_e_year, pm_e_month)[1])))

        try:
            py_start = str(start_dt.replace(year=start_dt.year - 1))
            py_end   = str(end_dt.replace(year=end_dt.year - 1))
        except ValueError:
            py_start = str(start_dt - timedelta(days=365))
            py_end   = str(end_dt   - timedelta(days=365))

        where, params     = build_date_filter(s, e, locations, date_col="payment_date")
        days_in_month     = calendar.monthrange(end_dt.year, end_dt.month)[1]
        days_elapsed      = (end_dt - end_dt.replace(day=1)).days + 1
        loc_and, loc_p    = loc_in(locations)

        sql = f"""
        WITH budget_lookup AS (
            SELECT location, monthly_budget FROM {_BUDGET_VALUES}
        ),
        current_period AS (
            SELECT
                center_name,
                SUM(sales_collected_exc_tax)                                                                  AS cash_sales,
                SUM(sales_collected_exc_tax) * 1.0
                    / NULLIF(COUNT(DISTINCT CAST(payment_date AS DATE)), 0)                                   AS avg_daily_sales,
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_collected_exc_tax ELSE 0 END)        AS cash_sales_excl_mbr,
                SUM(CASE WHEN CAST(payment_date AS DATE)
                             BETWEEN DATEADD(DAY, -6, '{e}') AND '{e}'
                         THEN sales_collected_exc_tax ELSE 0 END)                                             AS current_week_revenue,
                COUNT(DISTINCT CASE WHEN item_category = 'Memberships'  THEN guest_code END)                  AS new_members,
                COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN guest_code END)                  AS non_members,
                COUNT(DISTINCT guest_code)                                                                     AS total_guests
            FROM {FULL_CASH}
            {where}
            GROUP BY center_name
        ),
        prior_week AS (
            SELECT center_name, SUM(sales_collected_exc_tax) AS pw_revenue
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) >= '{pw_start}'
              AND CAST(payment_date AS DATE) <= '{pw_end}'
            {loc_and}
            GROUP BY center_name
        ),
        prior_month AS (
            SELECT center_name, SUM(sales_collected_exc_tax) AS pm_revenue
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) >= '{pm_start}'
              AND CAST(payment_date AS DATE) <= '{pm_end}'
            {loc_and}
            GROUP BY center_name
        ),
        prior_year AS (
            SELECT center_name, SUM(sales_collected_exc_tax) AS py_revenue
            FROM {FULL_CASH}
            WHERE CAST(payment_date AS DATE) >= '{py_start}'
              AND CAST(payment_date AS DATE) <= '{py_end}'
            {loc_and}
            GROUP BY center_name
        )
        SELECT
            c.center_name                                                               AS location,
            c.cash_sales,
            c.avg_daily_sales,
            c.avg_daily_sales * {days_in_month}                                         AS trending,
            b.monthly_budget,
            c.cash_sales - b.monthly_budget                                             AS surplus_shortfall,
            c.cash_sales * 1.0 / NULLIF(b.monthly_budget, 0) * 100                    AS pct_to_goal_mtd,
            c.avg_daily_sales * {days_in_month} * 1.0 / NULLIF(b.monthly_budget, 0) * 100
                                                                                        AS pct_to_goal_total,
            c.cash_sales_excl_mbr,
            c.current_week_revenue,
            COALESCE(pw.pw_revenue, 0)                                                   AS prior_week_revenue,
            c.current_week_revenue - COALESCE(pw.pw_revenue, 0)                         AS prior_week_variance,
            (c.current_week_revenue - COALESCE(pw.pw_revenue, 0)) * 1.0
                / NULLIF(COALESCE(pw.pw_revenue, 0), 0) * 100                           AS prior_week_variance_pct,
            COALESCE(pm.pm_revenue, 0)                                                   AS pm_revenue,
            c.cash_sales - COALESCE(pm.pm_revenue, 0)                                   AS pm_variance,
            (c.cash_sales - COALESCE(pm.pm_revenue, 0)) * 1.0
                / NULLIF(COALESCE(pm.pm_revenue, 0), 0) * 100                           AS pm_variance_pct,
            COALESCE(py.py_revenue, 0)                                                   AS py_revenue,
            c.cash_sales - COALESCE(py.py_revenue, 0)                                   AS py_variance,
            (c.cash_sales - COALESCE(py.py_revenue, 0)) * 1.0
                / NULLIF(COALESCE(py.py_revenue, 0), 0) * 100                           AS py_variance_pct,
            c.new_members,
            c.non_members,
            c.new_members * 1.0 / NULLIF(c.total_guests, 0) * 100                      AS membership_adoption
        FROM current_period c
        LEFT JOIN budget_lookup b  ON c.center_name = b.location
        LEFT JOIN prior_week  pw ON c.center_name = pw.center_name
        LEFT JOIN prior_month pm ON c.center_name = pm.center_name
        LEFT JOIN prior_year  py ON c.center_name = py.center_name
        ORDER BY c.center_name
        """
        # params: current_period (where), prior_week (loc_p), prior_month (loc_p), prior_year (loc_p)
        all_params = merge_params(params, loc_p, loc_p, loc_p)
        return run_query(sql, all_params or None)

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
        return run_query(sql, params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/mtd-daily-trend")
def get_mtd_daily_trend(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Daily + cumulative cash sales, budget pace, and trending projection for the MTD chart."""
    try:
        if not end_date:
            r = run_query(f"SELECT MAX(CAST(payment_date AS DATE)) AS d FROM {FULL_CASH}")
            end_date = str(r[0]["d"]) if r and r[0].get("d") else str(datetime.utcnow().date())
        e     = end_date
        e_dt  = datetime.strptime(e, "%Y-%m-%d").date()
        s     = start_date or str(e_dt.replace(day=1))

        where, params    = build_date_filter(s, e, locations, date_col="payment_date")
        days_in_month    = calendar.monthrange(e_dt.year, e_dt.month)[1]
        days_elapsed     = (e_dt - e_dt.replace(day=1)).days + 1

        # ── Budget total for selected locations ──────────────────────────────
        if locations:
            bw_ph     = ",".join(["%s"] * len(locations))
            budget_sql = f"""
            WITH b AS (SELECT location, monthly_budget FROM {_BUDGET_VALUES})
            SELECT COALESCE(SUM(monthly_budget), 0) AS total_budget
            FROM b WHERE location IN ({bw_ph})
            """
            budget_rows = run_query(budget_sql, list(locations))
        else:
            budget_sql = f"""
            WITH b AS (SELECT location, monthly_budget FROM {_BUDGET_VALUES})
            SELECT COALESCE(SUM(monthly_budget), 0) AS total_budget FROM b
            """
            budget_rows = run_query(budget_sql)
        monthly_budget = float(budget_rows[0]["total_budget"]) if budget_rows else 0.0

        # ── Daily + cumulative cash sales ─────────────────────────────────────
        sql = f"""
        SELECT
            CAST(payment_date AS DATE)                                              AS day,
            SUM(sales_collected_exc_tax)                                            AS daily_sales,
            SUM(SUM(sales_collected_exc_tax)) OVER (
                ORDER BY CAST(payment_date AS DATE)
                ROWS UNBOUNDED PRECEDING
            )                                                                       AS cumulative_sales
        FROM {FULL_CASH}
        {where}
        GROUP BY CAST(payment_date AS DATE)
        ORDER BY day
        """
        daily_rows = run_query(sql, params or None)

        total_sales = float(daily_rows[-1]["cumulative_sales"]) if daily_rows else 0.0
        avg_daily   = total_sales / days_elapsed if days_elapsed else 0.0
        trending    = round(avg_daily * days_in_month, 2)

        return {
            "daily":          serialize_rows(daily_rows),
            "monthly_budget": monthly_budget,
            "trending":       trending,
            "days_in_month":  days_in_month,
        }

    except Exception as exc:
        log_and_raise_from_request(exc, request)