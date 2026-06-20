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

from config import FULL_APPT
from db import run_query, serialize_rows
from utils.filters import build_date_filter, loc_in, hhmm_to_hours, is_positive_duration
from utils.errors import log_and_raise_from_request

router = APIRouter()


def _appt_where(s: str, e: str, locations: Optional[List[str]]) -> tuple[str, list]:
    """Build WHERE for appointments table (appointment_date column)."""
    return build_date_filter(s, e, locations, date_col="appointment_date", loc_col="center_name")


@router.get("/api/appointments/summary")
def get_appointments_summary(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """KPI summary row per location."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = _appt_where(s, e, locations)

        sql = f"""
        SELECT
            center_name                                                                             AS location,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) != 'deleted' THEN 1 ELSE 0 END)          AS total_appointments,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'   THEN 1 ELSE 0 END)          AS completed,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'no show'  THEN 1 ELSE 0 END)          AS no_shows,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'cancelled' THEN 1 ELSE 0 END)         AS cancellations,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'deleted'  THEN 1 ELSE 0 END)          AS deleted,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'no show'  THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN add_on = 'No' AND LOWER(status) != 'deleted' THEN 1 ELSE 0 END), 0)
                * 100                                                                               AS no_show_rate,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'cancelled' THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN add_on = 'No' AND LOWER(status) != 'deleted' THEN 1 ELSE 0 END), 0)
                * 100                                                                               AS cancellation_rate,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed' AND LOWER(rebooked) = 'yes' THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed' THEN 1 ELSE 0 END), 0)
                * 100                                                                               AS rebooking_rate,
            SUM(CASE WHEN add_on = 'No' AND LOWER(first_visit) = 'yes' AND LOWER(status) = 'closed' THEN 1 ELSE 0 END)
                                                                                                    AS new_guests,
            COUNT(DISTINCT CASE WHEN add_on = 'No' AND LOWER(status) = 'closed' THEN guest_code END)
                                                                                                    AS unique_guests,
            AVG(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'
                      AND (service_name IS NULL OR LTRIM(RTRIM(service_name)) = '')
                      AND {is_positive_duration('actual_duration')}
                     THEN {hhmm_to_hours('actual_duration')} END)                                     AS avg_actual_duration,
            SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'
                      AND checkin_time IS NOT NULL AND checkin_time > start_time THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN add_on = 'No' AND LOWER(status) = 'closed'
                                   AND checkin_time IS NOT NULL THEN 1 ELSE 0 END), 0)
                * 100                                                                               AS late_checkin_rate
        FROM {FULL_APPT}
        {where}
        GROUP BY center_name
        ORDER BY center_name
        """
        return run_query(sql, params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/by-status")
def get_appointments_by_status(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Appointment counts by status across all locations."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        where, params = _appt_where(s, e, locations)
        and_kw = "AND" if where else "WHERE"

        sql = f"""
        SELECT status, COUNT(*) AS count
        FROM {FULL_APPT}
        {where}
        {and_kw} add_on = 'No'
          AND LOWER(status) != 'deleted'
        GROUP BY status
        ORDER BY count DESC
        """
        return run_query(sql, params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/by-category")
def get_appointments_by_category(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Appointment count and completion rate by service_category."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            COALESCE(service_category, 'Uncategorized')                                            AS category,
            COUNT(*)                                                                                AS total,
            SUM(CASE WHEN LOWER(status) = 'closed'    THEN 1 ELSE 0 END)                           AS completed,
            SUM(CASE WHEN LOWER(status) = 'no show'   THEN 1 ELSE 0 END)                           AS no_shows,
            SUM(CASE WHEN LOWER(status) = 'cancelled' THEN 1 ELSE 0 END)                           AS cancellations,
            SUM(CASE WHEN LOWER(status) = 'closed' THEN 1.0 ELSE 0 END)
                / NULLIF(COUNT(*), 0) * 100                                                         AS completion_rate
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          AND service_category IS NOT NULL
          {loc_and}
        GROUP BY service_category
        ORDER BY total DESC
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/by-provider")
def get_appointments_by_provider(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Per-provider appointment stats."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            center_name                                                                             AS location,
            providers                                                                               AS provider,
            COUNT(*)                                                                                AS total,
            SUM(CASE WHEN LOWER(status) = 'closed'    THEN 1 ELSE 0 END)                           AS completed,
            SUM(CASE WHEN LOWER(status) = 'no show'   THEN 1 ELSE 0 END)                           AS no_shows,
            SUM(CASE WHEN LOWER(status) = 'cancelled' THEN 1 ELSE 0 END)                           AS cancellations,
            SUM(CASE WHEN LOWER(status) = 'closed' AND LOWER(rebooked) = 'yes' THEN 1.0 ELSE 0 END)
                / NULLIF(SUM(CASE WHEN LOWER(status) = 'closed' THEN 1 ELSE 0 END), 0) * 100       AS rebooking_rate,
            AVG(CASE WHEN LOWER(status) = 'closed' AND {is_positive_duration('actual_duration')}
                     THEN {hhmm_to_hours('actual_duration')} END)                                     AS avg_actual_duration,
            AVG(CASE WHEN LOWER(status) = 'closed' AND {is_positive_duration('default_service_duration')}
                     THEN {hhmm_to_hours('default_service_duration')} END)                            AS avg_scheduled_duration
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          AND providers IS NOT NULL
          {loc_and}
        GROUP BY center_name, providers
        ORDER BY center_name, completed DESC
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/by-booking-source")
def get_appointments_by_booking_source(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Appointment count by booking_source."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT TOP 10
            COALESCE(booking_source, 'Unknown')                                                     AS booking_source,
            COUNT(*)                                                                                 AS total,
            SUM(CASE WHEN LOWER(status) = 'closed' THEN 1 ELSE 0 END)                              AS completed,
            SUM(CASE WHEN LOWER(status) = 'closed' THEN 1.0 ELSE 0 END)
                / NULLIF(COUNT(*), 0) * 100                                                         AS completion_rate
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY booking_source
        ORDER BY total DESC
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/cancellation-reasons")
def get_cancellation_reasons(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Cancellation breakdown by reason column."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            COALESCE(reason, 'Not Specified') AS reason,
            COUNT(*)                           AS count
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND LOWER(status) = 'cancelled'
          AND add_on = 'No'
          {loc_and}
        GROUP BY reason
        ORDER BY count DESC
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/daily-trend")
def get_appointments_daily_trend(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Daily trend of appointment counts by status."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            CAST(appointment_date AS DATE)                                      AS appointment_date,
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN LOWER(status) = 'closed'    THEN 1 ELSE 0 END)       AS completed,
            SUM(CASE WHEN LOWER(status) = 'no show'   THEN 1 ELSE 0 END)       AS no_shows,
            SUM(CASE WHEN LOWER(status) = 'cancelled' THEN 1 ELSE 0 END)       AS cancellations
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY CAST(appointment_date AS DATE)
        ORDER BY appointment_date
        """
        return serialize_rows(run_query(sql, loc_params or None))

    except Exception as exc:
        log_and_raise_from_request(exc, request)


