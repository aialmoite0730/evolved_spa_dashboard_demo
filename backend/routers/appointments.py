"""
Appointments router.

All metrics sourced from the appointments table using the schema:
  appointment_date, center_name, status, add_on, rebooked,
  providers, service_category, service_subcategory, service_name,
  booking_source, gender, first_visit, request_type,
  scheduled_service_duration, actual_duration, checkin_time,
  start_time, reason, guest_code (for unique guest counts)
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Request
from google.cloud import bigquery

from config import FULL_APPT
from db import run_query, serialize_rows
from utils.filters import build_date_filter
from utils.errors import log_and_raise_from_request

router = APIRouter()

# ─── shared appointment filter helper ────────────────────────────────────────
def _appt_where(s: str, e: str, locations: Optional[List[str]]) -> tuple[str, list]:
    """Build WHERE for appointments table (appointment_date column)."""
    return build_date_filter(s, e, locations, date_col="appointment_date", loc_col="center_name")


# ─── /api/appointments/summary ───────────────────────────────────────────────
@router.get("/api/appointments/summary")
def get_appointments_summary(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    KPI summary row per location:
      - Total appointments (add_on = No, exclude Deleted)
      - Completed (Closed)
      - No-shows
      - Cancellations (status = Cancelled)
      - No-show rate, cancellation rate
      - Rebooking rate: COUNT(rebooked=true) / total closed
      - New guests (first_visit = true)
      - Avg scheduled duration
      - Avg actual duration
      - Late check-in rate (checkin_time > start_time)
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = _appt_where(s, e, locations)

        sql = f"""
        SELECT
            center_name                                                                             AS location,
            -- Volume
            COUNTIF(add_on = 'No' AND LOWER(status) != 'deleted')                                  AS total_appointments,
            COUNTIF(add_on = 'No' AND LOWER(status) = 'closed')                                    AS completed,
            COUNTIF(add_on = 'No' AND LOWER(status) = 'no show')                                   AS no_shows,
            COUNTIF(add_on = 'No' AND LOWER(status) = 'cancelled')                                 AS cancellations,
            COUNTIF(add_on = 'No' AND LOWER(status) = 'deleted')                                   AS deleted,
            -- Rates (% of total excl. deleted)
            SAFE_DIVIDE(
                COUNTIF(add_on = 'No' AND LOWER(status) = 'no show'),
                NULLIF(COUNTIF(add_on = 'No' AND LOWER(status) != 'deleted'), 0)
            ) * 100                                                                                 AS no_show_rate,
            SAFE_DIVIDE(
                COUNTIF(add_on = 'No' AND LOWER(status) = 'cancelled'),
                NULLIF(COUNTIF(add_on = 'No' AND LOWER(status) != 'deleted'), 0)
            ) * 100                                                                                 AS cancellation_rate,
            -- Rebooking: rebooked=true / total closed (non add-on)
            SAFE_DIVIDE(
                COUNTIF(add_on = 'No' AND LOWER(status) = 'closed' AND rebooked = true),
                NULLIF(COUNTIF(add_on = 'No' AND LOWER(status) = 'closed'), 0)
            ) * 100                                                                                 AS rebooking_rate,
            -- New guests
            COUNTIF(add_on = 'No' AND first_visit = true AND LOWER(status) = 'closed')             AS new_guests,
            COUNT(DISTINCT CASE WHEN add_on = 'No'
                                  AND LOWER(status) = 'closed' THEN guest_code END)                AS unique_guests,
            -- Duration
            AVG(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'
                      AND default_service_duration > 0
                     THEN default_service_duration END)                                             AS avg_scheduled_duration,
            AVG(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'
                      AND actual_duration > 0
                     THEN actual_duration END)                                                      AS avg_actual_duration,
            -- Late check-in: checkin_time is after start_time (both not null)
            SAFE_DIVIDE(
                COUNTIF(add_on = 'No' AND LOWER(status) = 'closed'
                        AND checkin_time IS NOT NULL
                        AND checkin_time > start_time),
                NULLIF(COUNTIF(add_on = 'No' AND LOWER(status) = 'closed'
                               AND checkin_time IS NOT NULL), 0)
            ) * 100                                                                                 AS late_checkin_rate
        FROM {FULL_APPT}
        {where}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/by-status ─────────────────────────────────────────────
