# Evolve Med Spa — Analytics Dashboard

## Architecture

```
SQL Server (evolve_spa database — main data)
  ├── BRONZE_ZENOTI_SALES_ACCRUAL        → Revenue, sales mix, KPIs, ASP, client counts
  ├── BRONZE_ZENOTI_EMPLOYEE_SCHEDULES   → Utilization (booked_hours / scheduled_hours)
  ├── BRONZE_ZENOTI_APPOINTMENTS         → No-shows, cancellations, rebooking rate
  └── BRONZE_ZENOTI_CASH_COLLECTIONS     → Cash collected (MTD KPIs, daily cash, avg daily)

BigQuery (observability only)
  ├── api_log              → Request logs (every endpoint call, duration, errors)
  └── ai_insights_log      → AI insight cache (keyed by tab + prompt hash)

EVOLVED_SPA_DASHBOARD_DEMO/
  ├── .env
  ├── backend/
  │   ├── .env
  │   ├── bigquery_service_account.json
  │   ├── config.py            → SQL Server connection pool + table refs; BigQuery client singleton
  │   ├── db.py                → run_query(), serialize_rows()
  │   ├── main.py              → Orchestrator only (app, CORS, middleware, router registration)
  │   ├── Procfile             → Production process definition
  │   ├── railway.json         → Railway deployment config
  │   ├── requirements.txt     → Python dependencies
  │   ├── routers/
  │   │   ├── appointments.py  → /api/appointments/*
  │   │   ├── charts.py        → /api/category-breakdown, /api/revenue-trend
  │   │   ├── daily.py         → /api/latest-date, /api/latest-cash-date, /api/daily-kpis, /api/daily-sales-mix
  │   │   ├── employees.py     → /api/employee-utilization, /api/employee-rph, /api/employee-scorecard
  │   │   ├── insights.py      → /api/insights (AI generation + BigQuery cache)
  │   │   ├── locations.py     → /api/locations
  │   │   ├── mtd.py           → /api/mtd-kpi-header, /api/mtd-summary, /api/mtd-sales-mix, /api/mtd-daily-trend
  │   │   └── operations.py    → /api/operations-summary, /api/monthly-trend
  │   └── utils/
  │       ├── errors.py        → Structured error handler → attaches error info to request.state
  │       ├── filters.py       → WHERE-clause builders (date, schedule, join alias, param merge)
  │       └── request_logs.py  → RequestLoggingMiddleware → writes every request to api_log (BigQuery)
  └── frontend/
      ├── .env
      ├── package.json
      ├── package-lock.json
      ├── railway.json
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

| Dashboard metric             | SQL Server table(s)                                    | Join key / filter                                       |
|------------------------------|--------------------------------------------------------|---------------------------------------------------------|
| Cash sales, avg daily, ASP   | `BRONZE_ZENOTI_CASH_COLLECTIONS`                       | `payment_date`, `center_name`                           |
| MTD KPIs (revenue, clients)  | `BRONZE_ZENOTI_CASH_COLLECTIONS`                       | `payment_date`, `center_name`                           |
| Sales mix (MTD)              | `BRONZE_ZENOTI_SALES_ACCRUAL`                          | `sale_date`, `item_category`, `item_sub_category`       |
| Daily KPIs (cash)            | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_APPOINTMENTS` | `sale_date` / `appointment_date`                |
| Revenue trend / category     | `BRONZE_ZENOTI_SALES_ACCRUAL`                          | `sale_date`, `item_category`                            |
| Operations / monthly trend   | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` | `center_name`, date range              |
| No-shows / cancellations     | `BRONZE_ZENOTI_APPOINTMENTS`                           | `center_name` + `appointment_date`                      |
| Rebooking rate               | `BRONZE_ZENOTI_APPOINTMENTS`                           | `rebooked = 'yes'` / `status = 'closed'`                |
| Provider / Esti utilization  | `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES`                     | `booked_hours ÷ scheduled_hours`                        |
| Revenue per utilized hour    | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` | `serviced_by = employee_name`, date + center |
| Employee role (Provider/Esti)| `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES.job_name`            | —                                                       |
| Locations list               | `BRONZE_ZENOTI_SALES_ACCRUAL`                          | `DISTINCT center_name`                                  |
| Request logs                 | BigQuery `api_log`                                     | Auto-written by `RequestLoggingMiddleware`              |
| AI insight cache             | BigQuery `ai_insights_log`                             | `sha256(tab + prompt)` cache key                        |

