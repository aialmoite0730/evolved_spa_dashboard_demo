from datetime import date, datetime
from typing import Optional
import pymssql

from config import get_sql_connection, return_sql_connection


def run_query(sql: str, params: Optional[list] = None) -> list[dict]:
    """
    Execute a parameterised SQL Server query and return rows as plain dicts.
    Raises on any SQL Server error — callers (routers) catch and log via errors.py.
    """
    conn = get_sql_connection()
    try:
        cursor = conn.cursor(as_dict=True)
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return rows if rows else []
    except pymssql.DatabaseError as e:
        raise RuntimeError(f"SQL Server query error: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error executing query: {e}") from e
    finally:
        return_sql_connection(conn)


def serialize_rows(rows: list[dict]) -> list[dict]:
    """Convert date / datetime values to ISO strings so FastAPI can JSON-encode them."""
    for row in rows:
        for key, val in row.items():
            if isinstance(val, (date, datetime)):
                row[key] = str(val)
    return rows
