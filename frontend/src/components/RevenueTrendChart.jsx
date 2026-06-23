import React from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell, ReferenceLine,
  ComposedChart, Line,
} from "recharts";
import { fmt } from "../utils/format";

// ── Shared tooltip ────────────────────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label, yType }) => {
  if (!active || !payload?.length) return null;
  const fmtVal = v =>
    yType === "pct" ? v.toFixed(1) + "%" : yType === "cur" ? fmt.currency(v) : fmt.number(v);
  return (
    <div style={{
      background: "#fff", border: "1px solid #E8E7E4",
      padding: "8px 12px", fontSize: 11,
      fontFamily: "'Josefin Sans', sans-serif",
      boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", gap: 8, marginTop: 2, alignItems: "center" }}>
          <span style={{
            width: 8, height: 8, borderRadius: "2px",
            background: p.fill || p.color,
            display: "inline-block", flexShrink: 0,
          }} />
          <span style={{ color: "#888" }}>{p.name}:</span>
          <span style={{ marginLeft: "auto", fontFamily: "monospace", fontWeight: 600 }}>
            {fmtVal(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

// ── Shared legend renderer ────────────────────────────────────────────────────
const LegendLabel = v => (
  <span style={{
    fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
    letterSpacing: "0.1em", textTransform: "uppercase", color: "#555",
  }}>
    {v}
  </span>
);

// ── Revenue & Appointments Trend (area) ───────────────────────────────────────
export function RevenueTrendChart({ data }) {
  if (!data?.length) return <div className="empty-state">No trend data.</div>;

  const fmtDate = d => {
    if (!d) return "";
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#A37B88" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#A37B88" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="apptGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#2E2E2E" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#2E2E2E" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" />
        <XAxis dataKey="sale_date" tickFormatter={fmtDate}
          tick={{ fill: "#aaa", fontSize: 10, fontFamily: "'Josefin Sans', sans-serif" }} />
        <YAxis yAxisId="left" tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <YAxis yAxisId="right" orientation="right"
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <Tooltip content={<ChartTooltip />} />
        <Legend iconType="square" iconSize={8} formatter={LegendLabel} />
        <Area yAxisId="left" type="monotone" dataKey="daily_revenue"
          name="Revenue" stroke="#A37B88" fill="url(#revGrad)" strokeWidth={2} dot={false} />
        <Area yAxisId="right" type="monotone" dataKey="appointments"
          name="Appointments" stroke="#2E2E2E" fill="url(#apptGrad)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Color helpers ─────────────────────────────────────────────────────────────
// Primary bar color (with target-aware coloring)
function primaryColor(v, target) {
  if (!target) return "#A37B88";
  const n = Number(v);
  if (n >= target)        return "#1a5c34";
  if (n >= target * 0.85) return "#7c3a00";
  return "#7f1d1d";
}

// Secondary bar (budget / daily need) — always a soft neutral
const SECONDARY_COLOR = "#C8C4BE";  // warm light gray

// ── Grouped Bar chart ─────────────────────────────────────────────────────────
// Props:
//   data            – array of row objects
//   xKey            – field for x-axis labels
//   yKey            – primary bar field
//   label           – primary bar legend label
//   yType           – "cur" | "pct" | "num"
//   target          – optional numeric target (colors primary bars)
//   secondaryKey    – optional field for secondary (budget / daily need) bars
//   secondaryLabel  – legend label for secondary bars
// lines = [{ dataKey, name, color, dashed? }] — optional overlay lines on bar chart
export function LocationBarChart({
  data, xKey, yKey, label,
  yType = "cur", target,
  secondaryKey, secondaryLabel,
  lines = [],
}) {
  if (!data?.length) return <div className="empty-state">No data.</div>;

  const hasSecondary = Boolean(secondaryKey);
  const hasLines     = lines.length > 0;

  const legendItems = [];
  if (hasSecondary) {
    legendItems.push({ color: SECONDARY_COLOR, name: secondaryLabel || "Budget / Target", type: "square" });
  }
  if (target) {
    legendItems.push({ color: "#1a5c34", name: `≥ ${yType === "pct" ? target + "%" : fmt.currency(target)} (on target)`, type: "square" });
    legendItems.push({ color: "#7c3a00", name: `≥ ${yType === "pct" ? (target * 0.85).toFixed(0) + "%" : fmt.currency(target * 0.85)} (near target)`, type: "square" });
    legendItems.push({ color: "#7f1d1d", name: "Below target", type: "square" });
  } else {
    legendItems.push({ color: "#A37B88", name: label, type: "square" });
  }
  lines.forEach(l => legendItems.push({ color: l.color, name: l.name, type: "line", dashed: l.dashed }));

  const Chart = hasLines ? ComposedChart : BarChart;

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Custom legend */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "10px 16px",
        padding: "0 8px 6px", justifyContent: "center",
      }}>
        {legendItems.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            {item.type === "line" ? (
              <svg width="18" height="10" style={{ flexShrink: 0 }}>
                <line
                  x1="0" y1="5" x2="18" y2="5"
                  stroke={item.color} strokeWidth="2"
                  strokeDasharray={item.dashed ? "4 3" : "0"}
                />
              </svg>
            ) : (
              <span style={{
                width: 10, height: 10, borderRadius: 2,
                background: item.color, display: "inline-block", flexShrink: 0,
              }} />
            )}
            <span style={{
              fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
              letterSpacing: "0.1em", textTransform: "uppercase", color: "#555",
            }}>
              {item.name}
            </span>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <Chart
            data={data}
            margin={{ top: 4, right: 16, left: 0, bottom: 60 }}
            barCategoryGap="25%"
            barGap={2}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
            <XAxis
              dataKey={xKey}
              tick={{ fill: "#666", fontSize: 9, fontFamily: "'Josefin Sans', sans-serif" }}
              angle={-45}
              textAnchor="end"
              interval={0}
              height={60}
            />
            <YAxis
              tickFormatter={v =>
                yType === "pct" ? v + "%" : yType === "cur" ? `$${(v / 1000).toFixed(0)}k` : v
              }
              tick={{ fill: "#aaa", fontSize: 10 }}
            />
            <Tooltip content={<ChartTooltip yType={yType} />} />

            {hasSecondary && (
              <Bar
                dataKey={secondaryKey}
                name={secondaryLabel}
                fill={SECONDARY_COLOR}
                radius={[2, 2, 0, 0]}
              />
            )}

            <Bar dataKey={yKey} name={label} radius={[2, 2, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={primaryColor(entry[yKey], target)} />
              ))}
            </Bar>

            {target && (
              <ReferenceLine
                y={target}
                stroke={yType === "pct" ? "#1a5c34" : "#A37B88"}
                strokeDasharray="4 3"
                strokeWidth={1}
              />
            )}

            {lines.map((l, i) => (
              <Line
                key={i}
                type="monotone"
                dataKey={l.dataKey}
                name={l.name}
                stroke={l.color}
                strokeWidth={2}
                strokeDasharray={l.dashed ? "5 4" : "0"}
                dot={{ r: 3, fill: l.color }}
                activeDot={{ r: 5 }}
                connectNulls
              />
            ))}
          </Chart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// ── MTD Performance Chart ─────────────────────────────────────────────────────
// Combo chart: daily revenue bars (left axis) + cumulative lines (right axis).
// Matches reference: dark gray bars, dark-brown MTD trendline, light-gray
// trending projection, gold goal line. Dual Y-axes ($M left, M right).
//
// API shape (from mtd.py /api/mtd-daily-trend):
//   { daily: [{day, daily_sales, cumulative_sales},...],
//     monthly_budget, trending (scalar month-end projection), days_in_month }
export function MTDPerformanceChart({ data }) {
  const daily       = data?.daily;
  const daysInMonth = data?.days_in_month || 30;
  const apiTrending = Number(data?.trending)       || 0;
  const apiBudget   = Number(data?.monthly_budget) || 0;

  if (!daily?.length) return <div className="empty-state">No MTD trend data.</div>;

  const hasBudget = apiBudget > 0;

  // Pace trending & goal as diagonals: value at day i = total * (i+1) / daysInMonth
  const enriched = daily.map((row, i) => ({
    day:            row.day,
    daily_revenue:  Number(row.daily_sales)      || 0,
    mtd_cumulative: Number(row.cumulative_sales) || 0,
    trending:       apiTrending ? (apiTrending / daysInMonth) * (i + 1) : null,
    goal_mtd:       hasBudget   ? (apiBudget   / daysInMonth) * (i + 1) : null,
  }));

  const fmtDate = d => {
    if (!d) return "";
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-US", { weekday: "short", month: "numeric", day: "numeric" });
  };

  // Left axis: $0.0M, $0.2M … (daily bar scale)
  const fmtLeft = v => {
    const n = Number(v);
    return `$${(n / 1_000_000).toFixed(1)}M`;
  };

  // Right axis: 0M, 5M, 10M … (cumulative line scale)
  const fmtRight = v => {
    const n = Number(v);
    return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(0)}M`
         : n >= 1_000     ? `${(n / 1_000).toFixed(0)}K`
         : `${n}`;
  };

  // Tooltip formatter — always show dollars
  const fmtDollar = v => {
    const n = Number(v);
    return n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M`
         : n >= 1_000     ? `$${(n / 1_000).toFixed(0)}K`
         : `$${n.toFixed(0)}`;
  };

  const MTDTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const byKey = Object.fromEntries(payload.map(p => [p.dataKey, p.value]));
    const rows = [
      { label: "Total Revenue",     val: byKey.daily_revenue,   color: "#4B4B4B" },
      { label: "MTD Trendline Cut", val: byKey.mtd_cumulative,  color: "#5a3a2e" },
      { label: "Trending",          val: byKey.trending,        color: "#9ca3af" },
      hasBudget && { label: "Goal MTD", val: byKey.goal_mtd,    color: "#c9a227" },
    ].filter(Boolean);
    return (
      <div style={{
        background: "#fff", border: "1px solid #E8E7E4",
        padding: "8px 12px", fontSize: 11,
        fontFamily: "'Josefin Sans', sans-serif",
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{fmtDate(label)}</div>
        {rows.map(r => r.val != null && (
          <div key={r.label} style={{ display: "flex", gap: 8, marginTop: 2, alignItems: "center" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: r.color, display: "inline-block", flexShrink: 0 }} />
            <span style={{ color: "#888" }}>{r.label}:</span>
            <span style={{ marginLeft: "auto", fontFamily: "monospace", fontWeight: 600 }}>{fmtDollar(r.val)}</span>
          </div>
        ))}
      </div>
    );
  };

  // Legend — circle dots for lines, square for bars (matching reference style)
  const legendItems = [
    { shape: "circle", color: "#4B4B4B", label: "Total Revenue" },
    { shape: "circle", color: "#5a3a2e", label: "Revenue MTD Trendline Cut" },
    { shape: "circle", color: "#9ca3af", label: "Trending (Projected MTD by Day)" },
    hasBudget && { shape: "circle", color: "#c9a227", label: "Goal MTD" },
  ].filter(Boolean);

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Legend */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "6px 14px",
        padding: "0 8px 8px", justifyContent: "flex-start",
      }}>
        {legendItems.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{
              width: 8, height: 8, borderRadius: "50%",
              background: item.color, display: "inline-block", flexShrink: 0,
            }} />
            <span style={{
              fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
              letterSpacing: "0.08em", textTransform: "uppercase", color: "#555",
            }}>
              {item.label}
            </span>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={enriched}
            margin={{ top: 8, right: 60, left: 0, bottom: 60 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
            <XAxis
              dataKey="day"
              tickFormatter={fmtDate}
              tick={{ fill: "#666", fontSize: 9, fontFamily: "'Josefin Sans', sans-serif" }}
              angle={-45}
              textAnchor="end"
              interval={0}
              height={60}
            />

            {/* Left axis — daily bar scale ($0.0M … $0.4M) */}
            <YAxis
              yAxisId="left"
              tickFormatter={fmtLeft}
              tick={{ fill: "#aaa", fontSize: 10 }}
              width={52}
            />

            {/* Right axis — cumulative line scale (0M … 10M) */}
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={fmtRight}
              tick={{ fill: "#aaa", fontSize: 10 }}
              width={40}
            />

            <Tooltip content={<MTDTooltip />} />

            {/* Dark gray bars — Total Revenue (left axis) */}
            <Bar
              yAxisId="left"
              dataKey="daily_revenue"
              name="Total Revenue"
              fill="#4B4B4B"
              radius={[2, 2, 0, 0]}
              opacity={0.9}
              maxBarSize={24}
            />

            {/* Dark brown line — MTD Trendline Cut (right axis) */}
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="mtd_cumulative"
              name="Revenue MTD Trendline Cut"
              stroke="#5a3a2e"
              strokeWidth={2}
              dot={false}
            />

            {/* Light gray line — Trending projection (right axis) */}
            <Line
              yAxisId="right"
              type="linear"
              dataKey="trending"
              name="Trending"
              stroke="#9ca3af"
              strokeWidth={1.5}
              dot={false}
              connectNulls
            />

            {/* Gold dashed line — Goal MTD (right axis) */}
            {hasBudget && (
              <Line
                yAxisId="right"
                type="linear"
                dataKey="goal_mtd"
                name="Goal MTD"
                stroke="#c9a227"
                strokeWidth={2}
                strokeDasharray="5 3"
                dot={false}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}


// ── MTD Revenue vs Budget by Location ────────────────────────────────────────
// Replicates the reference chart: grouped bars (Budget + MTD Sales) with three
// overlay lines (Budget Line dashed gray, Sales Line solid mauve, Trending dashed green).
//
// Props:
//   data – mtdSummary rows: [{ location, cash_sales, monthly_budget, trending }]
export function MTDLocationChart({ data }) {
  if (!data?.length) return <div className="empty-state">No MTD location data.</div>;

  const fmtCurK = v => {
    const n = Number(v);
    if (isNaN(n)) return "$0k";
    return n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
         : n >= 1_000     ? `$${Math.round(n / 1_000)}k`
         : `$${Math.round(n)}`;
  };

  const LocationTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    const order = ["monthly_budget", "cash_sales", "budget_line", "sales_line", "trending_line"];
    const meta = {
      monthly_budget: { label: "Budget",       color: "#C8C4BE" },
      cash_sales:     { label: "MTD Sales",    color: "#A37B88" },
      budget_line:    { label: "Budget Line",  color: "#aaa"    },
      sales_line:     { label: "Sales Line",   color: "#7a4f5a" },
      trending_line:  { label: "Trending",     color: "#3a7d44" },
    };
    const sorted = [...payload].sort(
      (a, b) => order.indexOf(a.dataKey) - order.indexOf(b.dataKey)
    );
    return (
      <div style={{
        background: "#fff", border: "1px solid #E8E7E4",
        padding: "8px 12px", fontSize: 11,
        fontFamily: "'Josefin Sans', sans-serif",
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
        {sorted.map(p => {
          const m = meta[p.dataKey];
          if (!m || p.value == null) return null;
          return (
            <div key={p.dataKey} style={{ display: "flex", gap: 8, marginTop: 2, alignItems: "center" }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: m.color, display: "inline-block", flexShrink: 0 }} />
              <span style={{ color: "#888" }}>{m.label}:</span>
              <span style={{ marginLeft: "auto", fontFamily: "monospace", fontWeight: 600 }}>{fmtCurK(p.value)}</span>
            </div>
          );
        })}
      </div>
    );
  };

  const enriched = data.map(row => ({
    location:       row.location,
    monthly_budget: Number(row.monthly_budget) || 0,
    cash_sales:     Number(row.cash_sales)     || 0,
    budget_line:    Number(row.monthly_budget) || 0,
    sales_line:     Number(row.cash_sales)     || 0,
    trending_line:  Number(row.trending)       || 0,
  }));

  const legendItems = [
    { type: "square", color: "#C8C4BE", name: "Budget" },
    { type: "square", color: "#A37B88", name: "MTD Sales" },
    { type: "line",   color: "#aaa",    name: "Budget Line",  dashed: true  },
    { type: "line",   color: "#7a4f5a", name: "Sales Line",   dashed: false },
    { type: "line",   color: "#3a7d44", name: "Trending",     dashed: true  },
  ];

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "8px 16px",
        padding: "0 8px 8px", justifyContent: "center",
      }}>
        {legendItems.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            {item.type === "line" ? (
              <svg width="20" height="10" style={{ flexShrink: 0 }}>
                <line x1="0" y1="5" x2="20" y2="5"
                  stroke={item.color} strokeWidth="2"
                  strokeDasharray={item.dashed ? "5 3" : "0"} />
              </svg>
            ) : (
              <span style={{
                width: 10, height: 10, borderRadius: 2,
                background: item.color, display: "inline-block", flexShrink: 0,
              }} />
            )}
            <span style={{
              fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
              letterSpacing: "0.1em", textTransform: "uppercase", color: "#555",
            }}>
              {item.name}
            </span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart
            data={enriched}
            margin={{ top: 8, right: 16, left: 0, bottom: 60 }}
            barCategoryGap="30%"
            barGap={2}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
            <XAxis
              dataKey="location"
              tick={{ fill: "#666", fontSize: 9, fontFamily: "'Josefin Sans', sans-serif" }}
              angle={-45}
              textAnchor="end"
              interval={0}
              height={60}
            />
            <YAxis
              tickFormatter={fmtCurK}
              tick={{ fill: "#aaa", fontSize: 10 }}
              width={50}
            />
            <Tooltip content={<LocationTooltip />} />

            <Bar dataKey="monthly_budget" name="Budget"    fill="#C8C4BE" radius={[2, 2, 0, 0]} opacity={0.9} />
            <Bar dataKey="cash_sales"     name="MTD Sales" fill="#A37B88" radius={[2, 2, 0, 0]} opacity={0.9} />

            <Line type="monotone" dataKey="budget_line"   name="Budget Line"
              stroke="#aaa"    strokeWidth={1.5} strokeDasharray="5 3"
              dot={{ r: 3, fill: "#aaa",    strokeWidth: 0 }} activeDot={{ r: 5 }} connectNulls />
            <Line type="monotone" dataKey="sales_line"    name="Sales Line"
              stroke="#7a4f5a" strokeWidth={2}
              dot={{ r: 3, fill: "#7a4f5a", strokeWidth: 0 }} activeDot={{ r: 5 }} connectNulls />
            <Line type="monotone" dataKey="trending_line" name="Trending"
              stroke="#3a7d44" strokeWidth={2} strokeDasharray="6 3"
              dot={{ r: 4, fill: "#3a7d44", strokeWidth: 0 }} activeDot={{ r: 6 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default RevenueTrendChart;