---

## API Endpoints

| Endpoint                                     | Router file      | SQL Server table(s)                                                                 | Powers                                        |
|----------------------------------------------|------------------|-------------------------------------------------------------------------------------|-----------------------------------------------|
| `GET /api/locations`                         | locations.py     | `BRONZE_ZENOTI_SALES_ACCRUAL`                                                       | Location dropdown                             |
| `GET /api/latest-date`                       | daily.py         | `BRONZE_ZENOTI_SALES_ACCRUAL`                                                       | Latest closed sale date                       |
| `GET /api/latest-cash-date`                  | daily.py         | `BRONZE_ZENOTI_CASH_COLLECTIONS`                                                    | Latest payment date (used on mount)           |
| `GET /api/daily-kpis`                        | daily.py         | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_APPOINTMENTS`                        | Prior-day KPI table                           |
| `GET /api/daily-sales-mix`                   | daily.py         | `BRONZE_ZENOTI_CASH_COLLECTIONS`                                                    | Daily sales mix table                         |
| `GET /api/mtd-kpi-header`                    | mtd.py           | `BRONZE_ZENOTI_CASH_COLLECTIONS` + `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` + `BRONZE_ZENOTI_APPOINTMENTS` | Top KPI tile strip |
| `GET /api/mtd-summary`                       | mtd.py           | `BRONZE_ZENOTI_CASH_COLLECTIONS`                                                    | MTD Performance Summary table                 |
| `GET /api/mtd-sales-mix`                     | mtd.py           | `BRONZE_ZENOTI_SALES_ACCRUAL`                                                       | MTD Sales Mix table                           |
| `GET /api/mtd-daily-trend`                   | mtd.py           | `BRONZE_ZENOTI_CASH_COLLECTIONS`                                                    | MTD daily + cumulative cash + trending        |
| `GET /api/operations-summary`                | operations.py    | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` + `BRONZE_ZENOTI_APPOINTMENTS` | Operations tab table       |
| `GET /api/monthly-trend`                     | operations.py    | `BRONZE_ZENOTI_SALES_ACCRUAL` + `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` + `BRONZE_ZENOTI_APPOINTMENTS` | Operational Metrics table  |
| `GET /api/employee-utilization`              | employees.py     | `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES`                                                  | Utilization pivot table                       |
| `GET /api/employee-rph`                      | employees.py     | `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` + `BRONZE_ZENOTI_SALES_ACCRUAL`                 | Rev/Hr pivot table                            |
| `GET /api/employee-scorecard`                | employees.py     | `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES` + `BRONZE_ZENOTI_SALES_ACCRUAL`                 | Employee Scorecard card grid                  |
| `GET /api/category-breakdown`                | charts.py        | `BRONZE_ZENOTI_SALES_ACCRUAL`                                                       | Donut chart — sales mix by category           |
| `GET /api/revenue-trend`                     | charts.py        | `BRONZE_ZENOTI_SALES_ACCRUAL`                                                       | Area chart — daily revenue trend              |
| `GET /api/appointments/summary`              | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Appointment KPI summary per location          |
| `GET /api/appointments/by-status`            | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Status breakdown donut chart                  |
| `GET /api/appointments/by-category`          | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Appointment count by service category         |
| `GET /api/appointments/by-provider`          | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Per-provider appointment metrics              |
| `GET /api/appointments/by-booking-source`    | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Booking source bar chart                      |
| `GET /api/appointments/cancellation-reasons` | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Cancellation reason breakdown                 |
| `GET /api/appointments/daily-trend`          | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Daily trend area/line chart                   |
| `GET /api/appointments/request-type`         | appointments.py  | `BRONZE_ZENOTI_APPOINTMENTS`                                                        | Provider preference breakdown                 |
| `POST /api/insights`                         | insights.py      | BigQuery `ai_insights_log`                                                          | AI insight generation with BigQuery cache     |
| `GET /health`                                | main.py          | —                                                                                   | Liveness probe                                |

### Query Parameters

