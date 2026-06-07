import os
import json
import base64
import tempfile
import calendar
from datetime import date, datetime, timedelta
from typing import Optional, List
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from pydantic import BaseModel

load_dotenv()

# ─── Credentials ─────────────────────────────────────────────────────────────
def setup_credentials():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    creds_b64  = os.getenv("BIGQUERY_CREDENTIALS_BASE64")
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode("utf-8")
            creds_dict = json.loads(creds_json)
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            tmp.write(json.dumps(creds_dict))
            tmp.close()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
            print(f"✅ Credentials loaded from Base64: {tmp.name}")
            return
        except Exception as e:
            raise Exception(f"Failed to decode BIGQUERY_CREDENTIALS_BASE64: {e}")
    elif creds_path:
        if os.path.exists(creds_path):
            print(f"✅ Credentials loaded from file: {creds_path}")
            return
        raise FileNotFoundError(f"Credentials file not found at: {creds_path}")
    else:
        raise EnvironmentError(
            "No Google Cloud credentials found. "
            "Set GOOGLE_APPLICATION_CREDENTIALS or BIGQUERY_CREDENTIALS_BASE64."
        )

setup_credentials()

# ─── Config ──────────────────────────────────────────────────────────────────
PROJECT_ID      = os.getenv("BIGQUERY_PROJECT_ID", "your-project-id")
DATASET         = os.getenv("BIGQUERY_DATASET", "your_dataset")
SALES_TABLE     = os.getenv("BIGQUERY_TABLE", "sales_accrual")
SCHEDULE_TABLE  = os.getenv("BIGQUERY_SCHEDULE_TABLE", "employee_schedule")
APPT_TABLE      = os.getenv("BIGQUERY_APPT_TABLE", "appointments")

FULL_SALES    = f"`{PROJECT_ID}.{DATASET}.{SALES_TABLE}`"
FULL_SCHEDULE = f"`{PROJECT_ID}.{DATASET}.{SCHEDULE_TABLE}`"
FULL_APPT     = f"`{PROJECT_ID}.{DATASET}.{APPT_TABLE}`"

client = bigquery.Client()

