import React, { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell,
  LineChart, Line, AreaChart, Area,
} from "recharts";
import { fmt } from "../utils/format";

// ── Palette ──────────────────────────────────────────────────────────────────
const C = {
  completed:     "#1a5c34",
  no_show:       "#c0392b",
  cancelled:     "#e67e22",
  total:         "#A37B88",
  pink:          "#A37B88",
  pink2:         "#c4a0ac",
  grey:          "#6b7280",
  dark:          "#2E2E2E",
};
const STATUS_COLORS = [C.completed, C.cancelled, C.no_show, C.grey, C.pink2];

// ── Shared tooltip ────────────────────────────────────────────────────────────
const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#fff", border: "1px solid #E8E7E4",
      padding: "8px 12px", fontSize: 11,
      fontFamily: "'Josefin Sans', sans-serif",
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", gap: 8, marginTop: 2 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color,
            display: "inline-block", marginTop: 3, flexShrink: 0 }} />
          <span style={{ color: "#aaa" }}>{p.name}:</span>
          <span style={{ marginLeft: "auto", fontFamily: "monospace" }}>
            {typeof p.value === "number" && p.value % 1 !== 0
              ? p.value.toFixed(1) + (p.name?.includes("%") ? "%" : "")
              : p.value}
          </span>
        </div>
      ))}
    </div>
  );
};