| Param        | Applies to              | Description                        | Example                  |
|--------------|-------------------------|------------------------------------|--------------------------| 
| `start_date` | All MTD endpoints       | MTD start date (YYYY-MM-DD)        | `2026-06-01`             |
| `end_date`   | All MTD endpoints       | MTD end date (YYYY-MM-DD)          | `2026-06-04`             |
| `date`       | Daily endpoints only    | Target date (YYYY-MM-DD)           | `2026-06-04`             |
| `locations`  | All endpoints           | Repeatable location filter         | `?locations=Hoboken,+NJ` |

---

## Computation Metrics

### Revenue & Cash

| Metric                  | Formula                                                                                      | Source table                        |
|-------------------------|----------------------------------------------------------------------------------------------|-------------------------------------|
| `mtd_revenue`           | `SUM(sales_collected_exc_tax)`                                                               | `BRONZE_ZENOTI_CASH_COLLECTIONS`    |
| `avg_daily_revenue`     | `SUM(sales_collected_exc_tax) / COUNT(DISTINCT payment_date)`                                | `BRONZE_ZENOTI_CASH_COLLECTIONS`    |
| `recognized_revenue`    | `SUM(sales_inc_tax)` WHERE `status = 'closed'`                                               | `BRONZE_ZENOTI_SALES_ACCRUAL`       |
| `trending`              | `avg_daily_revenue × days_in_month`                                                          | computed                            |
| `cash_sales`            | `SUM(sales_collected_exc_tax)` within date range                                             | `BRONZE_ZENOTI_CASH_COLLECTIONS`    |
| `daily_revenue`         | `SUM(sales_exc_tax)` GROUP BY `sale_date`                                                    | `BRONZE_ZENOTI_SALES_ACCRUAL`       |

### Average Selling Price (ASP)

| Metric                    | Formula                                                                                    |
|---------------------------|--------------------------------------------------------------------------------------------|
| `blended_asp`             | `SUM(sales_collected_exc_tax WHERE category != 'Memberships') / COUNT(DISTINCT invoice_no WHERE category != 'Memberships')` |
| `asp_new_clients`         | `SUM(revenue WHERE first_visit='yes' AND category!='Memberships') / COUNT(DISTINCT guest WHERE first_visit='yes' AND category!='Memberships')` |
| `asp_existing_clients`    | Same as above for `first_visit='no'`                                                       |
| `asp` (daily)             | `SUM(sales_exc_tax WHERE status='closed') / COUNT(DISTINCT invoice_id WHERE status='closed')` |
| `asp_excl_memberships`    | Same but excludes `item_category = 'Memberships'`                                          |

### Client Counts

| Metric                    | Formula                                                                                    |
|---------------------------|--------------------------------------------------------------------------------------------|
| `total_client_count`      | `COUNT(DISTINCT guest_code)`                                                               |
| `new_client_count`        | `COUNT(DISTINCT guest_code WHERE is_new = 1)` — `is_new` from `guest_classification` CTE: `MAX(first_visit='yes')` per guest, so a guest with any `'yes'` row = new |
| `existing_client_count`   | `COUNT(DISTINCT guest_code WHERE is_new = 0)` — guaranteed: `new + existing = total` (no NULL leak) |
| `member_count`            | `COUNT(DISTINCT guest_code WHERE member = 'yes')`                                          |
| `new_members`             | `COUNT(DISTINCT guest_code WHERE item_category = 'Memberships')`                           |
| `membership_adoption_rate`| `new_members / total_client_count × 100`                                                   |

### MTD Variance (per-location, `mtd-summary`)

| Metric                    | Formula                                                                                    |
|---------------------------|--------------------------------------------------------------------------------------------|
| `prior_week_variance`     | `current_week_revenue - pw_revenue` (same date-of-week window, -7 days)                   |
| `prior_week_variance_pct` | `prior_week_variance / pw_revenue × 100`                                                   |
| `pm_variance`             | `cash_sales - pm_revenue` (same day-of-month window in prior calendar month)               |
| `pm_variance_pct`         | `pm_variance / pm_revenue × 100`                                                           |
| `py_variance`             | `cash_sales - py_revenue` (same date window, year − 1)                                     |
| `py_variance_pct`         | `py_variance / py_revenue × 100`                                                           |
| `same_store_yoy`          | `(mtd_revenue - py_revenue) / py_revenue × 100`                                            |
| `pct_to_goal_mtd`         | `cash_sales / monthly_budget × 100`                                                        |
| `pct_to_goal_total`       | `(avg_daily_sales × days_in_month) / monthly_budget × 100`                                 |

