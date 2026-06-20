"""
Combined request + error logging using BigQuery streaming inserts.

A single BigQuery table — api_log — holds one row per request. Most rows have
NULL error_type/error_message/traceback. When a router calls
log_and_raise_from_request() (utils/errors.py), the error details are stashed
on request.state and folded into that same row by the middleware below, so
request + error info never need to be joined across tables.

api_log schema (auto-created if missing):
  request_id    STRING    — UUID v4, generated at the start of the request
  timestamp     TIMESTAMP — when the request was received (UTC)
  endpoint      STRING    — request path, e.g. "/api/daily-kpis"
  method        STRING    — HTTP method
  params        STRING    — JSON-encoded query params
  status_code   INTEGER   — HTTP response status code
  duration_ms   FLOAT     — total request handling time in milliseconds
  error_type    STRING    — exception class name (NULL if no error)
  error_message STRING    — str(exception) (NULL if no error)
  traceback     STRING    — full stack trace (NULL if no error)
  environment   STRING    — value of APP_ENV env var (default "production")

Usage in main.py:
    from utils.request_logs import RequestLoggingMiddleware
    app.add_middleware(RequestLoggingMiddleware)
"""

import os
import json
import time
import uuid
import threading
from datetime import datetime, timezone

from google.cloud import bigquery
from config import BQ_CLIENT, PROJECT_ID, DATASET, API_LOG_TABLE, FULL_API_LOG, PLAIN_API_LOG
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_API_LOG_SCHEMA = [
    bigquery.SchemaField("request_id",    "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("timestamp",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("endpoint",      "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("method",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("params",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("status_code",   "INTEGER",   mode="NULLABLE"),
    bigquery.SchemaField("duration_ms",   "FLOAT",     mode="NULLABLE"),
    bigquery.SchemaField("error_type",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("error_message", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("traceback",     "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("environment",   "STRING",    mode="NULLABLE"),
]


def _ensure_api_log_table() -> None:
    """Create the api_log table in BigQuery if it doesn't already exist."""
    dataset_ref = BQ_CLIENT.dataset(DATASET, project=PROJECT_ID)
    table_ref   = dataset_ref.table(API_LOG_TABLE)
    try:
        BQ_CLIENT.get_table(table_ref)
    except Exception:
        table = bigquery.Table(table_ref, schema=_API_LOG_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp",
        )
        try:
            BQ_CLIENT.create_table(table)
            print(f"✅ Created api_log table: {FULL_API_LOG}")
        except Exception as create_exc:
            print(f"⚠️  Could not create api_log table: {create_exc}")


_ensure_api_log_table()


def insert_log_row(row: dict) -> None:
    """Write a single row to api_log via BigQuery streaming insert."""
    try:
        errors = BQ_CLIENT.insert_rows_json(PLAIN_API_LOG, [row])
        if errors:
            print(f"⚠️  api_log insert failed: {errors}")
    except Exception as exc:
        print(f"⚠️  Could not write to api_log: {exc}")


def insert_log_row_async(row: dict) -> None:
    """Fire-and-forget insert in a daemon thread."""
    threading.Thread(target=insert_log_row, args=(row,), daemon=True).start()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    SKIP_PATHS = {"/health"}

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        path = request.url.path
        if path not in self.SKIP_PATHS:
            error_info = getattr(request.state, "error_info", None) or {}
            row = {
                "request_id":    request_id,
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "endpoint":      path,
                "method":        request.method,
                "params":        json.dumps(dict(request.query_params), default=str),
                "status_code":   response.status_code,
                "duration_ms":   round(duration_ms, 2),
                "error_type":    error_info.get("error_type"),
                "error_message": error_info.get("error_message"),
                "traceback":     error_info.get("traceback"),
                "environment":   "production",
            }
            insert_log_row_async(row)

        return response