app = FastAPI(title="Evolve Med Spa Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Helpers ─────────────────────────────────────────────────────────────────
def run_query(sql: str, params: list = None) -> list:
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    job = client.query(sql, job_config=job_config)
    rows = job.result()
    return [dict(row) for row in rows]


def build_date_filter(
    start: Optional[str],
    end: Optional[str],
    locations: Optional[List[str]],
    date_col: str = "sale_date",
    loc_col: str = "center_name",
) -> tuple[str, list]:
    """Build a WHERE clause + BigQuery param list for the given date column."""
    conditions = []
    params = []
    if start:
        conditions.append(f"DATE({date_col}) >= @start_date")
        params.append(bigquery.ScalarQueryParameter("start_date", "DATE", start))
    if end:
        conditions.append(f"DATE({date_col}) <= @end_date")
        params.append(bigquery.ScalarQueryParameter("end_date", "DATE", end))
    if locations:
        conditions.append(f"{loc_col} IN UNNEST(@locations)")
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


def build_sched_filter(
    s: str,
    e: str,
    locations: Optional[List[str]],
    sched_params_raw: list,
) -> tuple[str, list]:
    """
    Build a self-contained WHERE block for the employee_schedule table that
    includes the role/hours guard conditions, so callers never append a second
    WHERE clause after it.

    Returns (filter_block, extra_params_to_add_to_all_params).
    Date params are renamed sched_start / sched_end to avoid collisions.
    """
    conds = []
    extra = []

    if s:
        conds.append("DATE(date) >= @sched_start")
    if e:
        conds.append("DATE(date) <= @sched_end")
    if locations:
        # @locations is already in main params – reuse it, no extra param needed
        conds.append("center_name IN UNNEST(@locations)")

    # Always include role + hours guard
    conds.append("job_name IN ('Treatment Provider', 'Esthetician')")
    conds.append("scheduled_hours > 0")

    filter_block = "WHERE " + " AND ".join(conds)

    for p in sched_params_raw:
        if p.name == "start_date":
            extra.append(bigquery.ScalarQueryParameter("sched_start", "DATE", p.value))
        elif p.name == "end_date":
            extra.append(bigquery.ScalarQueryParameter("sched_end", "DATE", p.value))
        # skip "locations" – already in main params

    return filter_block, extra


def build_join_where(where: str) -> str:
    """
    Scope a sales WHERE clause to the 'sa' alias used in JOIN queries.
    Rewrites DATE(sale_date) → DATE(sa.sale_date) and center_name → sa.center_name.
    """
    if not where:
        return ""
    return (
        where
        .replace("DATE(sale_date)", "DATE(sa.sale_date)")
        .replace("center_name", "sa.center_name")
    )


def serialize_rows(rows: list) -> list:
    """Convert date/datetime objects to strings for JSON serialization."""
    for r in rows:
        for k, v in r.items():
            if isinstance(v, (date, datetime)):
                r[k] = str(v)
    return rows


# ─── /api/locations ──────────────────────────────────────────────────────────
@app.get("/api/locations")
def get_locations():
    sql = f"""
    SELECT DISTINCT center_name
    FROM {FULL_SALES}
    WHERE center_name IS NOT NULL
    ORDER BY center_name
    """
    rows = run_query(sql)
    return [r["center_name"] for r in rows]


# ─── /api/daily-kpis ─────────────────────────────────────────────────────────
# Pulls KPIs from the sales_accrual table for the requested date.
# No-shows & cancellations come from the appointments table.
#
# NOTE: In the appointments table, the `status` column holds values like
# 'Cancelled' and 'Closed'. The cancellation reason (e.g. 'Client Cancelled')
# lives in the `reason` column, not `status`. The filter below uses `status`
# only, which captures all cancellations regardless of who cancelled.
# Adjust if you need to distinguish client-initiated vs staff-initiated.
@app.get("/api/daily-kpis")
def get_daily_kpis(
    date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    target_date = date or str(datetime.utcnow().date())
    params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
    loc_filter = ""
    appt_loc_filter = ""
    if locations:
        loc_filter = "AND center_name IN UNNEST(@locations)"
        appt_loc_filter = "AND center_name IN UNNEST(@locations)"
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

    sql = f"""
    WITH sales AS (
        SELECT
            center_name                                                                        AS location,
            SUM(sales_exc_tax)                                                                 AS cash_sales,
            SUM(sales_inc_tax)                                                                 AS recognized_revenue,
            SUM(sales_exc_tax)                                                                 AS daily_need,
            SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END)       AS cash_sales_excl_mbr,
            SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT guest_id), 0))              AS asp,
            SAFE_DIVIDE(
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN invoice_id END), 0)
            )                                                                                  AS asp_excl_memberships,
            COUNT(DISTINCT invoice_id)                                                         AS appointment_count,
            SUM(CASE WHEN item_type = 'Service' THEN qty ELSE 0 END)                          AS service_count,
            SAFE_DIVIDE(
                SUM(CASE WHEN item_type = 'Service' THEN qty ELSE 0 END),
                NULLIF(COUNT(DISTINCT invoice_id), 0)
            )                                                                                  AS services_per_appt,
            COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                   AS new_client_count,
            COUNT(DISTINCT CASE WHEN first_visit = false AND member = false THEN guest_id END) AS existing_client_count,
            COUNT(DISTINCT guest_id)                                                           AS total_client_count,
            COUNT(DISTINCT CASE WHEN status = 'Closed' THEN invoice_id END)                   AS closed_invoice_count
        FROM {FULL_SALES}
        WHERE DATE(sale_date) = @target_date
        {loc_filter}
        GROUP BY center_name
    ),
    appts AS (
        SELECT
            center_name                                                                        AS location,
            COUNTIF(LOWER(status) = 'no show')                                                AS no_shows,
            -- status = 'Cancelled' covers all cancellations; reason distinguishes
            -- client-initiated ('Client Cancelled') vs other causes if needed.
            COUNTIF(LOWER(status) = 'cancelled')                                              AS cancellations
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) = @target_date
          AND add_on = 'No'
        {appt_loc_filter}
        GROUP BY center_name
    )
    SELECT
        s.*,
        COALESCE(a.no_shows, 0)      AS no_shows,
        COALESCE(a.cancellations, 0) AS cancellations
    FROM sales s
    LEFT JOIN appts a ON s.location = a.location
    ORDER BY s.location
    """
    return serialize_rows(run_query(sql, params))


# ─── /api/daily-sales-mix ────────────────────────────────────────────────────
@app.get("/api/daily-sales-mix")
def get_daily_sales_mix(
    date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    target_date = date or str(datetime.utcnow().date())
    params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
    loc_filter = ""
    if locations:
        loc_filter = "AND center_name IN UNNEST(@locations)"
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

    sql = f"""
    SELECT
        center_name                                                                            AS location,
        SUM(CASE WHEN item_category = 'Body Contouring'
                  OR item_sub_category = 'Body Contouring'     THEN sales_exc_tax ELSE 0 END) AS body_contouring,
        SUM(CASE WHEN item_category = 'Facials'                THEN sales_exc_tax ELSE 0 END) AS facials,
        SUM(CASE WHEN item_sub_category = 'Filler'             THEN sales_exc_tax ELSE 0 END) AS filler,
        SUM(CASE WHEN item_category = 'Laser Hair Removal'
                  OR item_sub_category = 'Laser Hair Removal'  THEN sales_exc_tax ELSE 0 END) AS laser_hair_removal,
        SUM(CASE WHEN item_category = 'Memberships'            THEN sales_exc_tax ELSE 0 END) AS memberships,
        SUM(CASE WHEN item_sub_category = 'Toxin'              THEN sales_exc_tax ELSE 0 END) AS neurotoxins,
        SUM(CASE WHEN
                item_category NOT IN ('Facials','Memberships','Injectables','Skin Rejuvenation','Retail','Laser Hair Removal','Body Contouring')
                AND item_sub_category NOT IN ('Body Contouring','Filler','Laser Hair Removal','Toxin','Other Injectables','PRF')
             THEN sales_exc_tax ELSE 0 END)                                                   AS other,
        SUM(CASE WHEN item_sub_category = 'Other Injectables'  THEN sales_exc_tax ELSE 0 END) AS other_injectables,
        SUM(CASE WHEN item_sub_category = 'PRF'                THEN sales_exc_tax ELSE 0 END) AS prf,
        SUM(CASE WHEN item_category = 'Retail'                 THEN sales_exc_tax ELSE 0 END) AS retail,
        SUM(CASE WHEN item_category = 'Skin Rejuvenation'      THEN sales_exc_tax ELSE 0 END) AS skin_rejuvenation,
        SUM(sales_exc_tax)                                                                     AS total
    FROM {FULL_SALES}
    WHERE DATE(sale_date) = @target_date
    {loc_filter}
    GROUP BY center_name
    ORDER BY center_name
    """
    return run_query(sql, params)


# ─── /api/mtd-kpi-header ─────────────────────────────────────────────────────
# Single-row KPI banner visible on every tab.
# Utilization sourced from employee_schedule (booked_hours / scheduled_hours).
@app.get("/api/mtd-kpi-header")
def get_mtd_kpi_header(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)

    yesterday = today - timedelta(days=1)
    y_param = bigquery.ScalarQueryParameter("yesterday", "DATE", str(yesterday))

    try:
        py_start = datetime.strptime(s, "%Y-%m-%d").date().replace(
            year=datetime.strptime(s, "%Y-%m-%d").date().year - 1)
        py_end   = datetime.strptime(e, "%Y-%m-%d").date().replace(
            year=datetime.strptime(e, "%Y-%m-%d").date().year - 1)
    except ValueError:
        py_start = datetime.strptime(s, "%Y-%m-%d").date() - timedelta(days=365)
        py_end   = datetime.strptime(e, "%Y-%m-%d").date() - timedelta(days=365)

    py_where_str = f"WHERE DATE(sale_date) >= '{py_start}' AND DATE(sale_date) <= '{py_end}'"
    y_loc_filter = ""
    if locations:
        py_where_str += " AND center_name IN UNNEST(@locations)"
        y_loc_filter  = "AND center_name IN UNNEST(@locations)"

    # FIX Bug 1 + Bug 2: build a single self-contained schedule filter block
    # that includes role/hours guards — no second WHERE appended in SQL.
    _, sched_params_raw = build_date_filter(s, e, locations, date_col="date", loc_col="center_name")
    sched_filter_block, sched_extra = build_sched_filter(s, e, locations, sched_params_raw)

    # FIX Bug 2: scope the sales WHERE to the 'sa' alias in the JOIN CTE.
    join_where = build_join_where(where)

    appt_loc = "AND center_name IN UNNEST(@locations)" if locations else ""

    seen = set(p.name for p in params)
    all_params = list(params) + [y_param]
    for p in sched_extra:
        if p.name not in seen:
            all_params.append(p)
            seen.add(p.name)

    sql = f"""
    WITH mtd AS (
        SELECT
            SUM(sales_exc_tax)                                                                  AS mtd_revenue,
            SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))        AS avg_daily_revenue,
            COUNT(DISTINCT guest_id)                                                            AS total_client_count,
            COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                    AS new_client_count,
            COUNT(DISTINCT CASE WHEN first_visit = false AND member = false THEN guest_id END) AS existing_client_count,
            -- member_count: guests who held a membership and transacted this period
            COUNT(DISTINCT CASE WHEN member = true THEN guest_id END)                          AS member_count,
            -- new_members: guests who purchased a membership product this period
            COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END)          AS new_members,
            SAFE_DIVIDE(
                COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END),
                NULLIF(COUNT(DISTINCT guest_id), 0)
            ) * 100                                                                             AS membership_adoption_rate,
            SAFE_DIVIDE(
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN invoice_id END), 0)
            )                                                                                   AS blended_asp
        FROM {FULL_SALES}
        {where}
    ),
    yesterday_data AS (
        SELECT
            SUM(sales_exc_tax)       AS yesterday_revenue,
            COUNT(DISTINCT guest_id) AS yesterday_clients
        FROM {FULL_SALES}
        WHERE DATE(sale_date) = @yesterday
        {y_loc_filter}
    ),
    prior_year AS (
        SELECT SUM(sales_exc_tax) AS py_revenue
        FROM {FULL_SALES}
        {py_where_str}
    ),
    -- Utilization from employee_schedule (booked_hours / scheduled_hours).
    -- FIX: sched_filter_block is a single WHERE that includes role + hours guards.
    schedule_util AS (
        SELECT
            LOWER(job_name) AS role,
            SAFE_DIVIDE(SUM(booked_hours), NULLIF(SUM(scheduled_hours), 0)) * 100 AS utilization_pct,
            SUM(booked_hours) AS total_booked_hours
        FROM {FULL_SCHEDULE}
        {sched_filter_block}
        GROUP BY job_name
    ),
    -- Revenue per utilized hour: sales joined to schedule on employee + center + date.
    -- FIX: join_where scopes DATE() and center_name to the 'sa' alias correctly.
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
        JOIN {FULL_SCHEDULE} es
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        {join_where}
    ),
    rebooking AS (
        SELECT
            SAFE_DIVIDE(
                COUNTIF(rebooked = true),
                NULLIF(COUNT(*), 0)
            ) * 100 AS rebooking_rate
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
        y.yesterday_revenue,
        y.yesterday_clients,
        p.py_revenue,
        SAFE_DIVIDE(m.mtd_revenue - p.py_revenue, NULLIF(p.py_revenue, 0)) * 100 AS same_store_yoy,
        (SELECT utilization_pct FROM schedule_util WHERE role = 'treatment provider' LIMIT 1) AS provider_utilization,
        (SELECT utilization_pct FROM schedule_util WHERE role = 'esthetician' LIMIT 1)        AS esthetician_utilization,
        pv.rev_per_provider_hr    AS rev_per_provider,
        pv.rev_per_esthetician_hr AS rev_per_esthetician,
        ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                                            AS gross_margin_pct,
        CAST(NULL AS NUMERIC)                                                                  AS monthly_budget,
        rb.rebooking_rate
    FROM mtd m
    CROSS JOIN yesterday_data y
    CROSS JOIN prior_year p
    CROSS JOIN provider_rev pv
    CROSS JOIN rebooking rb
    """
    rows = run_query(sql, all_params)
    return rows[0] if rows else {}


# ─── /api/mtd-summary ────────────────────────────────────────────────────────
@app.get("/api/mtd-summary")
def get_mtd_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))

    end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
    start_dt = datetime.strptime(s, "%Y-%m-%d").date()

    pw_end   = end_dt   - timedelta(weeks=1)
    pw_start = start_dt - timedelta(weeks=1)

    pm_start_year  = start_dt.year
    pm_start_month = start_dt.month - 1
    if pm_start_month == 0:
        pm_start_month = 12
        pm_start_year -= 1
    pm_end_year  = end_dt.year
    pm_end_month = end_dt.month - 1
    if pm_end_month == 0:
        pm_end_month = 12
        pm_end_year -= 1

    max_day  = calendar.monthrange(pm_start_year, pm_start_month)[1]
    pm_start = date(pm_start_year, pm_start_month, min(start_dt.day, max_day))
    pm_end   = date(pm_end_year,   pm_end_month,   min(end_dt.day,   max_day))

    try:
        py_start = start_dt.replace(year=start_dt.year - 1)
        py_end   = end_dt.replace(year=end_dt.year - 1)
    except ValueError:
        py_start = start_dt - timedelta(days=365)
        py_end   = end_dt   - timedelta(days=365)

    where, params = build_date_filter(s, e, locations)
    days_in_month = calendar.monthrange(end_dt.year, end_dt.month)[1]

    def make_cte_where(new_start, new_end, suffix):
        extra = [
            bigquery.ScalarQueryParameter(f"{suffix}_start", "DATE", str(new_start)),
            bigquery.ScalarQueryParameter(f"{suffix}_end",   "DATE", str(new_end)),
        ]
        clause = f"WHERE DATE(sale_date) >= @{suffix}_start AND DATE(sale_date) <= @{suffix}_end"
        if locations:
            clause += " AND center_name IN UNNEST(@locations)"
        return extra, clause

    pw_extra, pw_where = make_cte_where(pw_start, pw_end, "pw")
    pm_extra, pm_where = make_cte_where(pm_start, pm_end, "pm")
    py_extra, py_where = make_cte_where(py_start, py_end, "py")

    seen = set(p.name for p in params)
    all_params = list(params)
    for p in pw_extra + pm_extra + py_extra:
        if p.name not in seen:
            all_params.append(p)
            seen.add(p.name)

    sql = f"""
    WITH current_period AS (
        SELECT
            center_name,
            SUM(sales_exc_tax)                                                                AS cash_sales,
            SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))      AS avg_daily_sales,
            SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END)       AS cash_sales_excl_mbr,
            SUM(CASE WHEN DATE(sale_date) BETWEEN DATE_SUB(@end_date, INTERVAL 6 DAY) AND @end_date
                     THEN sales_exc_tax ELSE 0 END)                                            AS current_week_revenue,
            COUNT(DISTINCT CASE WHEN item_category = 'Memberships' THEN guest_id END)         AS new_members,
            COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN guest_id END)        AS non_members,
            COUNT(DISTINCT guest_id)                                                          AS total_guests
        FROM {FULL_SALES}
        {where}
        GROUP BY center_name
    ),
    prior_week AS (
        SELECT center_name, SUM(sales_exc_tax) AS pw_revenue
        FROM {FULL_SALES}
        {pw_where}
        GROUP BY center_name
    ),
    prior_month AS (
        SELECT center_name, SUM(sales_exc_tax) AS pm_revenue
        FROM {FULL_SALES}
        {pm_where}
        GROUP BY center_name
    ),
    prior_year AS (
        SELECT center_name, SUM(sales_exc_tax) AS py_revenue
        FROM {FULL_SALES}
        {py_where}
        GROUP BY center_name
    )
    SELECT
        c.center_name                                                              AS location,
        c.cash_sales,
        c.avg_daily_sales,
        c.avg_daily_sales * {days_in_month}                                        AS trending,
        CAST(NULL AS NUMERIC)                                                      AS monthly_budget,
        CAST(NULL AS NUMERIC)                                                      AS surplus_shortfall,
        CAST(NULL AS NUMERIC)                                                      AS pct_to_goal_mtd,
        CAST(NULL AS NUMERIC)                                                      AS pct_to_goal_total,
        c.cash_sales_excl_mbr,
        c.current_week_revenue,
        COALESCE(pw.pw_revenue, 0)                                                 AS prior_week_revenue,
        c.current_week_revenue - COALESCE(pw.pw_revenue, 0)                       AS prior_week_variance,
        SAFE_DIVIDE(
            c.current_week_revenue - COALESCE(pw.pw_revenue, 0),
            NULLIF(COALESCE(pw.pw_revenue, 0), 0)
        ) * 100                                                                    AS prior_week_variance_pct,
        COALESCE(pm.pm_revenue, 0)                                                 AS pm_revenue,
        c.cash_sales - COALESCE(pm.pm_revenue, 0)                                 AS pm_variance,
        SAFE_DIVIDE(
            c.cash_sales - COALESCE(pm.pm_revenue, 0),
            NULLIF(COALESCE(pm.pm_revenue, 0), 0)
        ) * 100                                                                    AS pm_variance_pct,
        COALESCE(py.py_revenue, 0)                                                 AS py_revenue,
        c.cash_sales - COALESCE(py.py_revenue, 0)                                 AS py_variance,
        SAFE_DIVIDE(
            c.cash_sales - COALESCE(py.py_revenue, 0),
            NULLIF(COALESCE(py.py_revenue, 0), 0)
        ) * 100                                                                    AS py_variance_pct,
        c.new_members,
        c.non_members,
        SAFE_DIVIDE(c.new_members, NULLIF(c.total_guests, 0)) * 100               AS membership_adoption
    FROM current_period c
    LEFT JOIN prior_week  pw ON c.center_name = pw.center_name
    LEFT JOIN prior_month pm ON c.center_name = pm.center_name
    LEFT JOIN prior_year  py ON c.center_name = py.center_name
    ORDER BY c.center_name
    """
    return run_query(sql, all_params)


# ─── /api/mtd-sales-mix ───────────────────────────────────────────────────────
@app.get("/api/mtd-sales-mix")
def get_mtd_sales_mix(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)

    sql = f"""
    SELECT
        center_name                                                                            AS location,
        SUM(CASE WHEN item_category = 'Body Contouring'
                  OR item_sub_category = 'Body Contouring'     THEN sales_exc_tax ELSE 0 END) AS body_contouring,
        SUM(CASE WHEN item_category = 'Facials'                THEN sales_exc_tax ELSE 0 END) AS facials,
        SUM(CASE WHEN item_sub_category = 'Filler'             THEN sales_exc_tax ELSE 0 END) AS filler,
        SUM(CASE WHEN item_category = 'Laser Hair Removal'
                  OR item_sub_category = 'Laser Hair Removal'  THEN sales_exc_tax ELSE 0 END) AS laser_hair_removal,
        SUM(CASE WHEN item_category = 'Memberships'            THEN sales_exc_tax ELSE 0 END) AS memberships,
        SUM(CASE WHEN item_sub_category = 'Toxin'              THEN sales_exc_tax ELSE 0 END) AS neurotoxins,
        SUM(CASE WHEN
                item_category NOT IN ('Facials','Memberships','Injectables','Skin Rejuvenation','Retail','Laser Hair Removal','Body Contouring')
                AND item_sub_category NOT IN ('Body Contouring','Filler','Laser Hair Removal','Toxin','Other Injectables','PRF')
             THEN sales_exc_tax ELSE 0 END)                                                   AS other,
        SUM(CASE WHEN item_sub_category = 'Other Injectables'  THEN sales_exc_tax ELSE 0 END) AS other_injectables,
        SUM(CASE WHEN item_sub_category = 'PRF'                THEN sales_exc_tax ELSE 0 END) AS prf,
        SUM(CASE WHEN item_category = 'Retail'                 THEN sales_exc_tax ELSE 0 END) AS retail,
        SUM(CASE WHEN item_category = 'Skin Rejuvenation'      THEN sales_exc_tax ELSE 0 END) AS skin_rejuvenation,
        SUM(sales_exc_tax)                                                                     AS total
    FROM {FULL_SALES}
    {where}
    GROUP BY center_name
    ORDER BY center_name
    """
    return run_query(sql, params)


# ─── /api/operations-summary ─────────────────────────────────────────────────
# Per-location operational metrics. Utilization from schedule, rev/hr from join.
@app.get("/api/operations-summary")
def get_operations_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)

    end_dt_obj    = datetime.strptime(e, "%Y-%m-%d").date()
    days_in_month = calendar.monthrange(end_dt_obj.year, end_dt_obj.month)[1]

    # FIX Bug 1 + Bug 2: build a single self-contained schedule filter block.
    _, sched_params_raw = build_date_filter(s, e, locations, date_col="date", loc_col="center_name")
    sched_filter_block, sched_extra = build_sched_filter(s, e, locations, sched_params_raw)

    # FIX Bug 2: scope the sales WHERE to the 'sa' alias in JOIN CTEs.
    join_where = build_join_where(where)

    appt_loc = "AND center_name IN UNNEST(@locations)" if locations else ""

    seen = set(p.name for p in params)
    all_params = list(params)
    for p in sched_extra:
        if p.name not in seen:
            all_params.append(p)
            seen.add(p.name)

    sql = f"""
    WITH sales AS (
        SELECT
            center_name,
            SUM(sales_inc_tax)                                                                 AS recognized_revenue,
            SAFE_DIVIDE(SUM(sales_inc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))        AS avg_daily_revenue,
            SAFE_DIVIDE(SUM(sales_exc_tax), NULLIF(COUNT(DISTINCT guest_id), 0))               AS asp,
            SAFE_DIVIDE(
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN invoice_id END), 0)
            )                                                                                  AS asp_excl_memberships,
            COUNT(DISTINCT invoice_id)                                                         AS appointment_count,
            COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                   AS new_client_count,
            COUNT(DISTINCT CASE WHEN first_visit = false THEN guest_id END)                   AS existing_client_count
        FROM {FULL_SALES}
        {where}
        GROUP BY center_name
    ),
    -- FIX: sched_filter_block is one WHERE that includes role + hours guards.
    -- No second WHERE clause follows it.
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
            ) * 100 AS esthetician_utilization,
            SUM(CASE WHEN job_name = 'Treatment Provider' THEN booked_hours ELSE 0 END) AS prov_booked_hrs,
            SUM(CASE WHEN job_name = 'Esthetician'        THEN booked_hours ELSE 0 END) AS esti_booked_hrs
        FROM {FULL_SCHEDULE}
        {sched_filter_block}
        GROUP BY center_name
    ),
    -- FIX: join_where rewrites DATE(sale_date) → DATE(sa.sale_date) and
    -- center_name → sa.center_name so the alias is correct inside the JOIN.
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
        FROM {FULL_SALES} sa
        JOIN {FULL_SCHEDULE} es
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        {join_where}
        GROUP BY sa.center_name
    ),
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
        s.center_name                                                           AS location,
        s.recognized_revenue,
        s.avg_daily_revenue,
        s.avg_daily_revenue * {days_in_month}                                   AS trending,
        ROUND(20.0, 1)                                                          AS cogs_pct,
        ROUND(22.0 * 1.12, 1)                                                  AS payroll_pct,
        ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                             AS gross_margin_pct,
        s.asp,
        s.asp_excl_memberships,
        s.appointment_count,
        s.new_client_count,
        s.existing_client_count,
        COALESCE(r.rev_per_provider, NULL)    AS rev_per_provider,
        COALESCE(r.rev_per_esthetician, NULL) AS rev_per_esthetician,
        sch.provider_utilization,
        sch.esthetician_utilization,
        COALESCE(rb.rebooking_rate, NULL)     AS rebooking_rate,
        CAST(NULL AS INT64)                   AS review_count,
        CAST(NULL AS NUMERIC)                 AS avg_rating
    FROM sales s
    LEFT JOIN schedule_agg  sch ON s.center_name = sch.center_name
    LEFT JOIN rev_by_role   r   ON s.center_name = r.center_name
    LEFT JOIN rebooking     rb  ON s.center_name = rb.center_name
    ORDER BY s.center_name
    """
    return serialize_rows(run_query(sql, all_params))