### Employee Performance

| Metric              | Formula                                                                                          |
|---------------------|--------------------------------------------------------------------------------------------------|
| `utilization`       | `SUM(booked_hours) / SUM(scheduled_hours) × 100` — per employee or per role                     |
| `rev_per_hr`        | `SUM(sales_exc_tax) / SUM(booked_hours)` — schedule and sales pre-aggregated to (center, employee, day) grain before join to avoid fan-out |
| `total_revenue`     | `SUM(sales_exc_tax)` from `BRONZE_ZENOTI_SALES_ACCRUAL` joined to schedule on `serviced_by = employee_name AND sale_date = date AND center_name` |

Hours are stored as `HH:MM` varchar. Converted via:
```sql
CAST(SUBSTRING(col, 1, CHARINDEX(':', col)-1) AS FLOAT)
+ CAST(SUBSTRING(col, CHARINDEX(':', col)+1, LEN(col)) AS FLOAT) / 60.0
```

### Cost & Margin (hardcoded assumptions)

| Metric            | Value / Formula                            |
|-------------------|--------------------------------------------|
| `cogs_pct`        | 20% of recognized revenue                 |
| `payroll_pct`     | 22% × 1.12 (includes 12% benefits load)   |
| `gross_margin_pct`| `(1 − 0.20 − 0.22 × 1.12) × 100` ≈ 55.4% |
| `cogs_est`        | `recognized_revenue × 0.20`               |
| `payroll_costs_est`| `recognized_revenue × 0.22 × 1.12`       |
| `gross_margin`    | `recognized_revenue × (1 − 0.20 − 0.22 × 1.12)` |

### Appointment Metrics

| Metric               | Formula                                                                                     |
|----------------------|---------------------------------------------------------------------------------------------|
| `no_show_rate`       | `COUNT(status='no show') / COUNT(status != 'deleted') × 100`                               |
| `cancellation_rate`  | `COUNT(status='cancelled') / COUNT(status != 'deleted') × 100`                             |
| `rebooking_rate`     | `COUNT(rebooked='yes' AND status='closed') / COUNT(status='closed') × 100`                 |
| `completion_rate`    | `COUNT(status='closed') / COUNT(*) × 100`                                                  |
| `late_checkin_rate`  | `COUNT(checkin_time > start_time) / COUNT(checkin_time IS NOT NULL) × 100`                 |
| `avg_actual_duration`| `AVG(actual_duration)` in decimal hours — only closed, non-add-on, positive-duration rows  |

All appointment queries exclude `add_on = 'No'` filter (primary appointments only) and exclude `status = 'deleted'` unless noted.

### Sales Mix Categories

Revenue bucketed by `item_category` / `item_sub_category`:

| Bucket              | Category / Sub-category match                                      |
|---------------------|--------------------------------------------------------------------|
| `body_contouring`   | `item_category = 'Body Contouring'` OR `item_sub_category = 'Body Contouring'` |
| `facials`           | `item_category = 'Facials'`                                        |
| `filler`            | `item_sub_category = 'Filler'`                                     |
| `laser_hair_removal`| `item_category = 'Laser Hair Removal'` OR `item_sub_category = 'Laser Hair Removal'` |
| `memberships`       | `item_category = 'Memberships'`                                    |
| `neurotoxins`       | `item_sub_category = 'Toxin'`                                      |
| `other_injectables` | `item_sub_category = 'Other Injectables'`                          |
| `prf`               | `item_sub_category = 'PRF'`                                        |
| `retail`            | `item_category = 'Retail'`                                         |
| `skin_rejuvenation` | `item_category = 'Skin Rejuvenation'`                              |
| `other`             | Anything not matched by above buckets                              |

### Budget (hardcoded in `mtd.py`)

Monthly budget per location stored as a SQL Server `VALUES` inline table. Totals ≈ $1,950,000/month across 14 locations.

---

## Frontend Architecture

### State Management — `useDashboard.js`

Single source of truth for all dashboard data. Key behaviors:

- **Boot sequence:** On mount, `/api/latest-cash-date` and `/api/locations` fetched in parallel. `filters` stays `null` until both resolve, preventing any data fetch with wrong dates.
- **Debounce:** Filter changes debounced 300 ms. Back-to-back updates collapse into single fetch.
- **Abort control:** Each fetch batch tied to `AbortController`. New filter change cancels in-flight batch.
- **21 parallel requests:** All endpoints fetched in single `Promise.all` per refresh cycle.

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

