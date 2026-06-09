# Evolve Med Spa — Analytics Dashboard

## Architecture

```
BigQuery (3 tables)
  ├── sales_accrual        → Revenue, sales mix, KPIs, ASP, client counts
  ├── employee_schedule    → Utilization (booked_hours / scheduled_hours)
  └── appointments         → No-shows, cancellations, rebooking rate

FastAPI backend/
  ├── main.py              → Orchestrator only (app, CORS, router registration)
  ├── config.py            → Credentials, BigQuery client, table refs
  ├── db.py                → run_query(), serialize_rows()
  ├── utils/
  │   ├── filters.py       → WHERE-clause builders (date, schedule, join alias)
  │   └── errors.py        → Structured error logger → BigQuery api_error_log
  └── routers/
      ├── locations.py     → /api/locations
      ├── daily.py         → /api/daily-kpis, /api/daily-sales-mix
      ├── mtd.py           → /api/mtd-kpi-header, /api/mtd-summary, /api/mtd-sales-mix
      ├── operations.py    → /api/operations-summary, /api/monthly-trend
      ├── employees.py     → /api/employee-utilization, /api/employee-rph, /api/employee-scorecard
      └── charts.py        → /api/category-breakdown, /api/revenue-trend

React frontend/src/
  ├── App.js               → Layout, tab routing, top bar filters
  ├── hooks/useDashboard.js→ All API fetches, filter state
  ├── components/          → One file per table/chart/card
  └── utils/format.js      → Currency, number, pct formatters + CSS class helpers
```

---

## Data Source Mapping

| Dashboard metric             | Source table(s)                       | Join key                                        |
|------------------------------|---------------------------------------|-------------------------------------------------|
| Cash sales, ASP, sales mix   | `sales_accrual`                       | —                                               |
| No-shows / cancellations     | `appointments`                        | `center_name` + `appointment_date`              |
| Rebooking rate               | `appointments.rebooked`               | `center_name` + date range                      |
| Provider / Esti utilization  | `employee_schedule`                   | `booked_hours ÷ scheduled_hours`                |
| Revenue per utilized hour    | `sales_accrual` + `employee_schedule` | `serviced_by = employee_name`                   |
| Employee role (Provider/Esti)| `employee_schedule.job_name`          | —                                               |
| Employee name                | `sales_accrual.serviced_by`           | matched to `employee_schedule.employee_name`    |

---

## API Endpoints

| Endpoint                        | Router file      | Powers                                        |
|---------------------------------|------------------|-----------------------------------------------|
| `GET /api/locations`            | locations.py     | Location dropdown                             |
| `GET /api/daily-kpis`           | daily.py         | Prior-day KPI table + bar chart               |
| `GET /api/daily-sales-mix`      | daily.py         | Daily sales mix table                         |
| `GET /api/mtd-kpi-header`       | mtd.py           | Top KPI tile strip (both rows)                |
| `GET /api/mtd-summary`          | mtd.py           | MTD Performance Summary table                 |
| `GET /api/mtd-sales-mix`        | mtd.py           | MTD Sales Mix table                           |
| `GET /api/operations-summary`   | operations.py    | Operations tab charts + table                 |
| `GET /api/monthly-trend`        | operations.py    | Operations — Operational Metrics table        |
| `GET /api/employee-utilization` | employees.py     | Ops — Utilization by Employee (daily pivot)   |
| `GET /api/employee-rph`         | employees.py     | Ops — Rev/Hr by Employee (daily pivot)        |
| `GET /api/employee-scorecard`   | employees.py     | Employee Scorecard card grid                  |
| `GET /api/category-breakdown`   | charts.py        | Donut chart — sales mix by category           |
| `GET /api/revenue-trend`        | charts.py        | Area chart — daily revenue trend              |
| `GET /health`                   | main.py          | Liveness probe                                |

### Query Parameters

| Param        | Applies to              | Description                        | Example              |
|--------------|-------------------------|------------------------------------|----------------------|
| `start_date` | All MTD endpoints       | MTD start date (YYYY-MM-DD)        | `2026-06-01`         |
| `end_date`   | All MTD endpoints       | MTD end date (YYYY-MM-DD)          | `2026-06-04`         |
| `date`       | Daily endpoints only    | Target date (YYYY-MM-DD)           | `2026-06-04`         |
| `locations`  | All endpoints           | Repeatable location filter         | `?locations=Hoboken,+NJ` |

---

## Error Handling

Errors are handled at two layers:

**Backend** (`utils/errors.py`) — catches every unhandled exception in every router and:
1. Generates a UUID `error_id` for correlation.
2. Fire-and-forgets a background thread to insert the full record into BigQuery (`api_error_log` table) — non-blocking, client does not wait.
3. Returns a structured JSON error body: `{ error, message, error_id }`.

The `api_error_log` table is auto-created on first error if it doesn't exist (day-partitioned on `timestamp`).

To look up an error by ID:
```sql
SELECT *
FROM `your_project.your_dataset.api_error_log`
WHERE error_id = '<id-from-the-UI>'
```

**Frontend** (`useDashboard.js`) — catches HTTP/network failures and surfaces the error message in the UI error banner. The `error_id` is available in the response body for display to users so ops can correlate with the BQ log.

---

## Employee Data Design

Employee names and roles flow as follows:

1. `employee_schedule.employee_name` → who is scheduled; `job_name` → their role
2. `sales_accrual.serviced_by` → who delivered each service
3. JOIN: `employee_name = serviced_by AND DATE(date) = DATE(sale_date) AND center_name = center_name`

This join produces:
- **Utilization** = `SUM(booked_hours) / SUM(scheduled_hours)` per employee per day
- **Rev/Hr** = `SUM(sales_exc_tax) / SUM(booked_hours)` per employee per day

`job_name` values used: `Treatment Provider` and `Esthetician`.
Managers, Clinic Directors, and Concierge roles are excluded from all utilization and Rev/Hr metrics.

---

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in GCP project, dataset, and credentials
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

### Environment Variables (`.env`)

| Variable                       | Required | Description                                      |
|--------------------------------|----------|--------------------------------------------------|
| `BIGQUERY_PROJECT_ID`          | ✅       | GCP project ID                                   |
| `BIGQUERY_DATASET`             | ✅       | BigQuery dataset name                            |
| `BIGQUERY_TABLE`               | ✅       | Sales accrual table name                         |
| `BIGQUERY_SCHEDULE_TABLE`      | ✅       | Employee schedule table name                     |
| `BIGQUERY_APPT_TABLE`          | ✅       | Appointments table name                          |
| `BIGQUERY_ERROR_TABLE`         |          | Error log table name (default: `api_error_log`)  |
| `GOOGLE_APPLICATION_CREDENTIALS` |        | Path to service account JSON file                |
| `BIGQUERY_CREDENTIALS_BASE64`  |          | Base64-encoded service account JSON              |
| `APP_ENV`                      |          | Environment tag in error logs (default: `production`) |