// ── KPI Tile ─────────────────────────────────────────────────────────────────
function ATile({ label, val, sub, cls }) {
  return (
    <div className={`tile${cls ? " " + cls : ""}`}>
      <div className="tile-lbl">{label}</div>
      <div className="tile-val">{val}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

function pct(v, d = 1) {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toFixed(d) + "%";
}
function num(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return new Intl.NumberFormat("en-US").format(Math.round(Number(v)));
}
function mins(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return `${Math.round(Number(v))} min`;
}

// ── Summary KPI tiles ─────────────────────────────────────────────────────────
function SummaryTiles({ data }) {
  if (!data?.length) return null;

  const totals = data.reduce((acc, row) => {
    acc.total_appointments += Number(row.total_appointments || 0);
    acc.completed          += Number(row.completed          || 0);
    acc.no_shows           += Number(row.no_shows           || 0);
    acc.cancellations      += Number(row.cancellations      || 0);
    acc.new_guests         += Number(row.new_guests         || 0);
    acc.unique_guests      += Number(row.unique_guests      || 0);
    return acc;
  }, { total_appointments: 0, completed: 0, no_shows: 0, cancellations: 0, new_guests: 0, unique_guests: 0 });

  const nsr  = totals.total_appointments ? (totals.no_shows      / totals.total_appointments * 100) : null;
  const cr   = totals.total_appointments ? (totals.cancellations  / totals.total_appointments * 100) : null;
  const comp = totals.total_appointments ? (totals.completed      / totals.total_appointments * 100) : null;

  const validRows = data.filter(r => r.avg_actual_duration);
  const avgDur    = validRows.length
    ? validRows.reduce((a, r) => a + Number(r.avg_actual_duration), 0) / validRows.length
    : null;
  const rbRows    = data.filter(r => r.rebooking_rate);
  const avgRb     = rbRows.length
    ? rbRows.reduce((a, r) => a + Number(r.rebooking_rate), 0) / rbRows.length
    : null;

  return (
    <div className="tiles">
      <div className="tiles-row">
        <ATile label="Total Appointments" val={num(totals.total_appointments)} sub="excl. add-ons & deleted" />
        <ATile label="Completed"          val={num(totals.completed)}          sub={`${pct(comp)} completion rate`} cls={comp >= 85 ? "good" : comp >= 70 ? "warn" : "bad"} />
        <ATile label="No-Shows"           val={num(totals.no_shows)}           sub={`${pct(nsr)} no-show rate`}    cls={nsr <= 5 ? "good" : nsr <= 10 ? "warn" : "bad"} />
        <ATile label="Cancellations"      val={num(totals.cancellations)}      sub={`${pct(cr)} cancel rate`}      cls={cr <= 10 ? "good" : cr <= 20 ? "warn" : "bad"} />
        <ATile label="Unique Guests"      val={num(totals.unique_guests)}      sub="closed appointments" />
        <ATile label="New Guests"         val={num(totals.new_guests)}         sub="first_visit = true" />
        <ATile label="Avg Actual Duration" val={mins(avgDur)}                  sub="closed appointments" />
        <ATile label="Rebooking Rate"     val={pct(avgRb)}                     sub="avg across locations" cls={avgRb >= 40 ? "good" : avgRb >= 25 ? "warn" : "bad"} />
      </div>
    </div>
  );
}

// ── Status donut ──────────────────────────────────────────────────────────────
function StatusDonut({ data }) {
  if (!data?.length) return <div className="empty-state">No status data.</div>;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="status"
          cx="50%" cy="50%" innerRadius={50} outerRadius={85} paddingAngle={2}>
          {data.map((_, i) => <Cell key={i} fill={STATUS_COLORS[i % STATUS_COLORS.length]} />)}
        </Pie>
        <Tooltip formatter={(v, n) => [num(v), n]} />
        <Legend iconType="circle" iconSize={7}
          formatter={v => <span style={{ fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
            letterSpacing: "0.08em", textTransform: "uppercase" }}>{v}</span>} />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Daily trend chart ─────────────────────────────────────────────────────────
// Single data point → grouped BarChart (area/line with 1 point = floating dots)
// Multiple points   → AreaChart
function DailyTrend({ data }) {
  if (!data?.length) return <div className="empty-state">No trend data.</div>;

  const fmtDate = d => d ? new Date(d + "T00:00:00").toLocaleDateString("en-US",
    { month: "short", day: "numeric" }) : "";

  if (data.length === 1) {
    const row = data[0];
    const barData = [
      { metric: "Completed",     value: Number(row.completed     || 0), color: C.completed },
      { metric: "No-Shows",      value: Number(row.no_shows      || 0), color: C.no_show   },
      { metric: "Cancellations", value: Number(row.cancellations || 0), color: C.cancelled },
    ];
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={barData} margin={{ top: 6, right: 16, left: 0, bottom: 8 }} barCategoryGap="40%">
          <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
          <XAxis dataKey="metric" tick={{ fill: "#666", fontSize: 10, fontFamily: "'Josefin Sans', sans-serif" }}
            tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#aaa", fontSize: 10 }} tickLine={false} axisLine={false} />
          <Tooltip content={<ChartTip />} />
          <Bar dataKey="value" name="Count" radius={[3, 3, 0, 0]} maxBarSize={64}>
            {barData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
        <defs>
          {[["comp", C.completed],["ns", C.no_show],["can", C.cancelled]].map(([id, color]) => (
            <linearGradient key={id} id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0}   />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" />
        <XAxis dataKey="appointment_date" tickFormatter={fmtDate}
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <YAxis tick={{ fill: "#aaa", fontSize: 10 }} />
        <Tooltip content={<ChartTip />} />
        <Legend iconType="circle" iconSize={7} />
        <Area type="monotone" dataKey="completed"     name="Completed"     stroke={C.completed} fill="url(#g-comp)" strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="no_shows"      name="No-Shows"      stroke={C.no_show}   fill="url(#g-ns)"   strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="cancellations" name="Cancellations" stroke={C.cancelled} fill="url(#g-can)"  strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Category bar chart ────────────────────────────────────────────────────────
function CategoryChart({ data }) {
  if (!data?.length) return <div className="empty-state">No category data.</div>;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
        <XAxis dataKey="category" angle={-40} textAnchor="end" interval={0} height={60}
          tick={{ fill: "#666", fontSize: 9 }} />
        <YAxis tick={{ fill: "#aaa", fontSize: 10 }} />
        <Tooltip content={<ChartTip />} />
        <Legend iconType="circle" iconSize={7} />
        <Bar dataKey="completed"    name="Completed"    stackId="a" fill={C.completed} radius={[0,0,0,0]} />
        <Bar dataKey="no_shows"     name="No-Shows"     stackId="a" fill={C.no_show}   radius={[0,0,0,0]} />
        <Bar dataKey="cancellations"name="Cancellations"stackId="a" fill={C.cancelled} radius={[2,2,0,0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Booking source bar chart ──────────────────────────────────────────────────
function BookingSourceChart({ data }) {
  if (!data?.length) return <div className="empty-state">No booking source data.</div>;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 6, right: 40, left: 80, bottom: 6 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" horizontal={false} />
        <XAxis type="number" tick={{ fill: "#aaa", fontSize: 10 }} />
        <YAxis type="category" dataKey="booking_source" width={75}
          tick={{ fill: "#666", fontSize: 9 }} />
        <Tooltip content={<ChartTip />} />
        <Bar dataKey="total"     name="Total"     fill={C.pink}      radius={[0,2,2,0]} />
        <Bar dataKey="completed" name="Completed" fill={C.completed} radius={[0,2,2,0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Cancellation reasons ──────────────────────────────────────────────────────
function CancellationReasons({ data }) {
  if (!data?.length) return <div className="empty-state">No cancellation data.</div>;
  const total = data.reduce((a, r) => a + Number(r.count), 0);
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr><th>Reason</th><th className="r">Count</th><th className="r">% of Cancels</th></tr>
        </thead>
        <tbody>
          {data.map((r, i) => (
            <tr key={i}>
              <td>{r.reason}</td>
              <td className="r">{num(r.count)}</td>
              <td className="r">{pct(Number(r.count) / total * 100)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Location dropdown selector ────────────────────────────────────────────────
function LocationDropdown({ locations, value, onChange }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
      <span style={{
        fontSize: 8, textTransform: "uppercase", letterSpacing: "0.15em",
        color: "#A37B88", fontFamily: "'Josefin Sans', sans-serif", fontWeight: 400,
        flexShrink: 0,
      }}>
        Location
      </span>
      <div style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          style={{
            appearance: "none",
            WebkitAppearance: "none",
            border: "1px solid #E8E7E4",
            borderRadius: 0,
            padding: "4px 32px 4px 10px",
            height: 28,
            fontFamily: "'Josefin Sans', sans-serif",
            fontSize: 11,
            fontWeight: 400,
            letterSpacing: "0.04em",
            color: "#111111",
            background: "#ffffff",
            cursor: "pointer",
            outline: "none",
            minWidth: 180,
            transition: "border-color 0.15s",
          }}
          onFocus={e => e.target.style.borderColor = "#A37B88"}
          onBlur={e  => e.target.style.borderColor = "#E8E7E4"}
        >
          <option value="all">All Locations</option>
          {locations.map(l => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        {/* Custom chevron */}
        <span style={{
          position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
          pointerEvents: "none", color: "#A37B88", fontSize: 9, lineHeight: 1,
        }}>
          ▾
        </span>
      </div>
    </div>
  );
}

// ── Provider performance table ────────────────────────────────────────────────
function ProviderTable({ data }) {
  const [loc, setLoc] = useState("all");
  if (!data?.length) return <div className="empty-state">No provider data.</div>;

  const locations = [...new Set(data.map(r => r.location))].sort();
  const filtered  = loc === "all" ? data : data.filter(r => r.location === loc);

  return (
    <>
      <LocationDropdown locations={locations} value={loc} onChange={setLoc} />
      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Location</th>
              <th>Provider</th>
              <th className="r">Total</th>
              <th className="r">Completed</th>
              <th className="r">No-Shows</th>
              <th className="r">Cancels</th>
              <th className="r">Rebook %</th>
              <th className="r">Avg Duration</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i}>
                <td>{r.location}</td>
                <td>{r.provider}</td>
                <td className="r">{num(r.total)}</td>
                <td className="r">{num(r.completed)}</td>
                <td className="r">{num(r.no_shows)}</td>
                <td className="r">{num(r.cancellations)}</td>
                <td className="r">{pct(r.rebooking_rate)}</td>
                <td className="r">{mins(r.avg_actual_duration)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Location summary table ────────────────────────────────────────────────────
function LocationSummaryTable({ data }) {
  if (!data?.length) return <div className="empty-state">No summary data.</div>;
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Location</th>
            <th className="r">Total</th>
            <th className="r">Completed</th>
            <th className="r">No-Shows</th>
            <th className="r">No-Show %</th>
            <th className="r">Cancels</th>
            <th className="r">Cancel %</th>
            <th className="r">Rebook %</th>
            <th className="r">New Guests</th>
            <th className="r">Unique Guests</th>
            <th className="r">Avg Duration</th>
            <th className="r">Late Check-in %</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r, i) => (
            <tr key={i}>
              <td>{r.location}</td>
              <td className="r">{num(r.total_appointments)}</td>
              <td className="r">{num(r.completed)}</td>
              <td className="r">{num(r.no_shows)}</td>
              <td className={`r ${Number(r.no_show_rate) > 10 ? "neg" : ""}`}>{pct(r.no_show_rate)}</td>
              <td className="r">{num(r.cancellations)}</td>
              <td className={`r ${Number(r.cancellation_rate) > 20 ? "neg" : ""}`}>{pct(r.cancellation_rate)}</td>
              <td className={`r ${Number(r.rebooking_rate) >= 40 ? "pos" : ""}`}>{pct(r.rebooking_rate)}</td>
              <td className="r">{num(r.new_guests)}</td>
              <td className="r">{num(r.unique_guests)}</td>
              <td className="r">{mins(r.avg_actual_duration)}</td>
              <td className="r">{pct(r.late_checkin_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Request type table ────────────────────────────────────────────────────────
function RequestTypeTable({ data }) {
  if (!data?.length) return <div className="empty-state">No request type data.</div>;
  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Request Type</th>
            <th className="r">Total</th>
            <th className="r">Completed</th>
            <th className="r">Completion %</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r, i) => (
            <tr key={i}>
              <td>{r.request_type}</td>
              <td className="r">{num(r.total)}</td>
              <td className="r">{num(r.completed)}</td>
              <td className="r">{pct(r.completion_rate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function AppointmentsDashboard({
  summary, byStatus, byCategory, byProvider,
  bySource, cancelReasons, dailyTrend, requestType,
}) {
  return (
    <>
      {/* KPI tiles */}
      <SummaryTiles data={summary} />

      {/* Row 1: Daily trend + Status donut */}
      <div className="chart-row">
        <div className="chart-box" style={{ flex: 2 }}>
          <div className="chart-title">Appointment Trend — Daily</div>
          <div className="chart-inner"><DailyTrend data={dailyTrend} /></div>
        </div>
        <div className="chart-box" style={{ flex: 1 }}>
          <div className="chart-title">Status Breakdown</div>
          <div className="chart-inner"><StatusDonut data={byStatus} /></div>
        </div>
      </div>

      {/* Row 2: Category + Booking source */}
      <div className="chart-row">
        <div className="chart-box">
          <div className="chart-title">Appointments by Service Category</div>
          <div className="chart-inner"><CategoryChart data={byCategory} /></div>
        </div>
        <div className="chart-box">
          <div className="chart-title">Appointments by Booking Source</div>
          <div className="chart-inner"><BookingSourceChart data={bySource} /></div>
        </div>
      </div>

      {/* Location summary table */}
      <div className="sec-hdr mt2">Location Summary</div>
      <LocationSummaryTable data={summary} />

      {/* Provider table */}
      <div className="sec-hdr mt2">Provider Performance</div>
      <ProviderTable data={byProvider} />

      {/* Cancellation reasons + Request type */}
      <div className="chart-row" style={{ marginTop: 24 }}>
        <div style={{ flex: 1 }}>
          <div className="sec-hdr">Cancellation Reasons</div>
          <CancellationReasons data={cancelReasons} />
        </div>
        <div style={{ flex: 1 }}>
          <div className="sec-hdr">Provider Request Type</div>
          <RequestTypeTable data={requestType} />
        </div>
      </div>
    </>
  );
}