# ─── /api/employee-utilization ───────────────────────────────────────────────
# Returns per-employee daily utilization % for the MTD period.
@app.get("/api/employee-utilization")
def get_employee_utilization(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))

    start_dt = datetime.strptime(s, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
    date_range = []
    d = start_dt
    while d <= end_dt:
        date_range.append(d)
        d += timedelta(days=1)

    pivot_cols = ",\n        ".join([
        f"SAFE_DIVIDE(SUM(CASE WHEN DATE(date) = '{day}' THEN booked_hours ELSE 0 END), "
        f"NULLIF(SUM(CASE WHEN DATE(date) = '{day}' THEN scheduled_hours ELSE 0 END), 0)) * 100 AS d_{day.strftime('%Y%m%d')}"
        for day in date_range
    ])

    loc_filter = ""
    params = []
    if locations:
        loc_filter = "AND center_name IN UNNEST(@locations)"
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

    sql = f"""
    SELECT
        center_name                                                                            AS center,
        job_name                                                                               AS role,
        employee_name                                                                          AS name,
        SAFE_DIVIDE(SUM(booked_hours), NULLIF(SUM(scheduled_hours), 0)) * 100                 AS tot,
        {pivot_cols}
    FROM {FULL_SCHEDULE}
    WHERE DATE(date) BETWEEN '{s}' AND '{e}'
      AND job_name IN ('Treatment Provider','Esthetician')
      AND scheduled_hours > 0
      {loc_filter}
    GROUP BY center_name, job_name, employee_name
    HAVING SUM(scheduled_hours) > 0
    ORDER BY job_name, center_name, employee_name
    """
    rows = run_query(sql, params)
    for r in rows:
        sorted_date_cols = sorted([k for k in r.keys() if k.startswith("d_")])
        for i, col in enumerate(sorted_date_cols, 1):
            r[f"d{i}"] = r.pop(col)
    return rows


# ─── /api/employee-rph ────────────────────────────────────────────────────────
# Revenue per utilized hour per employee per day.
@app.get("/api/employee-rph")
def get_employee_rph(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))

    start_dt = datetime.strptime(s, "%Y-%m-%d").date()
    end_dt   = datetime.strptime(e, "%Y-%m-%d").date()
    date_range = []
    d = start_dt
    while d <= end_dt:
        date_range.append(d)
        d += timedelta(days=1)

    pivot_cols = ",\n        ".join([
        f"SAFE_DIVIDE("
        f"SUM(CASE WHEN DATE(es.date) = '{day}' THEN sa.sales_exc_tax ELSE 0 END), "
        f"NULLIF(SUM(CASE WHEN DATE(es.date) = '{day}' THEN es.booked_hours ELSE 0 END), 0)"
        f") AS d_{day.strftime('%Y%m%d')}"
        for day in date_range
    ])

    loc_filter_sa = ""
    loc_filter_es = ""
    params = []
    if locations:
        loc_filter_sa = "AND sa.center_name IN UNNEST(@locations)"
        loc_filter_es = "AND es.center_name IN UNNEST(@locations)"
        params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

    sql = f"""
    SELECT
        es.center_name                                                                         AS center,
        es.job_name                                                                            AS role,
        es.employee_name                                                                       AS name,
        SAFE_DIVIDE(SUM(sa.sales_exc_tax), NULLIF(SUM(es.booked_hours), 0))                  AS tot,
        {pivot_cols}
    FROM {FULL_SCHEDULE} es
    JOIN {FULL_SALES} sa
      ON sa.serviced_by = es.employee_name
     AND DATE(sa.sale_date) = DATE(es.date)
     AND sa.center_name = es.center_name
    WHERE DATE(es.date) BETWEEN '{s}' AND '{e}'
      AND es.job_name IN ('Treatment Provider','Esthetician')
      AND es.booked_hours > 0
      {loc_filter_es}
      {loc_filter_sa}
    GROUP BY es.center_name, es.job_name, es.employee_name
    ORDER BY es.job_name, es.center_name, es.employee_name
    """
    rows = run_query(sql, params)
    for r in rows:
        sorted_date_cols = sorted([k for k in r.keys() if k.startswith("d_")])
        for i, col in enumerate(sorted_date_cols, 1):
            r[f"d{i}"] = r.pop(col)
    return rows


