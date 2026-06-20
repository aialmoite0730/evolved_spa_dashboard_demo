from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Request

from config import FULL_SALES, FULL_CASH, FULL_APPT
from db import run_query, serialize_rows
from utils.filters import loc_in
from utils.errors import log_and_raise_from_request

router = APIRouter()


@router.get("/api/latest-date")
def get_latest_date(request: Request):
    """Returns the latest sale_date that has closed sales data."""
    try:
        sql = f"""
        SELECT MAX(CAST(sale_date AS DATE)) AS latest_date
        FROM {FULL_SALES}
        WHERE LOWER(status) = 'closed'
        """
        rows = run_query(sql)
        return {"latest_date": str(rows[0]["latest_date"]) if rows else None}
    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/latest-cash-date")
def get_latest_cash_date(request: Request):
    """Returns the latest payment_date in the cash collections table."""
    try:
        sql = f"""
        SELECT MAX(CAST(payment_date AS DATE)) AS latest_date
        FROM {FULL_CASH}
        """
        rows = run_query(sql)
        return {"latest_date": str(rows[0]["latest_date"]) if rows else None}
    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/daily-kpis")
def get_daily_kpis(
    request:   Request,
    date:      Optional[str]       = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    """
    Prior-day KPI table per location.

    Metric corrections applied:
    - cash_sales       : SUM(collected) WHERE status = 'Closed'
    - recognized_rev   : SUM(sales_inc_tax) WHERE status = 'Closed'
    - daily_need       : recognized_rev (placeholder until budgets connected)
    - asp              : SUM(sales_exc_tax) / COUNT(DISTINCT invoice_id)
    - no_shows         : appointments.status = 'No Show'
    - cancellations    : appointments.status = 'Cancelled'
    """
    try:
        target_date = date or str(datetime.utcnow().date())
        loc_and, loc_params = loc_in(locations)

        # ── Resolve effective date ────────────────────────────────────────────
        resolve_sql = f"""
        SELECT MAX(CAST(sale_date AS DATE)) AS last_date
        FROM {FULL_SALES}
        WHERE CAST(sale_date AS DATE) <= '{target_date}'
          AND CAST(sale_date AS DATE) >= DATEADD(DAY, -6, '{target_date}')
          AND LOWER(status) = 'closed'
          {loc_and}
        """
        resolved = run_query(resolve_sql, loc_params or None)
        effective_date = (
            str(resolved[0]["last_date"])
            if resolved and resolved[0].get("last_date")
            else target_date
        )

        sql = f"""
        WITH sales AS (
            SELECT
                center_name                                                                         AS location,
                SUM(CASE WHEN LOWER(status) = 'closed' THEN collected ELSE 0 END)                  AS cash_sales,
                SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_inc_tax ELSE 0 END)              AS recognized_revenue,
                SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_inc_tax ELSE 0 END)              AS daily_need,
                SUM(CASE WHEN LOWER(status) = 'closed' AND item_category != 'Memberships'
                         THEN collected ELSE 0 END)                                                 AS cash_sales_excl_mbr,
                SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_exc_tax ELSE 0 END)
                    * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_id END), 0)
                                                                                                    AS asp,
                SUM(CASE WHEN LOWER(status) = 'closed' AND item_category != 'Memberships'
                          THEN sales_exc_tax ELSE 0 END)
                    * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed'
                                                  AND item_category != 'Memberships'
                                                  THEN invoice_id END), 0)
                                                                                                    AS asp_excl_memberships,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_id END)             AS appointment_count,
                SUM(CASE WHEN item_type = 'Service'
                          AND LOWER(status) = 'closed' THEN qty ELSE 0 END)                        AS service_count,
                SUM(CASE WHEN item_type = 'Service' AND LOWER(status) = 'closed' THEN qty ELSE 0 END)
                    * 1.0
                    / NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_id END), 0)
                                                                                                    AS services_per_appt,
                COUNT(DISTINCT CASE WHEN LOWER(first_visit) = 'yes'
                                     AND LOWER(status) = 'closed' THEN guest_id END)               AS new_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(first_visit) = 'no'
                                     AND LOWER(member) = 'no'
                                     AND LOWER(status) = 'closed' THEN guest_id END)               AS existing_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN guest_id END)               AS total_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_id END)             AS closed_invoice_count
            FROM {FULL_SALES}
            WHERE CAST(sale_date AS DATE) = '{effective_date}'
            {loc_and}
            GROUP BY center_name
        ),
        appts AS (
            SELECT
                center_name                                                      AS location,
                SUM(CASE WHEN LOWER(status) = 'no show'   THEN 1 ELSE 0 END)   AS no_shows,
                SUM(CASE WHEN LOWER(status) = 'cancelled' THEN 1 ELSE 0 END)   AS cancellations
            FROM {FULL_APPT}
            WHERE CAST(appointment_date AS DATE) = '{effective_date}'
              AND add_on = 'No'
            {loc_and}
            GROUP BY center_name
        )
        SELECT
            s.*,
            COALESCE(a.no_shows,      0) AS no_shows,
            COALESCE(a.cancellations, 0) AS cancellations
        FROM sales s
        LEFT JOIN appts a ON s.location = a.location
        ORDER BY s.location
        """
        # loc_params appear twice (once for sales CTE, once for appts CTE)
        params = (loc_params + loc_params) if loc_params else None
        return serialize_rows(run_query(sql, params))

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/daily-sales-mix")
def get_daily_sales_mix(
    request:   Request,
    date:      Optional[str]       = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    """Revenue by service category for a single day."""
    try:
        target_date = date or str(datetime.utcnow().date())
        loc_and, loc_params = loc_in(locations)

        resolve_sql = f"""
        SELECT MAX(CAST(sale_date AS DATE)) AS last_date
        FROM {FULL_SALES}
        WHERE CAST(sale_date AS DATE) <= '{target_date}'
          AND CAST(sale_date AS DATE) >= DATEADD(DAY, -6, '{target_date}')
          AND LOWER(status) = 'closed'
          {loc_and}
        """
        resolved = run_query(resolve_sql, loc_params or None)
        effective_date = (
            str(resolved[0]["last_date"])
            if resolved and resolved[0].get("last_date")
            else target_date
        )

        sql = f"""
        SELECT
            center_name                                                                                        AS location,
            SUM(CASE WHEN (item_category = 'Body Contouring'
                      OR item_sub_category = 'Body Contouring') THEN sales_collected_exc_tax ELSE 0 END)       AS body_contouring,
            SUM(CASE WHEN item_category = 'Facials'             THEN sales_collected_exc_tax ELSE 0 END)       AS facials,
            SUM(CASE WHEN item_sub_category = 'Filler'          THEN sales_collected_exc_tax ELSE 0 END)       AS filler,
            SUM(CASE WHEN (item_category = 'Laser Hair Removal'
                      OR item_sub_category = 'Laser Hair Removal')
                                                                 THEN sales_collected_exc_tax ELSE 0 END)       AS laser_hair_removal,
            SUM(CASE WHEN item_category = 'Memberships'         THEN sales_collected_exc_tax ELSE 0 END)       AS memberships,
            SUM(CASE WHEN item_sub_category = 'Toxin'           THEN sales_collected_exc_tax ELSE 0 END)       AS neurotoxins,
            SUM(CASE WHEN item_category NOT IN (
                        'Facials','Memberships','Injectables','Skin Rejuvenation',
                        'Retail','Laser Hair Removal','Body Contouring')
                      AND item_sub_category NOT IN (
                        'Body Contouring','Filler','Laser Hair Removal',
                        'Toxin','Other Injectables','PRF')
                                                                 THEN sales_collected_exc_tax ELSE 0 END)       AS other,
            SUM(CASE WHEN item_sub_category = 'Other Injectables'
                                                                 THEN sales_collected_exc_tax ELSE 0 END)       AS other_injectables,
            SUM(CASE WHEN item_sub_category = 'PRF'             THEN sales_collected_exc_tax ELSE 0 END)       AS prf,
            SUM(CASE WHEN item_category = 'Retail'              THEN sales_collected_exc_tax ELSE 0 END)       AS retail,
            SUM(CASE WHEN item_category = 'Skin Rejuvenation'   THEN sales_collected_exc_tax ELSE 0 END)       AS skin_rejuvenation,
            SUM(sales_collected_exc_tax)                                                                        AS total
        FROM {FULL_CASH}
        WHERE CAST(payment_date AS DATE) = '{effective_date}'
        {loc_and}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)