@router.get("/api/appointments/by-status")
def get_appointments_by_status(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Appointment counts by status across all locations.
    Used for the status breakdown donut chart.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = _appt_where(s, e, locations)

        sql = f"""
        SELECT
            status,
            COUNT(*) AS count
        FROM {FULL_APPT}
        {where}
        {'AND' if where else 'WHERE'} add_on = 'No'
          AND LOWER(status) != 'deleted'
        GROUP BY status
        ORDER BY count DESC
        """
        # Fix WHERE/AND logic
        if where:
            sql = f"""
            SELECT status, COUNT(*) AS count
            FROM {FULL_APPT}
            {where}
            AND add_on = 'No'
            AND LOWER(status) != 'deleted'
            GROUP BY status
            ORDER BY count DESC
            """
        else:
            sql = f"""
            SELECT status, COUNT(*) AS count
            FROM {FULL_APPT}
            WHERE add_on = 'No'
              AND LOWER(status) != 'deleted'
            GROUP BY status
            ORDER BY count DESC
            """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/by-category ───────────────────────────────────────────
@router.get("/api/appointments/by-category")
def get_appointments_by_category(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Appointment count and completion rate by service_category.
    Used for category bar chart.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = _appt_where(s, e, locations)
        and_clause = "AND" if where else "WHERE"

        sql = f"""
        SELECT
            COALESCE(service_category, 'Uncategorized')                                            AS category,
            COUNT(*)                                                                                AS total,
            COUNTIF(LOWER(status) = 'closed')                                                      AS completed,
            COUNTIF(LOWER(status) = 'no show')                                                     AS no_shows,
            COUNTIF(LOWER(status) = 'cancelled')                                                   AS cancellations,
            SAFE_DIVIDE(COUNTIF(LOWER(status) = 'closed'), NULLIF(COUNT(*), 0)) * 100              AS completion_rate
        FROM {FULL_APPT}
        {where}
        {and_clause if where else 'WHERE'} add_on = 'No'
          AND LOWER(status) != 'deleted'
          AND service_category IS NOT NULL
        GROUP BY service_category
        ORDER BY total DESC
        """
        # Rebuild cleanly
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        sql = f"""
        SELECT
            COALESCE(service_category, 'Uncategorized')                                            AS category,
            COUNT(*)                                                                                AS total,
            COUNTIF(LOWER(status) = 'closed')                                                      AS completed,
            COUNTIF(LOWER(status) = 'no show')                                                     AS no_shows,
            COUNTIF(LOWER(status) = 'cancelled')                                                   AS cancellations,
            SAFE_DIVIDE(COUNTIF(LOWER(status) = 'closed'), NULLIF(COUNT(*), 0)) * 100              AS completion_rate
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          AND service_category IS NOT NULL
          {loc_and}
        GROUP BY service_category
        ORDER BY total DESC
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/by-provider ───────────────────────────────────────────
@router.get("/api/appointments/by-provider")
def get_appointments_by_provider(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Per-provider appointment stats: total, completed, no-show, cancel,
    rebooking rate, avg duration. Used for provider performance table.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        params  = []
        if locations:
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            center_name                                                                             AS location,
            providers                                                                               AS provider,
            COUNT(*)                                                                                AS total,
            COUNTIF(LOWER(status) = 'closed')                                                      AS completed,
            COUNTIF(LOWER(status) = 'no show')                                                     AS no_shows,
            COUNTIF(LOWER(status) = 'cancelled')                                                   AS cancellations,
            SAFE_DIVIDE(
                COUNTIF(LOWER(status) = 'closed' AND rebooked = true),
                NULLIF(COUNTIF(LOWER(status) = 'closed'), 0)
            ) * 100                                                                                 AS rebooking_rate,
            AVG(CASE WHEN LOWER(status) = 'closed'
                      AND actual_duration > 0 THEN actual_duration END)                            AS avg_actual_duration,
            AVG(CASE WHEN LOWER(status) = 'closed'
                      AND default_service_duration > 0
                     THEN default_service_duration END)                                             AS avg_scheduled_duration
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          AND providers IS NOT NULL
          {loc_and}
        GROUP BY center_name, providers
        ORDER BY center_name, completed DESC
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/by-booking-source ─────────────────────────────────────
@router.get("/api/appointments/by-booking-source")
def get_appointments_by_booking_source(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Appointment count by booking_source. Used for booking source bar chart.
    Shows how guests booked (Zenoti, Online, POS, etc.).
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        params  = []
        if locations:
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            COALESCE(booking_source, 'Unknown')                                                     AS booking_source,
            COUNT(*)                                                                                 AS total,
            COUNTIF(LOWER(status) = 'closed')                                                       AS completed,
            SAFE_DIVIDE(COUNTIF(LOWER(status) = 'closed'), NULLIF(COUNT(*), 0)) * 100               AS completion_rate
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY booking_source
        ORDER BY total DESC
        LIMIT 10
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/cancellation-reasons ──────────────────────────────────
@router.get("/api/appointments/cancellation-reasons")
def get_cancellation_reasons(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Cancellation breakdown by reason column.
    reason field distinguishes 'Client Cancelled', 'Staff Cancelled', etc.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        params  = []
        if locations:
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            COALESCE(reason, 'Not Specified')   AS reason,
            COUNT(*)                             AS count
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND LOWER(status) = 'cancelled'
          AND add_on = 'No'
          {loc_and}
        GROUP BY reason
        ORDER BY count DESC
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/daily-trend ───────────────────────────────────────────
@router.get("/api/appointments/daily-trend")
def get_appointments_daily_trend(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Daily trend of appointment counts by status.
    Powers the area/line chart on the Appointments tab.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        params  = []
        if locations:
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            appointment_date,
            COUNT(*)                             AS total,
            COUNTIF(LOWER(status) = 'closed')    AS completed,
            COUNTIF(LOWER(status) = 'no show')   AS no_shows,
            COUNTIF(LOWER(status) = 'cancelled') AS cancellations
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY appointment_date
        ORDER BY appointment_date
        """
        return serialize_rows(run_query(sql, params))

    except Exception as exc:
        log_and_raise_from_request(exc, request)


# ─── /api/appointments/request-type ──────────────────────────────────────────
@router.get("/api/appointments/request-type")
def get_appointments_by_request_type(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """
    Breakdown by request_type (Any, Specific provider requested, etc.).
    Shows provider preference behaviour.
    """
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and = "AND center_name IN UNNEST(@locations)" if locations else ""
        params  = []
        if locations:
            params.append(bigquery.ArrayQueryParameter("locations", "STRING", locations))

        sql = f"""
        SELECT
            COALESCE(request_type, 'Not Specified')                                                 AS request_type,
            COUNT(*)                                                                                 AS total,
            COUNTIF(LOWER(status) = 'closed')                                                       AS completed,
            SAFE_DIVIDE(COUNTIF(LOWER(status) = 'closed'), NULLIF(COUNT(*), 0)) * 100               AS completion_rate
        FROM {FULL_APPT}
        WHERE DATE(appointment_date) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY request_type
        ORDER BY total DESC
        """
        return run_query(sql, params)

    except Exception as exc:
        log_and_raise_from_request(exc, request)