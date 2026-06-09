from datetime import date, datetime
from typing import Optional
from google.cloud import bigquery
from config import BQ_CLIENT


def run_query(sql: str, params: Optional[list] = None) -> list[dict]:
    """
    Execute a parameterised BigQuery SQL string and return rows as plain dicts.
    Raises on any BigQuery error — callers (routers) catch and log via errors.py.
    """
    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    job  = BQ_CLIENT.query(sql, job_config=job_config)
    rows = job.result()
    return [dict(row) for row in rows]


def serialize_rows(rows: list[dict]) -> list[dict]:
    """Convert date / datetime values to ISO strings so FastAPI can JSON-encode them."""
    for row in rows:
        for key, val in row.items():
            if isinstance(val, (date, datetime)):
                row[key] = str(val)
    return rows
