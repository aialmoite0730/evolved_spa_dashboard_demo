from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Request
from google.cloud import bigquery

from config import FULL_SALES, FULL_APPT
from db import run_query, serialize_rows
from utils.errors import log_and_raise_from_request

router = APIRouter()


@router.get("/api/latest-date")
def get_latest_date(request: Request):
    """Returns the latest sale_date that has closed sales data."""
    try:
        sql = f"""
        SELECT MAX(DATE(sale_date)) AS latest_date
        FROM {FULL_SALES}
        WHERE LOWER(status) = 'closed'
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
                         (actual cash collected, not sales_exc_tax)
    - recognized_rev   : SUM(sales_inc_tax) WHERE status = 'Closed'
    - daily_need       : recognized_rev (placeholder until budgets connected)
    - asp              : SUM(sales_exc_tax) / COUNT(DISTINCT invoice_no)
    - no_shows         : appointments.status = 'No Show'
    - cancellations    : appointments.status = 'Cancelled'
                         reason column distinguishes client vs staff
    """
    try:
        target_date = date or str(datetime.utcnow().date())
        params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
        loc_filter = appt_loc_filter = ""

        if locations:
            loc_filter = appt_loc_filter = "AND center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        # ── Resolve effective date ────────────────────────────────────────────
        # If the requested date has no closed sales (e.g. end-of-month boundary,
        # future date, or a day the business was closed), walk back up to 6 days
        # to find the most recent day that actually has data.
        resolve_sql = f"""
        SELECT MAX(DATE(sale_date)) AS last_date
        FROM {FULL_SALES}
        WHERE DATE(sale_date) <= @target_date
          AND DATE(sale_date) >= DATE_SUB(@target_date, INTERVAL 6 DAY)
          AND LOWER(status) = 'closed'
          {loc_filter}
        """
        resolved = run_query(resolve_sql, params)
        if resolved and resolved[0].get("last_date"):
            effective_date = str(resolved[0]["last_date"])
        else:
            effective_date = target_date

        # Replace target_date param with resolved effective date
        params[0] = bigquery.ScalarQueryParameter("target_date", "DATE", effective_date)

        sql = f"""
        WITH sales AS (
            SELECT
                center_name                                                                         AS location,
                -- Cash Sales: actual collected amount on closed invoices
                SUM(CASE WHEN LOWER(status) = 'closed' THEN collected ELSE 0 END)                  AS cash_sales,
                -- Recognized Revenue: sales inc tax on closed invoices
                SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_inc_tax ELSE 0 END)              AS recognized_revenue,
                -- Daily Need: placeholder = recognized_revenue until budget table connected
                SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_inc_tax ELSE 0 END)              AS daily_need,
                -- Cash Sales excl. memberships
                SUM(CASE WHEN LOWER(status) = 'closed'
                          AND item_category != 'Memberships'
                         THEN collected ELSE 0 END)                                                 AS cash_sales_excl_mbr,
                -- ASP: sales_exc_tax / distinct invoices (per spec)
                SAFE_DIVIDE(
                    SUM(CASE WHEN LOWER(status) = 'closed' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_no END), 0)
                )                                                                                   AS asp,
                -- ASP excl. memberships
                SAFE_DIVIDE(
                    SUM(CASE WHEN LOWER(status) = 'closed'
                              AND item_category != 'Memberships' THEN sales_exc_tax ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed'
                                               AND item_category != 'Memberships'
                                               THEN invoice_no END), 0)
                )                                                                                   AS asp_excl_memberships,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_no END)             AS appointment_count,
                SUM(CASE WHEN item_type = 'Service'
                          AND LOWER(status) = 'closed' THEN qty ELSE 0 END)                        AS service_count,
                SAFE_DIVIDE(
                    SUM(CASE WHEN item_type = 'Service'
                              AND LOWER(status) = 'closed' THEN qty ELSE 0 END),
                    NULLIF(COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_no END), 0)
                )                                                                                   AS services_per_appt,
                COUNT(DISTINCT CASE WHEN first_visit = true
                                     AND LOWER(status) = 'closed' THEN guest_id END)               AS new_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = false
                                     AND member = false
                                     AND LOWER(status) = 'closed' THEN guest_id END)               AS existing_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN guest_id END)               AS total_client_count,
                COUNT(DISTINCT CASE WHEN LOWER(status) = 'closed' THEN invoice_no END)             AS closed_invoice_count
            FROM {FULL_SALES}
            WHERE DATE(sale_date) = @target_date
            {loc_filter}
            GROUP BY center_name
        ),
        appts AS (
            -- No-shows and cancellations from appointments table
            -- status = 'No Show' | 'Cancelled'
            -- reason distinguishes client vs staff initiated cancellations
            SELECT
                center_name                                          AS location,
                COUNTIF(LOWER(status) = 'no show')                  AS no_shows,
                COUNTIF(LOWER(status) = 'cancelled')                AS cancellations
            FROM {FULL_APPT}
            WHERE DATE(appointment_date) = @target_date
              AND add_on = 'No'
            {appt_loc_filter}
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
        return serialize_rows(run_query(sql, params))

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/daily-sales-mix")
def get_daily_sales_mix(
    request:   Request,
    date:      Optional[str]       = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    """
    Revenue by service category for a single day.
    Sales mix = sales by item_category / total sales (closed invoices only).
    """
    try:
        target_date = date or str(datetime.utcnow().date())
        params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
        loc_filter = ""

        if locations:
            loc_filter = "AND center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        # ── Resolve effective date (same logic as daily-kpis) ────────────────
        resolve_sql = f"""
        SELECT MAX(DATE(sale_date)) AS last_date
        FROM {FULL_SALES}
        WHERE DATE(sale_date) <= @target_date
          AND DATE(sale_date) >= DATE_SUB(@target_date, INTERVAL 6 DAY)
          AND LOWER(status) = 'closed'
          {loc_filter}
        """
        resolved = run_query(resolve_sql, params)
        if resolved and resolved[0].get("last_date"):
            effective_date = str(resolved[0]["last_date"])
        else:
            effective_date = target_date

        params[0] = bigquery.ScalarQueryParameter("target_date", "DATE", effective_date)

        sql = f"""
        SELECT
            center_name                                                                              AS location,
            SUM(CASE WHEN (item_category = 'Body Contouring'
                      OR item_sub_category = 'Body Contouring')
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS body_contouring,
            SUM(CASE WHEN item_category = 'Facials'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS facials,
            SUM(CASE WHEN item_sub_category = 'Filler'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS filler,
            SUM(CASE WHEN (item_category = 'Laser Hair Removal'
                      OR item_sub_category = 'Laser Hair Removal')
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS laser_hair_removal,
            SUM(CASE WHEN item_category = 'Memberships'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS memberships,
            SUM(CASE WHEN item_sub_category = 'Toxin'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS neurotoxins,
            SUM(CASE WHEN item_category NOT IN (
                        'Facials','Memberships','Injectables','Skin Rejuvenation',
                        'Retail','Laser Hair Removal','Body Contouring')
                      AND item_sub_category NOT IN (
                        'Body Contouring','Filler','Laser Hair Removal',
                        'Toxin','Other Injectables','PRF')
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS other,
            SUM(CASE WHEN item_sub_category = 'Other Injectables'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS other_injectables,
            SUM(CASE WHEN item_sub_category = 'PRF'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS prf,
            SUM(CASE WHEN item_category = 'Retail'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS retail,
            SUM(CASE WHEN item_category = 'Skin Rejuvenation'
                      AND LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS skin_rejuvenation,
            SUM(CASE WHEN LOWER(status) = 'closed'             THEN sales_exc_tax ELSE 0 END)       AS total
        FROM {FULL_SALES}
        WHERE DATE(sale_date) = @target_date
        {loc_filter}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)