Dynamically measures combined rendered height of `.topbar`, `.tiles`, `.tabbar` to set `marginTop` on `.content`. Prevents tab content from being obscured by fixed header stack.

### Employee Performance Tiers

| Role              | High Performer               | Average                      | Needs Focus       |
|-------------------|------------------------------|------------------------------|-------------------|
| Treatment Provider| Util ≥ 75% AND Rev/Hr ≥ $550 | Util ≥ 60% AND Rev/Hr ≥ $450 | Below thresholds  |
| Esthetician       | Util ≥ 75% AND Rev/Hr ≥ $175 | Util ≥ 60% AND Rev/Hr ≥ $125 | Below thresholds  |

---

## Connection Wiring

```
Frontend (React)
  └── useDashboard.js
        └── fetchJSON() → REACT_APP_API_URL (default: http://localhost:8000)
              │
              ▼
Backend (FastAPI)
  └── main.py
        ├── RequestLoggingMiddleware → BigQuery api_log (fire-and-forget thread)
        └── routers/*.py
              └── db.py → run_query()
                    └── config.get_sql_connection()
                          └── pymssql → SQL Server (SQL_SERVER_HOST:SQL_SERVER_PORT)
                                └── database: SQL_SERVER_DATABASE (default: evolve_spa)
                                      ├── BRONZE_ZENOTI_SALES_ACCRUAL        (SQL_SALES_TABLE)
                                      ├── BRONZE_ZENOTI_EMPLOYEE_SCHEDULES   (SQL_SCHEDULE_TABLE)
                                      ├── BRONZE_ZENOTI_APPOINTMENTS         (SQL_APPT_TABLE)
                                      └── BRONZE_ZENOTI_CASH_COLLECTIONS     (SQL_CASH_TABLE)

insights.py (POST /api/insights)
  ├── BigQuery ai_insights_log → cache check (BQ_CLIENT)
  ├── OpenAI gpt-4o-mini (primary)
  ├── Gemini gemini-flash-latest (fallback)
  └── BigQuery ai_insights_log → cache write (fire-and-forget thread)
```

Connection pool: max 5 connections. Each `run_query()` call checks out a connection, executes, returns to pool. Pool validates connections with `SELECT 1` before reuse.

---

## Request Logging

Every API request logged to BigQuery `api_log` by `RequestLoggingMiddleware` (registered in `main.py`). Each row captures:

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

Table is day-partitioned on `timestamp`, auto-created on startup. `/health` excluded from logging.

```sql
SELECT *
FROM `your_project.your_dataset.api_log`
WHERE request_id = '<id-from-the-UI>'
```

---

## Error Handling

**Backend** (`utils/errors.py`) — every unhandled exception in every router:
1. Attaches `error_type`, `error_message`, `traceback` to `request.state`.
2. `RequestLoggingMiddleware` folds this into the same `api_log` row — no separate table, no extra latency.
3. Returns `{ error, request_id }` JSON body so frontend can surface correlation ID.

**Frontend** (`useDashboard.js`) — catches HTTP/network failures, surfaces message in UI error banner. `AbortError` silently ignored (expected when newer request cancels in-flight one).

---

## AI Insights Cache

`POST /api/insights` caches every AI response in BigQuery `ai_insights_log` to avoid redundant API calls.

**Flow:**
1. `sha256(tab + "|" + prompt)` cache key generated from request.
2. BigQuery checked for existing row within TTL window (default 60 minutes, `AI_INSIGHTS_CACHE_TTL_MINUTES`).
3. **Cache hit** → saved insight returned immediately, no AI call.
4. **Cache miss** → OpenAI (`gpt-4o-mini`) called first; Gemini (`gemini-flash-latest`) as fallback. Result saved to BigQuery asynchronously in daemon thread.

Response includes `"cached": true/false` and `provider` (`"openai"` or `"gemini"`).

Table is day-partitioned on `created_at`, clustered on `cache_key`, auto-created on startup.

---

## Employee Data Design

Employee names and roles flow:

