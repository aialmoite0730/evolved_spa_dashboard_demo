import React, { useState } from "react";
import "./App.css";
import { useDashboard } from "./hooks/useDashboard";
import KpiHeader from "./components/KpiHeader";
import DailyKPITable from "./components/DailyKPITable";
import SalesMixTable from "./components/SalesMixTable";
import MTDSummaryTable from "./components/MTDSummaryTable";
import MonthlyTrendTable from "./components/MonthlyTrendTable";
import OperationsTable from "./components/OperationsTable";
import { RevenueTrendChart, LocationBarChart } from "./components/RevenueTrendChart";
import CategoryBreakdown from "./components/CategoryBreakdown";
import EmployeeUtilTable from "./components/EmployeeUtilTable";
import EmployeeRphTable from "./components/EmployeeRphTable";
import EmployeeScorecard from "./components/EmployeeScorecard";

const TABS = [
  { id: "daily",     label: "Daily KPIs" },
  { id: "mtd",       label: "MTD Performance" },
  { id: "ops",       label: "Operations" },
  { id: "scorecard", label: "Employee Scorecard" },
];

function fmtDateLong(dateStr) {
  const d = dateStr ? new Date(dateStr + "T00:00:00") : new Date();
  return d.toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });
}

function mtdLabel(start, end) {
  const fmt  = s => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" });
  const thru = s => new Date(s + "T00:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric" });
  return `${fmt(start)} · Through ${thru(end)}`;
}

