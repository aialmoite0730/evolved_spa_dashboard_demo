from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Request
from google.cloud import bigquery

from config import FULL_SALES, FULL_APPT
from db import run_query, serialize_rows
from utils.errors import log_and_raise_from_request

router = APIRouter()


@router.get("/api/daily-kpis")
def get_daily_kpis(
    request:   Request,
    date:      Optional[str]       = Query(None),
    locations: Optional[List[str]] = Query(None),
):
    """
    Prior-day KPI table per location.
    Sales metrics from sales_accrual; no-shows + cancellations from appointments.

    NOTE: In appointments, `status` = 'Cancelled' for all cancellations.
    The `reason` column holds 'Client Cancelled', 'Staff Cancelled', etc.
    We count all cancellations here; adjust the COUNTIF if you need to split by reason.
    """
    try:
        target_date = date or str(datetime.utcnow().date())
        params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
        loc_filter = appt_loc_filter = ""

        if locations:
            loc_filter = appt_loc_filter = "AND center_name IN UNNEST(@locations)"
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
                    NULLIF(COUNT(DISTINCT CASE WHEN item_category != 'Memberships'
                                               THEN invoice_id END), 0)
                )                                                                                  AS asp_excl_memberships,
                COUNT(DISTINCT invoice_id)                                                         AS appointment_count,
                SUM(CASE WHEN item_type = 'Service' THEN qty ELSE 0 END)                          AS service_count,
                SAFE_DIVIDE(
                    SUM(CASE WHEN item_type = 'Service' THEN qty ELSE 0 END),
                    NULLIF(COUNT(DISTINCT invoice_id), 0)
                )                                                                                  AS services_per_appt,
                COUNT(DISTINCT CASE WHEN first_visit = true  THEN guest_id END)                   AS new_client_count,
                COUNT(DISTINCT CASE WHEN first_visit = false
                                     AND member = false       THEN guest_id END)                   AS existing_client_count,
                COUNT(DISTINCT guest_id)                                                           AS total_client_count,
                COUNT(DISTINCT CASE WHEN status = 'Closed'   THEN invoice_id END)                 AS closed_invoice_count
            FROM {FULL_SALES}
            WHERE DATE(sale_date) = @target_date
            {loc_filter}
            GROUP BY center_name
        ),
        appts AS (
            SELECT
                center_name                                      AS location,
                COUNTIF(LOWER(status) = 'no show')              AS no_shows,
                COUNTIF(LOWER(status) = 'cancelled')            AS cancellations
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
    """Revenue by service category for a single day."""
    try:
        target_date = date or str(datetime.utcnow().date())
        params = [bigquery.ScalarQueryParameter("target_date", "DATE", target_date)]
        loc_filter = ""

        if locations:
            loc_filter = "AND center_name IN UNNEST(@locations)"
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            center_name                                                                             AS location,
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
        FROM {FULL_SALES}
        WHERE DATE(sale_date) = @target_date
        {loc_filter}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)
