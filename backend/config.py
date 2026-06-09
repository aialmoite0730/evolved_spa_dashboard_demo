import os
import json
import base64
import tempfile
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()


# ─── Credentials ──────────────────────────────────────────────────────────────
def _setup_credentials() -> None:
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
            print(f"✅ Credentials loaded from Base64 → {tmp.name}")
            return
        except Exception as exc:
            raise RuntimeError(f"Failed to decode BIGQUERY_CREDENTIALS_BASE64: {exc}") from exc

    if creds_path:
        if os.path.exists(creds_path):
            print(f"✅ Credentials loaded from file → {creds_path}")
            return
        raise FileNotFoundError(f"Credentials file not found: {creds_path}")

    raise EnvironmentError(
        "No Google Cloud credentials found. "
        "Set GOOGLE_APPLICATION_CREDENTIALS or BIGQUERY_CREDENTIALS_BASE64."
    )


_setup_credentials()


# ─── BigQuery client (singleton) ──────────────────────────────────────────────
BQ_CLIENT: bigquery.Client = bigquery.Client()


# ─── Table identifiers ────────────────────────────────────────────────────────
PROJECT_ID     = os.getenv("BIGQUERY_PROJECT_ID",       "your-project-id")
DATASET        = os.getenv("BIGQUERY_DATASET",          "your_dataset")
SALES_TABLE    = os.getenv("BIGQUERY_TABLE",            "sales_accrual")
SCHEDULE_TABLE = os.getenv("BIGQUERY_SCHEDULE_TABLE",   "employee_schedule")
APPT_TABLE     = os.getenv("BIGQUERY_APPT_TABLE",       "appointments")
ERROR_TABLE    = os.getenv("BIGQUERY_ERROR_TABLE",      "api_error_log")

# Fully-qualified backtick references for use directly in SQL f-strings
FULL_SALES    = f"`{PROJECT_ID}.{DATASET}.{SALES_TABLE}`"
FULL_SCHEDULE = f"`{PROJECT_ID}.{DATASET}.{SCHEDULE_TABLE}`"
FULL_APPT     = f"`{PROJECT_ID}.{DATASET}.{APPT_TABLE}`"
FULL_ERRORS   = f"`{PROJECT_ID}.{DATASET}.{ERROR_TABLE}`"