1. `BRONZE_ZENOTI_EMPLOYEE_SCHEDULES.employee_name` → who is scheduled; `job_name` → their role
2. `BRONZE_ZENOTI_SALES_ACCRUAL.serviced_by` → who delivered each service
3. JOIN: `employee_name = serviced_by AND DATE(date) = DATE(sale_date) AND center_name = center_name`

**Fan-out prevention:** Schedule and sales are each pre-aggregated to `(center, employee, day)` grain in separate CTEs before joining. Joining line-item-grain sales directly to raw schedule rows and summing `booked_hours` over the result re-adds the same day's hours once per sales line item, wildly understating Rev/Hr.

`job_name` values used: `Treatment Provider` and `Esthetician`. Managers, Clinic Directors, Concierge excluded from all utilization and Rev/Hr metrics.

Daily pivot columns (`d1`, `d2`, … `dN`) renamed from `d_YYYYMMDD` format by `_rename_pivot_cols()` in `employees.py` before response is returned.

---

## Daily KPI Date Resolution

`/api/daily-kpis` and `/api/daily-sales-mix` apply effective-date resolution: if requested date has no closed sales (future date, month boundary, closed day), query walks back up to 6 days to find most recent date with data. Prevents empty tables on non-business days.

`/api/latest-cash-date` applies the same logic globally against `BRONZE_ZENOTI_CASH_COLLECTIONS` and is called on app boot to seed initial filter state.

---

## Filter Helpers — `utils/filters.py`

| Function              | Purpose                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `build_date_filter`   | Builds `WHERE` clause for `sale_date` / `appointment_date` + location  |
| `build_sched_filter`  | Builds self-contained `WHERE` block for `employee_schedule` queries; renames date params to avoid collision with main query params. Always appends role guard (`Treatment Provider`, `Esthetician`) and positive-duration guard |
| `build_join_where`    | Rewrites a sales `WHERE` clause to use `sa.` alias for JOIN queries    |
| `merge_params`        | Concatenates multiple BigQuery/SQL param lists (positional `%s`)        |
| `loc_in`              | Builds `AND center_name IN (%s, ...)` snippet for existing WHERE blocks |
| `hhmm_to_hours`       | SQL expression: converts `HH:MM` varchar to decimal hours (FLOAT)      |
| `is_positive_duration`| SQL condition: non-null, non-zero `HH:MM` or numeric duration          |

---

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in SQL Server + GCP credentials
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
| `SQL_SERVER_HOST`                | ✅       | SQL Server hostname or IP                                 |
| `SQL_SERVER_PORT`                |          | SQL Server port (default: `1433`)                         |
| `SQL_SERVER_USER`                | ✅       | SQL Server username                                       |
| `SQL_SERVER_PASSWORD`            | ✅       | SQL Server password                                       |
| `SQL_SERVER_DATABASE`            |          | Database name (default: `evolve_spa`)                     |
| `SQL_SALES_TABLE`                |          | Sales accrual table (default: `dbo.sales_accrual`)        |
| `SQL_SCHEDULE_TABLE`             |          | Employee schedule table (default: `dbo.employee_schedule`)|
| `SQL_APPT_TABLE`                 |          | Appointments table (default: `dbo.appointments`)          |
| `SQL_CASH_TABLE`                 |          | Cash collections table (default: `dbo.BRONZE_ZENOTI_CASH_COLLECTIONS`) |
| `BIGQUERY_PROJECT_ID`            |          | GCP project ID (for api_log + insights only)              |
| `BIGQUERY_DATASET`               |          | BigQuery dataset name                                     |
| `BIGQUERY_API_LOG_TABLE`         |          | Request log table name (default: `api_log`)               |
| `BIGQUERY_INSIGHTS_TABLE`        |          | AI insights cache table name (default: `ai_insights_log`) |
| `GOOGLE_APPLICATION_CREDENTIALS` |          | Path to service account JSON file                         |
| `BIGQUERY_CREDENTIALS_BASE64`    |          | Base64-encoded service account JSON (Railway-friendly)    |
| `OPENAI_API_KEY`                 |          | OpenAI API key (primary AI provider)                      |
| `GEMINI_API_KEY`                 |          | Gemini API key (fallback AI provider)                     |
| `AI_INSIGHTS_CACHE_TTL_MINUTES`  |          | Insight cache lifetime in minutes (default: `60`)         |
| `APP_ENV`                        |          | Environment tag in logs (default: `production`)           |
