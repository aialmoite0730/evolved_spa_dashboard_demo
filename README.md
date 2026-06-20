# Evolve Med Spa — Analytics Dashboard

## Architecture

```
BigQuery (5 tables)
  ├── sales_accrual        → Revenue, sales mix, KPIs, ASP, client counts
  ├── employee_schedule    → Utilization (booked_hours / scheduled_hours)
  ├── appointments         → No-shows, cancellations, rebooking rate
  ├── api_log              → Request logs (every endpoint call, duration, errors)
  └── ai_insights_log      → AI insight cache (keyed by tab + prompt hash)

EVOLVED_SPA_DASHBOARD_DEMO/
  ├── .env
  ├── backend/
  │   ├── .env
  │   ├── bigquery_service_account.json
  │   ├── config.py            → Credentials, BigQuery client singleton, table refs (SQL + streaming)
  │   ├── db.py                → run_query(), serialize_rows()
  │   ├── main.py              → Orchestrator only (app, CORS, middleware, router registration)
  │   ├── Procfile             → Production process definition
  │   ├── railway.json         → Railway deployment config
  │   ├── requirements.txt     → Python dependencies
  │   ├── routers/
  │   │   ├── appointments.py  → /api/appointments/*
  │   │   ├── charts.py        → /api/category-breakdown, /api/revenue-trend
  │   │   ├── daily.py         → /api/latest-date, /api/daily-kpis, /api/daily-sales-mix
  │   │   ├── employees.py     → /api/employee-utilization, /api/employee-rph, /api/employee-scorecard
  │   │   ├── insights.py      → /api/insights (AI generation + BigQuery cache)
  │   │   ├── locations.py     → /api/locations
  │   │   ├── mtd.py           → /api/mtd-kpi-header, /api/mtd-summary, /api/mtd-sales-mix
  │   │   └── operations.py    → /api/operations-summary, /api/monthly-trend
  │   └── utils/
  │       ├── errors.py        → Structured error handler → attaches error info to request.state
  │       ├── filters.py       → WHERE-clause builders (date, schedule, join alias, param merge)
  │       └── request_logs.py  → RequestLoggingMiddleware → writes every request to api_log
  └── frontend/
      ├── .env
      ├── package.json
      ├── package-lock.json
      ├── railway.json
      ├── .gitignore
      ├── public/
      │   └── index.html
      └── src/
          ├── App.js           → Layout, tab routing, top bar filters, dynamic offset hook
          ├── App.css          → Global styles, tile system, table styles, color tokens
          ├── index.js
          ├── index.css
          ├── hooks/
          │   └── useDashboard.js  → All API fetches, debounced filter state, AbortController
          ├── utils/
          │   ├── api.js           → Fetch wrapper with query string builder
          │   └── format.js        → Currency, number, pct formatters + CSS class helpers
          └── components/
              ├── AiInsights.jsx           → AI insight panel (prompt built client-side)
              ├── AppointmentsDashboard.jsx → Full appointments tab layout
              ├── CategoryBreakdown.jsx     → Donut chart — revenue by item_category
              ├── DailyKPITable.jsx         → Prior-day KPI table with totals row
              ├── EmployeeRphTable.jsx      → Rev/Hr daily pivot table with color tiers
              ├── EmployeeScorecard.jsx     → MTD leaderboard card grid with tier badges
              ├── EmployeeUtilTable.jsx     → Utilization daily pivot table with color tiers
              ├── FilterBar.jsx             → Location chip strip (below tab bar)
              ├── KpiHeader.jsx             → Two-row KPI tile strip (revenue + performance)
              ├── MonthlyTrendTable.jsx     → Monthly operational metrics table
              ├── MTDSummaryTable.jsx       → MTD performance summary table with WoW/PM/PY variance
              ├── OperationsTable.jsx       → Operations tab metrics table
              ├── RevenueTrendChart.jsx     → Area trend chart + grouped location bar chart
              ├── RoleToggle.jsx            → Shared segmented control (All / Providers / Estheticians)
              └── SalesMixTable.jsx         → Revenue by service category with % of total row
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
| Request logs                 | `api_log`                             | Auto-written by RequestLoggingMiddleware        |
| AI insight cache             | `ai_insights_log`                     | `sha256(tab + prompt)` cache key                |

---

## API Endpoints

| Endpoint                                     | Router file      | Powers                                        |
|----------------------------------------------|------------------|-----------------------------------------------|
| `GET /api/locations`                         | locations.py     | Location dropdown                             |
| `GET /api/latest-date`                       | daily.py         | Resolves most recent closed sales date        |
| `GET /api/daily-kpis`                        | daily.py         | Prior-day KPI table + bar chart               |
| `GET /api/daily-sales-mix`                   | daily.py         | Daily sales mix table                         |
| `GET /api/mtd-kpi-header`                    | mtd.py           | Top KPI tile strip (both rows)                |
| `GET /api/mtd-summary`                       | mtd.py           | MTD Performance Summary table                 |
| `GET /api/mtd-sales-mix`                     | mtd.py           | MTD Sales Mix table                           |
| `GET /api/operations-summary`                | operations.py    | Operations tab charts + table                 |
| `GET /api/monthly-trend`                     | operations.py    | Operations — Operational Metrics table        |
| `GET /api/employee-utilization`              | employees.py     | Ops — Utilization by Employee (daily pivot)   |
| `GET /api/employee-rph`                      | employees.py     | Ops — Rev/Hr by Employee (daily pivot)        |
| `GET /api/employee-scorecard`                | employees.py     | Employee Scorecard card grid                  |
| `GET /api/category-breakdown`                | charts.py        | Donut chart — sales mix by category           |
| `GET /api/revenue-trend`                     | charts.py        | Area chart — daily revenue trend              |
| `GET /api/appointments/summary`              | appointments.py  | Appointment KPI summary per location          |
| `GET /api/appointments/by-status`            | appointments.py  | Status breakdown donut chart                  |
| `GET /api/appointments/by-category`          | appointments.py  | Appointment count by service category         |
| `GET /api/appointments/by-provider`          | appointments.py  | Per-provider appointment metrics              |
| `GET /api/appointments/by-booking-source`    | appointments.py  | Booking source bar chart                      |
| `GET /api/appointments/cancellation-reasons` | appointments.py  | Cancellation reason breakdown                 |
| `GET /api/appointments/daily-trend`          | appointments.py  | Daily trend area/line chart                   |
| `GET /api/appointments/request-type`         | appointments.py  | Provider preference breakdown                 |
| `POST /api/insights`                         | insights.py      | AI insight generation with BigQuery cache     |
| `GET /health`                                | main.py          | Liveness probe                                |

### Query Parameters

| Param        | Applies to              | Description                        | Example                  |
|--------------|-------------------------|------------------------------------|--------------------------| 
| `start_date` | All MTD endpoints       | MTD start date (YYYY-MM-DD)        | `2026-06-01`             |
| `end_date`   | All MTD endpoints       | MTD end date (YYYY-MM-DD)          | `2026-06-04`             |
| `date`       | Daily endpoints only    | Target date (YYYY-MM-DD)           | `2026-06-04`             |
| `locations`  | All endpoints           | Repeatable location filter         | `?locations=Hoboken,+NJ` |

---

## Frontend Architecture

### State Management — `useDashboard.js`

The single source of truth for all dashboard data. Key behaviours:

- **Boot sequence:** On mount, `/api/latest-date` and `/api/locations` are fetched in parallel. `filters` stays `null` until both resolve, preventing any data fetch from firing with wrong dates.
- **Debounce:** Filter changes are debounced by 300 ms. Back-to-back updates (e.g. `startDate` + `endDate`) collapse into a single fetch.
- **Abort control:** Each fetch batch is tied to an `AbortController`. A new filter change cancels the in-flight batch before starting a fresh one.
- **20 parallel requests:** All endpoints are fetched in a single `Promise.all` per refresh cycle.

### Tab Structure — `App.js`

| Tab ID        | Label               | Key components rendered                                      |
|---------------|---------------------|--------------------------------------------------------------|
| `daily`       | Daily KPIs          | `LocationBarChart`, `CategoryBreakdown`, `DailyKPITable`, `SalesMixTable` |
| `mtd`         | MTD Performance     | `LocationBarChart`, `CategoryBreakdown`, `MTDSummaryTable`, `SalesMixTable` |
| `ops`         | Operations          | `LocationBarChart` (×2), `OperationsTable`, `EmployeeUtilTable`, `EmployeeRphTable` |
| `scorecard`   | Employee Scorecard  | `EmployeeScorecard`                                          |
| `appointments`| Appointments        | `AppointmentsDashboard`                                      |

`AiInsights` renders above all tab content regardless of active tab.

### Layout offset — `useTopOffset` hook

Dynamically measures the combined rendered height of `.topbar`, `.tiles`, and `.tabbar` to set the `marginTop` on `.content`. This prevents tab content from being obscured by the fixed header stack regardless of screen size or KPI tile wrap.

### Employee Performance Tiers

| Role              | High Performer            | Average                   | Needs Focus       |
|-------------------|---------------------------|---------------------------|-------------------|
| Treatment Provider| Util ≥ 75% AND Rev/Hr ≥ $550 | Util ≥ 60% AND Rev/Hr ≥ $450 | Below thresholds |
| Esthetician       | Util ≥ 75% AND Rev/Hr ≥ $175 | Util ≥ 60% AND Rev/Hr ≥ $125 | Below thresholds |

---

## Request Logging

Every API request is automatically logged to the `api_log` BigQuery table by `RequestLoggingMiddleware` (registered in `main.py`). Each row captures:

| Field           | Description                                      |
|-----------------|--------------------------------------------------|
| `request_id`    | UUID v4 — correlation ID for the request         |
| `timestamp`     | UTC time the request was received                |
| `endpoint`      | Request path e.g. `/api/daily-kpis`              |
| `method`        | HTTP method                                      |
| `params`        | JSON-encoded query parameters                    |
| `status_code`   | HTTP response status code                        |
| `duration_ms`   | Total request handling time in milliseconds      |
| `error_type`    | Exception class name (NULL if no error)          |
| `error_message` | Error message string (NULL if no error)          |
| `traceback`     | Full stack trace (NULL if no error)              |
| `environment`   | Value of `APP_ENV` env var                       |

The table is day-partitioned on `timestamp` and auto-created on startup if it doesn't exist. `/health` requests are excluded from logging.

To look up a failed request:
```sql
SELECT *
FROM `your_project.your_dataset.api_log`
WHERE request_id = '<id-from-the-UI>'
```

---

## Error Handling

Errors are handled at two layers:

**Backend** (`utils/errors.py`) — catches every unhandled exception in every router and:
1. Attaches structured error info (`error_type`, `error_message`, `traceback`) to `request.state`.
2. The `RequestLoggingMiddleware` folds this into the same `api_log` row — no separate error table insert, no extra latency.
3. Returns a structured JSON error body: `{ error, request_id }` so the frontend can surface the correlation ID.

**Frontend** (`useDashboard.js`) — catches HTTP/network failures and surfaces the error message in the UI error banner. `AbortError` is silently ignored (expected when a newer request cancels an in-flight one).

---

## AI Insights Cache

`POST /api/insights` caches every AI response in the `ai_insights_log` BigQuery table to avoid redundant API calls when the same tab and filters are requested again.

**How it works:**
1. A `sha256(tab + "|" + prompt)` cache key is generated from the request.
2. BigQuery is checked for an existing row within the TTL window (default 60 minutes).
3. On a **cache hit** — the saved insight is returned immediately, no AI call made.
4. On a **cache miss** — OpenAI (`gpt-4o-mini`) is called first, Gemini (`gemini-flash-latest`) as fallback. The result is saved to BigQuery asynchronously in a daemon thread.

The response includes a `"cached": true/false` flag and the `provider` that generated the insight (`"openai"` or `"gemini"`).

The table is day-partitioned on `created_at`, clustered on `cache_key`, and auto-created on startup if it doesn't exist.

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

Daily pivot columns (`d1`, `d2`, … `dN`) are renamed from `d_YYYYMMDD` format by the `_rename_pivot_cols()` helper in `employees.py` before the response is returned.

---

## Daily KPI Date Resolution

`/api/daily-kpis` and `/api/daily-sales-mix` apply an effective-date resolution step: if the requested date has no closed sales (future date, month boundary, or closed day), the query walks back up to 6 days to find the most recent date with data. This prevents empty tables when the dashboard loads on a non-business day.

`/api/latest-date` applies the same logic globally and is called once on app boot to seed the initial filter state.

---

## Filter Helpers — `utils/filters.py`

| Function              | Purpose                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `build_date_filter`   | Builds a `WHERE` clause for `sale_date` / `appointment_date` + location |
| `build_sched_filter`  | Builds a self-contained `WHERE` block for `employee_schedule` queries; renames date params to `sched_start` / `sched_end` to avoid collision with main query params |
| `build_join_where`    | Rewrites a sales `WHERE` clause to use the `sa.` alias for JOIN queries |
| `merge_params`        | Merges multiple BigQuery param lists, deduplicating by param name (first occurrence wins) |

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

| Variable                         | Required | Description                                               |
|----------------------------------|----------|-----------------------------------------------------------|
| `BIGQUERY_PROJECT_ID`            | ✅       | GCP project ID                                            |
| `BIGQUERY_DATASET`               | ✅       | BigQuery dataset name                                     |
| `BIGQUERY_TABLE`                 | ✅       | Sales accrual table name                                  |
| `BIGQUERY_SCHEDULE_TABLE`        | ✅       | Employee schedule table name                              |
| `BIGQUERY_APPT_TABLE`            | ✅       | Appointments table name                                   |
| `BIGQUERY_API_LOG_TABLE`         |          | Request log table name (default: `api_log`)               |
| `BIGQUERY_INSIGHTS_TABLE`        |          | AI insights cache table name (default: `ai_insights_log`) |
| `GOOGLE_APPLICATION_CREDENTIALS` |          | Path to service account JSON file                         |
| `BIGQUERY_CREDENTIALS_BASE64`    |          | Base64-encoded service account JSON (Railway-friendly)    |
| `OPENAI_API_KEY`                 |          | OpenAI API key (primary AI provider)                      |
| `GEMINI_API_KEY`                 |          | Gemini API key (fallback AI provider)                     |
| `AI_INSIGHTS_CACHE_TTL_MINUTES`  |          | Insight cache lifetime in minutes (default: `60`)         |
| `AI_INSIGHTS_DEBUG`              |          | Set to `0` to silence AI insights debug logging           |
| `APP_ENV`                        |          | Environment tag in logs (default: `production`)           |