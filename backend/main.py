"""
Evolve Med Spa — Analytics API
================================
This file is the orchestrator only.
No SQL, no business logic, no filter helpers.

Responsibilities:
  1. Create the FastAPI app instance.
  2. Configure CORS.
  3. Register all routers.
  4. Expose /health.

Everything else lives in:
  config.py          ← SQL Server connection pool + table references
  db.py              ← run_query, serialize_rows
  utils/filters.py   ← WHERE-clause builders
  utils/errors.py    ← structured error logger → SQL Server
  routers/
    locations.py     ← GET /api/locations
    daily.py         ← GET /api/daily-kpis, /api/daily-sales-mix
    mtd.py           ← GET /api/mtd-kpi-header, /api/mtd-summary, /api/mtd-sales-mix
    operations.py    ← GET /api/operations-summary, /api/monthly-trend
    employees.py     ← GET /api/employee-utilization, /api/employee-rph, /api/employee-scorecard
    charts.py        ← GET /api/category-breakdown, /api/revenue-trend
    insights.py      ← POST /api/insights

✅ SWITCHED FROM BIGQUERY TO SQL SERVER
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import triggers config.py → SQL Server connection pool init
import config  # noqa: F401  (side-effect import)

from routers import locations, daily, mtd, operations, employees, charts, appointments, insights
from utils.request_logs import RequestLoggingMiddleware


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Evolve Med Spa Dashboard API",
    version="2.0.0",
    description="Analytics API for the Evolve Med Spa multi-location dashboard.",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your frontend domain in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
# ─── Request / error logging ───────────────────────────────────────────────────
app.add_middleware(RequestLoggingMiddleware)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(locations.router,   tags=["Locations"])
app.include_router(daily.router,       tags=["Daily KPIs"])
app.include_router(mtd.router,         tags=["MTD Performance"])
app.include_router(operations.router,  tags=["Operations"])
app.include_router(employees.router,   tags=["Employees"])
app.include_router(charts.router,      tags=["Charts"])
app.include_router(appointments.router,tags=["Appointments"])
app.include_router(insights.router,    tags=["AI Insights"])

# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    """Liveness probe — returns 200 if the API process is running."""
    return {"status": "ok", "version": app.version}