# ─── /api/employee-scorecard ─────────────────────────────────────────────────
# Combined scorecard: utilization + rph + total revenue per employee MTD.
@app.get("/api/employee-scorecard")
def get_employee_scorecard(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))

    loc_filter_sa = ""
    loc_filter_es = ""
    params = []
    if locations:
        loc_filter_sa = "AND sa.center_name IN UNNEST(@locations)"
        loc_filter_es = "AND es.center_name IN UNNEST(@locations)"
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
          AND job_name IN ('Treatment Provider','Esthetician')
          AND scheduled_hours > 0
          {loc_filter_es}
        GROUP BY center_name, job_name, employee_name
    ),
    rev AS (
        SELECT
            es.center_name,
            es.job_name,
            es.employee_name,
            SUM(sa.sales_exc_tax)  AS total_revenue
        FROM {FULL_SCHEDULE} es
        JOIN {FULL_SALES} sa
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        WHERE DATE(es.date) BETWEEN '{s}' AND '{e}'
          AND es.job_name IN ('Treatment Provider','Esthetician')
          AND es.booked_hours > 0
          {loc_filter_es}
          {loc_filter_sa}
        GROUP BY es.center_name, es.job_name, es.employee_name
    )
    SELECT
        s.center_name                                                                          AS center,
        s.job_name                                                                             AS role,
        s.employee_name                                                                        AS name,
        SAFE_DIVIDE(s.booked_hours, NULLIF(s.scheduled_hours, 0)) * 100                       AS utilization,
        SAFE_DIVIDE(COALESCE(r.total_revenue, 0), NULLIF(s.booked_hours, 0))                 AS rev_per_hr,
        COALESCE(r.total_revenue, 0)                                                          AS total_revenue,
        s.booked_hours,
        s.scheduled_hours
    FROM sched s
    LEFT JOIN rev r ON s.center_name = r.center_name
                    AND s.job_name = r.job_name
                    AND s.employee_name = r.employee_name
    ORDER BY s.job_name, COALESCE(r.total_revenue, 0) DESC
    """
    return run_query(sql, params)


# ─── /api/monthly-trend ────────────────────────────────────────────────────────
@app.get("/api/monthly-trend")
def get_monthly_trend(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)

    end_dt_obj    = datetime.strptime(e, "%Y-%m-%d").date()
    days_in_month = calendar.monthrange(end_dt_obj.year, end_dt_obj.month)[1]

    # FIX Bug 1 + Bug 2: build a single self-contained schedule filter block.
    _, sched_params_raw = build_date_filter(s, e, locations, date_col="date", loc_col="center_name")
    sched_filter_block, sched_extra = build_sched_filter(s, e, locations, sched_params_raw)

    # FIX Bug 2: scope the sales WHERE to the 'sa' alias in JOIN CTEs.
    join_where = build_join_where(where)

    appt_loc = "AND center_name IN UNNEST(@locations)" if locations else ""

    seen = set(p.name for p in params)
    all_params = list(params)
    for p in sched_extra:
        if p.name not in seen:
            all_params.append(p)
            seen.add(p.name)

    sql = f"""
    WITH sales AS (
        SELECT
            center_name,
            SUM(sales_inc_tax)                                                                 AS recognized_revenue,
            SAFE_DIVIDE(SUM(sales_inc_tax), NULLIF(COUNT(DISTINCT DATE(sale_date)), 0))        AS avg_daily_revenue,
            ROUND(SUM(sales_inc_tax) * 0.20, 2)                                                AS cogs_est,
            ROUND(SUM(sales_inc_tax) * 0.22 * 1.12, 2)                                        AS payroll_costs_est,
            ROUND(SUM(sales_inc_tax) * (1 - 0.20 - 0.22 * 1.12), 2)                          AS gross_margin,
            20.0                                                                               AS cogs_margin,
            ROUND(22.0 * 1.12, 1)                                                              AS payroll_margin,
            ROUND((1 - 0.20 - 0.22 * 1.12) * 100, 1)                                         AS gross_margin_pct,
            SAFE_DIVIDE(
                SUM(CASE WHEN item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships' THEN invoice_id END), 0)
            )                                                                                  AS asp_excl_memberships,
            COUNT(DISTINCT invoice_id)                                                         AS appointment_count,
            COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                   AS new_client_count,
            COUNT(DISTINCT CASE WHEN first_visit = false THEN guest_id END)                   AS existing_client_count,
            COUNT(DISTINCT guest_id)                                                           AS total_client_count
        FROM {FULL_SALES}
        {where}
        GROUP BY center_name
    ),
    -- FIX: sched_filter_block is one WHERE that includes role + hours guards.
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
        FROM {FULL_SCHEDULE}
        {sched_filter_block}
        GROUP BY center_name
    ),
    -- FIX: join_where rewrites DATE(sale_date) → DATE(sa.sale_date) and
    -- center_name → sa.center_name so aliases are correct inside the JOIN.
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
        FROM {FULL_SALES} sa
        JOIN {FULL_SCHEDULE} es
          ON sa.serviced_by = es.employee_name
         AND DATE(sa.sale_date) = DATE(es.date)
         AND sa.center_name = es.center_name
        {join_where}
        GROUP BY sa.center_name
    ),
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
        s.center_name                                                           AS location,
        s.recognized_revenue,
        s.avg_daily_revenue,
        s.avg_daily_revenue * {days_in_month}                                   AS trending,
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