@router.get("/api/appointments/request-type")
def get_appointments_by_request_type(
    request:    Request,
    start_date: Optional[str]       = Query(None),
    end_date:   Optional[str]       = Query(None),
    locations:  Optional[List[str]] = Query(None),
):
    """Breakdown by request_type."""
    try:
        today = datetime.utcnow().date()
        e = end_date   or str(today)
        s = start_date or str(today.replace(day=1))
        loc_and, loc_params = loc_in(locations)

        sql = f"""
        SELECT
            COALESCE(request_type, 'Not Specified')                                                 AS request_type,
            COUNT(*)                                                                                 AS total,
            SUM(CASE WHEN LOWER(status) = 'closed' THEN 1 ELSE 0 END)                              AS completed,
            SUM(CASE WHEN LOWER(status) = 'closed' THEN 1.0 ELSE 0 END)
                / NULLIF(COUNT(*), 0) * 100                                                         AS completion_rate
        FROM {FULL_APPT}
        WHERE CAST(appointment_date AS DATE) BETWEEN '{s}' AND '{e}'
          AND add_on = 'No'
          AND LOWER(status) != 'deleted'
          {loc_and}
        GROUP BY request_type
        ORDER BY total DESC
        """
        return run_query(sql, loc_params or None)

    except Exception as exc:
        log_and_raise_from_request(exc, request)
