import os
import json
import base64
import tempfile
import threading
from dotenv import load_dotenv
from google.cloud import bigquery
import pymssql

load_dotenv()


# ─── SQL Server Connection (main data tables) ─────────────────────────────────
SQL_SERVER_HOST     = os.getenv("SQL_SERVER_HOST", "")
SQL_SERVER_PORT     = int(os.getenv("SQL_SERVER_PORT", "1433"))
SQL_SERVER_USER     = os.getenv("SQL_SERVER_USER", "")
SQL_SERVER_PASSWORD = os.getenv("SQL_SERVER_PASSWORD", "")
SQL_SERVER_DATABASE = os.getenv("SQL_SERVER_DATABASE", "evolve_spa")

_connection_lock = threading.Lock()
_connection_pool = []


def get_sql_connection():
    """Get a connection from the pool or create a new one."""
    global _connection_pool
    with _connection_lock:
        if _connection_pool:
            try:
                conn = _connection_pool.pop()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                return conn
            except Exception:
                pass

    try:
        conn = pymssql.connect(
            server=SQL_SERVER_HOST,
            port=SQL_SERVER_PORT,
            user=SQL_SERVER_USER,
            password=SQL_SERVER_PASSWORD,
            database=SQL_SERVER_DATABASE,
            timeout=10,
            charset='UTF-8'
        )
        print(f"[OK] Connected to SQL Server: {SQL_SERVER_HOST}:{SQL_SERVER_PORT}")
        return conn
    except pymssql.DatabaseError as exc:
        raise RuntimeError(f"Failed to connect to SQL Server: {exc}") from exc


def return_sql_connection(conn):
    """Return a connection to the pool."""
    global _connection_pool
    try:
        with _connection_lock:
            if len(_connection_pool) < 5:
                _connection_pool.append(conn)
            else:
                conn.close()
    except Exception:
        pass


# ─── BigQuery Credentials (api_log, insights, error tables only) ──────────────
def _setup_credentials() -> bool:
    """Returns True if credentials were found, False otherwise (non-fatal)."""
    creds_b64  = os.getenv("BIGQUERY_CREDENTIALS_BASE64")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode("utf-8")
            creds_dict = json.loads(creds_json)
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            tmp.write(json.dumps(creds_dict))
            tmp.close()
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
            print(f"[OK] BQ credentials loaded from Base64 -> {tmp.name}")
            return True
        except Exception as exc:
            print(f"[WARN] Failed to decode BIGQUERY_CREDENTIALS_BASE64: {exc}")
            return False

    if creds_path:
        if os.path.exists(creds_path):
            print(f"[OK] BQ credentials loaded from file -> {creds_path}")
            return True
        print(f"[WARN] BQ credentials file not found: {creds_path}")
        return False

    print("[WARN] No BQ credentials found - insights/api_log features will be unavailable.")
    return False


_BQ_AVAILABLE = _setup_credentials()
try:
    BQ_CLIENT: bigquery.Client = bigquery.Client() if _BQ_AVAILABLE else None
except Exception as _bq_exc:
    print(f"[WARN] Could not create BigQuery client: {_bq_exc}")
    BQ_CLIENT = None


# ─── SQL Server table identifiers ─────────────────────────────────────────────
SALES_TABLE    = os.getenv("SQL_SALES_TABLE",    "dbo.sales_accrual")
SCHEDULE_TABLE = os.getenv("SQL_SCHEDULE_TABLE", "dbo.employee_schedule")
APPT_TABLE     = os.getenv("SQL_APPT_TABLE",     "dbo.appointments")
CASH_TABLE     = os.getenv("SQL_CASH_TABLE",     "dbo.BRONZE_ZENOTI_CASH_COLLECTIONS")

# Aliases used by routers — plain table names work for SQL Server
FULL_SALES    = SALES_TABLE
FULL_SCHEDULE = SCHEDULE_TABLE
FULL_APPT     = APPT_TABLE
FULL_CASH     = CASH_TABLE


# ─── BigQuery table identifiers (api_log, insights, errors) ───────────────────
PROJECT_ID     = os.getenv("BIGQUERY_PROJECT_ID", "your-project-id")
DATASET        = os.getenv("BIGQUERY_DATASET",    "your_dataset")
API_LOG_TABLE  = os.getenv("BIGQUERY_API_LOG_TABLE",  "api_log")
INSIGHTS_TABLE = os.getenv("BIGQUERY_INSIGHTS_TABLE", "ai_insights_log")

# Backtick-quoted for BigQuery SQL queries
FULL_API_LOG   = f"`{PROJECT_ID}.{DATASET}.{API_LOG_TABLE}`"
FULL_INSIGHTS  = f"`{PROJECT_ID}.{DATASET}.{INSIGHTS_TABLE}`"

# Plain dotted for BigQuery streaming inserts (insert_rows_json)
PLAIN_API_LOG  = f"{PROJECT_ID}.{DATASET}.{API_LOG_TABLE}"
PLAIN_INSIGHTS = f"{PROJECT_ID}.{DATASET}.{INSIGHTS_TABLE}"