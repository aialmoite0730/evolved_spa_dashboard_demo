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
import AppointmentsDashboard from "./components/AppointmentsDashboard";
import AiInsights from "./components/AiInsights";

const TABS = [
  { id: "daily",     label: "Daily KPIs" },
  { id: "mtd",       label: "MTD Performance" },
  { id: "ops",       label: "Operations" },
  { id: "scorecard", label: "Employee Scorecard" },
  { id: "appointments", label: "Appointments" },
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
  const [tab, setTab] = useState("daily");

  const locCount       = dash.locations.length;
  const activeLocCount = dash.filters.locations.length;
  const isDay          = dash.viewMode === "day";

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

          {/* ── Day / Month toggle ── */}
          <div className="filter-group">
            <label>View</label>
            <div className="view-toggle">
              <button
                className={`view-toggle-btn${isDay ? " active" : ""}`}
                onClick={() => dash.setViewMode("day")}
              >
                Day
              </button>
              <button
                className={`view-toggle-btn${!isDay ? " active" : ""}`}
                onClick={() => dash.setViewMode("month")}
              >
                Month
              </button>
            </div>
          </div>

          {/* ── Date inputs — swap based on view mode ── */}
          {isDay ? (
            <div className="filter-group">
              <label>Date</label>
              <input
                type="date"
                className="ev-input"
                value={dash.filters.dayDate}
                onChange={e => dash.updateFilter("dayDate", e.target.value)}
              />
            </div>
          ) : (
            <>
              <div className="filter-group">
                <label>MTD From</label>
                <input
                  type="date"
                  className="ev-input"
                  value={dash.filters.startDate}
                  onChange={e => dash.updateFilter("startDate", e.target.value)}
                />
              </div>
              <div className="filter-group">
                <label>MTD To</label>
                <input
                  type="date"
                  className="ev-input"
                  value={dash.filters.endDate}
                  onChange={e => dash.updateFilter("endDate", e.target.value)}
                />
              </div>
            </>
          )}

          {/* ── Location ── */}
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

          <div className="topbar-divider" />

          {/* ── Report label ── */}
          <div className="report-label">
            {isDay
              ? fmtDateLong(dash.filters.dayDate)
              : (
                <>
                  {fmtDateLong(dash.effectiveEnd)}
                  &nbsp;·&nbsp;
                  MTD {new Date(dash.effectiveStart + "T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" })}
                </>
              )
            }
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
      <KpiHeader data={dash.kpiHeader} viewMode={dash.viewMode} />

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

        {/* ══ AI INSIGHTS ═════════════════════════════════════════════════════ */}
        <AiInsights
          tab={tab}
          dash={dash}
          effectiveStart={dash.effectiveStart}
          effectiveEnd={dash.effectiveEnd}
        />

        {/* ─── DAILY KPIs ─────────────────────────────────────────────── */}
        {tab === "daily" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">
                  {isDay ? "Cash Sales by Location" : "Daily Cash Sales by Location"}
                </div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.dailyKpis}
                    xKey="location"
                    yKey="cash_sales"
                    label="Cash Sales"
                    yType="cur"
                  />
                </div>
              </div>
              <div className="chart-box">
                <div className="chart-title">
                  {isDay ? "Sales Mix" : "Daily Sales Mix"}
                </div>
                <div className="chart-inner">
                  <CategoryBreakdown data={dash.categoryBreakdown} />
                </div>
              </div>
            </div>

            <div className="sec-hdr">
              {isDay ? "KPIs" : "Prior Day KPIs"}
              <span className="sec-sub">{fmtDateLong(dash.effectiveEnd)}</span>
            </div>
            <DailyKPITable data={dash.dailyKpis} />

            <div className="sec-hdr mt2">
              {isDay ? "Sales Mix" : "Daily Sales Mix"}
            </div>
            <SalesMixTable data={dash.dailyMix} />
          </>
        )}

        {/* ─── MTD PERFORMANCE ────────────────────────────────────────── */}
        {tab === "mtd" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">
                  {isDay ? "Revenue vs Budget by Location" : "MTD Revenue vs Budget by Location"}
                </div>
                <div className="chart-inner">
                  <LocationBarChart
                    data={dash.mtdSummary}
                    xKey="location"
                    yKey="cash_sales"
                    label="Cash Sales"
                    yType="cur"
                  />
                </div>
              </div>
              <div className="chart-box">
                <div className="chart-title">
                  {isDay ? "Sales Mix" : "MTD Sales Mix"}
                </div>
                <div className="chart-inner">
                  <CategoryBreakdown data={dash.categoryBreakdown} />
                </div>
              </div>
            </div>

            <div className="sec-hdr">
              {isDay ? "Performance Summary" : "MTD Performance Summary"}
              <span className="sec-sub">
                {isDay
                  ? fmtDateLong(dash.effectiveEnd)
                  : mtdLabel(dash.effectiveStart, dash.effectiveEnd)
                }
              </span>
            </div>
            <MTDSummaryTable data={dash.mtdSummary} />

            <div className="sec-hdr mt2">
              {isDay ? "Sales Mix" : "MTD Sales Mix"}
            </div>
            <SalesMixTable data={dash.mtdMix} />
          </>
        )}

        {/* ─── OPERATIONS ─────────────────────────────────────────────── */}
        {tab === "ops" && (
          <>
            <div className="chart-row">
              <div className="chart-box">
                <div className="chart-title">
                  Provider Utilization % by Location{isDay ? "" : " — MTD"}
                </div>
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
                <div className="chart-title">
                  Revenue per Utilized Hour by Location{isDay ? "" : " — MTD"}
                </div>
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

            <div className="sec-hdr">
              {isDay ? "Operational Metrics" : "Monthly Trend — Operational Metrics"}
            </div>
            <OperationsTable data={dash.operations} />

            <EmployeeUtilTable data={dash.employeeUtil} />
            <EmployeeRphTable  data={dash.employeeRph} />
          </>
        )}

        {/* ─── EMPLOYEE SCORECARD ─────────────────────────────────────── */}
        {tab === "scorecard" && (
          <EmployeeScorecard data={dash.employeeScorecard} />
        )}

        {/* ─── APPOINTMENTS ───────────────────────────────────────────── */}
        {tab === "appointments" && (
          <>
            <div className="sec-hdr">
              Appointments Dashboard
              <span className="sec-sub">
                {isDay ? fmtDateLong(dash.effectiveEnd) : mtdLabel(dash.effectiveStart, dash.effectiveEnd)}
              </span>
            </div>
            <AppointmentsDashboard
              summary={dash.apptSummary}
              byStatus={dash.apptByStatus}
              byCategory={dash.apptByCategory}
              byProvider={dash.apptByProvider}
              bySource={dash.apptBySource}
              cancelReasons={dash.apptCancelReasons}
              dailyTrend={dash.apptDailyTrend}
              requestType={dash.apptRequestType}
            />
          </>
        )}

      </div>
    </div>
  );
}