export default function App() {
  const dash = useDashboard();
  const [tab, setTab]  = useState("daily");

  const locCount       = dash.locations.length;
  const activeLocCount = dash.filters.locations.length;

  return (
    <div className="app">

      {/* ══ TOP BAR ══════════════════════════════════════════════════════════ */}
      <div className="topbar">
        {/* Brand */}
        <div className="brand">
          <div className="brand-mark">
            <svg width="28" height="20" viewBox="0 0 28 20" fill="none">
              <polygon points="0,0 14,20 28,0 22,0 14,13 6,0" fill="#A37B88" />
              <polygon points="6,0 14,13 14,20 0,0" fill="#c4a0ac" opacity="0.6" />
            </svg>
          </div>
          <div className="brand-wordmark">
            <div className="brand-name">evolve</div>
            <div className="brand-sub">Med Spa · Analytics</div>
          </div>
        </div>

        <div className="topbar-divider" />

        {/* Filters */}
        <div className="topbar-filters">
          {/* Location */}
          <div className="filter-group">
            <label>Location</label>
            <select
              className="ev-input"
              value={activeLocCount === 0 ? "all" : dash.filters.locations[0]}
              onChange={e => {
                if (e.target.value === "all") dash.updateFilter("locations", []);
                else dash.updateFilter("locations", [e.target.value]);
              }}
            >
              <option value="all">All ({locCount} locations)</option>
              {dash.locations.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>

          {/* MTD From */}
          <div className="filter-group">
            <label>MTD From</label>
            <input
              type="date"
              className="ev-input"
              value={dash.filters.startDate}
              onChange={e => dash.updateFilter("startDate", e.target.value)}
            />
          </div>

          {/* MTD To */}
          <div className="filter-group">
            <label>MTD To</label>
            <input
              type="date"
              className="ev-input"
              value={dash.filters.endDate}
              onChange={e => dash.updateFilter("endDate", e.target.value)}
            />
          </div>

          <div className="topbar-divider" />

          <div className="report-label">
            {fmtDateLong(dash.filters.endDate)}
            &nbsp;·&nbsp;
            MTD {new Date(dash.filters.startDate + "T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" })}
          </div>

          {dash.loading && (
            <div style={{
              fontSize: 9, color: "#A37B88", fontWeight: 300,
              letterSpacing: "0.12em", textTransform: "uppercase",
            }}>
              ⟳ Loading…
            </div>
          )}
        </div>
      </div>

      {/* ══ KPI TILES ════════════════════════════════════════════════════════ */}
      <KpiHeader data={dash.kpiHeader} />

      {/* ══ TAB BAR ══════════════════════════════════════════════════════════ */}
      <div className="tabbar">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab-btn${tab === t.id ? " active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ══ ERROR BANNER ═════════════════════════════════════════════════════ */}
      {dash.error && (
        <div className="error-banner" style={{ margin: "0 24px" }}>⚠ {dash.error}</div>
      )}

      {/* ══ CONTENT ══════════════════════════════════════════════════════════ */}
      <div className="content">

        {/* ─── DAILY KPIs ─────────────────────────────────────────────── */}
        {tab === "daily" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">Daily Cash Sales by Location</div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.dailyKpis}
                    xKey="location"
                    yKey="cash_sales"
                    label="Cash Sales"
                    yType="cur"
                    secondaryKey="daily_need"
                    secondaryLabel="Daily Need"
                  />
                </div>
              </div>
              <div className="chart-box">
                <div className="chart-title">Daily Sales Mix</div>
                <div className="chart-inner">
                  <CategoryBreakdown data={dash.categoryBreakdown} />
                </div>
              </div>
            </div>

            <div className="sec-hdr">
              Prior Day KPIs
              <span className="sec-sub">{fmtDateLong(dash.filters.endDate)}</span>
            </div>
            <DailyKPITable data={dash.dailyKpis} />

            <div className="sec-hdr mt2">Daily Sales Mix</div>
            <SalesMixTable data={dash.dailyMix} />
          </>
        )}

        {/* ─── MTD PERFORMANCE ────────────────────────────────────────── */}
        {tab === "mtd" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">MTD Revenue vs Budget by Location</div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.mtdSummary}
                    xKey="location"
                    yKey="cash_sales"
                    label="MTD Sales"
                    yType="cur"
                    secondaryKey="monthly_budget"
                    secondaryLabel="Budget"
                  />
                </div>
              </div>
              <div className="chart-box">
                <div className="chart-title">MTD Sales Mix</div>
                <div className="chart-inner">
                  <CategoryBreakdown data={dash.categoryBreakdown} />
                </div>
              </div>
            </div>

            <div className="sec-hdr">
              MTD Performance Summary
              <span className="sec-sub">{mtdLabel(dash.filters.startDate, dash.filters.endDate)}</span>
            </div>
            <MTDSummaryTable data={dash.mtdSummary} />

            <div className="sec-hdr mt2">MTD Sales Mix</div>
            <SalesMixTable data={dash.mtdMix} />
          </>
        )}

        {/* ─── OPERATIONS ─────────────────────────────────────────────── */}
        {tab === "ops" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">Provider Utilization % by Location — MTD</div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.operations}
                    xKey="location"
                    yKey="provider_utilization"
                    label="Provider Util %"
                    yType="pct"
                    target={75}
                  />
                </div>
              </div>
              <div className="chart-box">
                <div className="chart-title">Revenue per Utilized Hour by Location — MTD</div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.operations}
                    xKey="location"
                    yKey="rev_per_provider"
                    label="Rev / Hr (Prov)"
                    yType="cur"
                    target={550}
                  />
                </div>
              </div>
            </div>

            <div className="sec-hdr">Monthly Trend — Operational Metrics</div>
            <OperationsTable data={dash.operations} />

            {/* Employee-level utilization — powered by employee_schedule */}
            <EmployeeUtilTable data={dash.employeeUtil} />

            {/* Employee-level Rev/Hr — powered by schedule + sales join */}
            <EmployeeRphTable data={dash.employeeRph} />
          </>
        )}

        {/* ─── EMPLOYEE SCORECARD ─────────────────────────────────────── */}
        {tab === "scorecard" && (
          <EmployeeScorecard data={dash.employeeScorecard} />
        )}

      </div>
    </div>
  );
}