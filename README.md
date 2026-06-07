# Evolve Med Spa — Analytics Dashboard

## Architecture

```
BigQuery (3 tables)
  ├── sales_accrual        → Revenue, sales mix, KPIs, ASP, client counts
  ├── employee_schedule    → Utilization (booked_hours / scheduled_hours)
  └── appointments         → No-shows, cancellations, rebooking rate

FastAPI (backend/main.py)
  └── React (frontend/src/) → Dashboard UI
```

## Data Source Mapping

| Dashboard metric            | Source table(s)                        | Join key                              |
|-----------------------------|----------------------------------------|---------------------------------------|
| Cash sales, ASP, mix        | `sales_accrual`                        | —                                     |
| No-shows / cancellations    | `appointments`                         | center_name + appointment_date        |
| Rebooking rate              | `appointments.rebooked`                | center_name + date range              |
| Provider / Esti utilization | `employee_schedule`                    | booked_hours ÷ scheduled_hours        |
| Revenue per utilized hour   | `sales_accrual` + `employee_schedule`  | `serviced_by` = `employee_name`       |
| Employee role (Provider/Esti)| `employee_schedule.job_name`          | —                                     |
| Employee name               | `sales_accrual.serviced_by`           | matched to `employee_schedule.employee_name` |

## API Endpoints

| Endpoint                    | Powers                                         |
|-----------------------------|------------------------------------------------|
| `GET /api/locations`        | Location dropdown                              |
| `GET /api/daily-kpis`       | Prior-day KPI table + bar chart                |
| `GET /api/daily-sales-mix`  | Daily sales mix table                          |
| `GET /api/mtd-kpi-header`   | Top KPI tile strip (both rows)                 |
| `GET /api/mtd-summary`      | MTD Performance Summary table                  |
| `GET /api/mtd-sales-mix`    | MTD Sales Mix table                            |
| `GET /api/monthly-trend`    | Operations — Operational Metrics table         |
| `GET /api/operations-summary`| Operations tab charts + table                 |
| `GET /api/employee-utilization` | Ops — Utilization by Employee (daily pivot) |
| `GET /api/employee-rph`     | Ops — Rev/Hr by Employee (daily pivot)         |
| `GET /api/employee-scorecard`| Employee Scorecard card grid                  |
| `GET /api/category-breakdown`| Donut chart — sales mix by category           |
| `GET /api/revenue-trend`    | Area chart — daily revenue trend               |

## Query Parameters (all endpoints except `/api/locations`)

| Param        | Description                         | Example              |
|--------------|-------------------------------------|----------------------|
| `start_date` | MTD start date (YYYY-MM-DD)         | `2026-06-01`         |
| `end_date`   | MTD end date / prior-day date       | `2026-06-04`         |
| `date`       | Daily endpoints only                | `2026-06-04`         |
| `locations`  | Repeatable — filter to location(s)  | `?locations=Hoboken,+NJ` |

## Setup

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in your GCP project & credentials
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
REACT_APP_API_URL=http://localhost:8000 npm start
```

## Employee Data Design

Employee names flow as follows:
1. `employee_schedule.employee_name` → defines who is scheduled and their role (`job_name`)
2. `sales_accrual.serviced_by` → records who delivered each service
3. JOIN on `employee_name = serviced_by AND DATE(date) = DATE(sale_date) AND center_name = center_name`

This join enables:
- Utilization = `booked_hours / scheduled_hours` per employee per day
- Rev/Hr = `SUM(sales_exc_tax) / SUM(booked_hours)` per employee per day

**job_name values used:** `Treatment Provider` and `Esthetician`  
(Managers, Clinic Directors, Concierge roles are excluded from utilization/rev-hr metrics)