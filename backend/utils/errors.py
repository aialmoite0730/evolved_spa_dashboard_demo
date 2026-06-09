"""
Error logging utility.

Every unhandled exception in a router is caught, logged to the BigQuery
error_log table (non-blocking — fire-and-forget in a thread), and re-raised
as a FastAPI HTTPException so the frontend gets a clean JSON error body.

Error log schema (auto-created if table doesn't exist):
  error_id       STRING   — UUID v4
  timestamp      TIMESTAMP
  endpoint       STRING   — e.g. "/api/daily-kpis"
  method         STRING   — HTTP method
  params         STRING   — JSON-encoded query params
  error_type     STRING   — exception class name
  error_message  STRING
  traceback      STRING   — full stack trace
  environment    STRING   — value of APP_ENV env var (default "production")
"""

import os
import json
import uuid
import traceback as tb
import threading
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request
from google.cloud import bigquery

from config import BQ_CLIENT, FULL_ERRORS, PROJECT_ID, DATASET, ERROR_TABLE

_ENV = os.getenv("APP_ENV", "production")

# ─── BigQuery schema for the error log table ─────────────────────────────────
_ERROR_SCHEMA = [
    bigquery.SchemaField("error_id",      "STRING",    mode="REQUIRED"),
    bigquery.SchemaField("timestamp",     "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("endpoint",      "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("method",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("params",        "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("error_type",    "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("error_message", "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("traceback",     "STRING",    mode="NULLABLE"),
    bigquery.SchemaField("environment",   "STRING",    mode="NULLABLE"),
]


def _ensure_error_table() -> None:
    """Create the error log table if it doesn't already exist."""
    dataset_ref = BQ_CLIENT.dataset(DATASET, project=PROJECT_ID)
    table_ref   = dataset_ref.table(ERROR_TABLE)
    try:
        BQ_CLIENT.get_table(table_ref)
    except Exception:
        table = bigquery.Table(table_ref, schema=_ERROR_SCHEMA)
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp",
        )
        try:
            BQ_CLIENT.create_table(table)
            print(f"✅ Created error log table: {FULL_ERRORS}")
        except Exception as create_exc:
            # Non-fatal: if we can't create the table, errors still raise to the client
            print(f"⚠️  Could not create error log table: {create_exc}")


# Run table check once at import time (fast — just a get_table call)
_ensure_error_table()


def _insert_error_row(row: dict) -> None:
    """Insert a single error row into BigQuery. Runs in a daemon thread."""
    try:
        errors = BQ_CLIENT.insert_rows_json(
            f"{PROJECT_ID}.{DATASET}.{ERROR_TABLE}",
            [row],
        )
        if errors:
            print(f"⚠️  BigQuery error log insert failed: {errors}")
    except Exception as exc:
        # Last-resort: print to stdout/stderr so cloud logging picks it up
        print(f"⚠️  Could not write to error log: {exc}")


def log_and_raise(
    exc:      Exception,
    endpoint: str,
    method:   str   = "GET",
    params:   Optional[dict] = None,
    status:   int   = 500,
) -> None:
    """
    1. Build a structured error record.
    2. Fire-and-forget insert to BigQuery (non-blocking).
    3. Raise FastAPI HTTPException with the error_id so the frontend can
       display it and ops can correlate with the BQ log.

    Usage in a router:
        except Exception as exc:
            log_and_raise(exc, endpoint="/api/daily-kpis", params={"date": date})
    """
    error_id = str(uuid.uuid4())
    now      = datetime.now(timezone.utc).isoformat()

    row = {
        "error_id":      error_id,
        "timestamp":     now,
        "endpoint":      endpoint,
        "method":        method,
        "params":        json.dumps(params or {}, default=str),
        "error_type":    type(exc).__name__,
        "error_message": str(exc),
        "traceback":     tb.format_exc(),
        "environment":   _ENV,
    }

    # Non-blocking — don't make the client wait for BQ insert
    thread = threading.Thread(target=_insert_error_row, args=(row,), daemon=True)
    thread.start()

    print(f"❌ [{error_id}] {type(exc).__name__} @ {endpoint}: {exc}")

    raise HTTPException(
        status_code=status,
        detail={
            "error":    type(exc).__name__,
            "message":  str(exc),
            "error_id": error_id,          # frontend shows this so ops can look it up
        },
    )


def log_and_raise_from_request(exc: Exception, request: Request, status: int = 500) -> None:
    """
    Convenience wrapper that extracts endpoint + method + params from a
    FastAPI Request object automatically.

    Usage in a router that has access to the Request:
        except Exception as exc:
            log_and_raise_from_request(exc, request)
    """
    params = dict(request.query_params)
    log_and_raise(
        exc=exc,
        endpoint=str(request.url.path),
        method=request.method,
        params=params,
        status=status,
    )