# ─── /api/category-breakdown ─────────────────────────────────────────────────
@app.get("/api/category-breakdown")
def get_category_breakdown(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)
    cat_filter = "AND item_category IS NOT NULL" if where else "WHERE item_category IS NOT NULL"

    sql = f"""
    SELECT
        item_category,
        SUM(sales_exc_tax) AS revenue,
        COUNT(*)           AS count
    FROM {FULL_SALES}
    {where}
    {cat_filter}
    GROUP BY item_category
    ORDER BY revenue DESC
    """
    return run_query(sql, params)


# ─── /api/revenue-trend ──────────────────────────────────────────────────────
@app.get("/api/revenue-trend")
def get_revenue_trend(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    today = datetime.utcnow().date()
    e = end_date or str(today)
    s = start_date or str(today.replace(day=1))
    where, params = build_date_filter(s, e, locations)

    sql = f"""
    SELECT
        DATE(sale_date)            AS sale_date,
        SUM(sales_exc_tax)         AS daily_revenue,
        COUNT(DISTINCT invoice_id) AS appointments
    FROM {FULL_SALES}
    {where}
    GROUP BY DATE(sale_date)
    ORDER BY sale_date
    """
    return serialize_rows(run_query(sql, params))


@app.get("/health")
def health():
    return {"status": "ok"}