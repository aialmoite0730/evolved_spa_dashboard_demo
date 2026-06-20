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

// ── MTD Performance Chart (ComposedChart: daily bars + cumulative + budget pace + trending) ──
export function MTDPerformanceChart({ data }) {
  if (!data?.daily?.length) return <div className="empty-state">No trend data.</div>;

  const { daily, monthly_budget, days_in_month } = data;

  const firstDay  = daily[0].day;                                  // "2026-05-01"
  const [yr, mo]  = firstDay.split("-").map(Number);
  const dailyMap  = {};
  daily.forEach(d => { dailyMap[d.day] = d; });

  const lastRow          = daily[daily.length - 1];
  const lastDayNum       = parseInt(lastRow.day.split("-")[2], 10);
  const lastCumulative   = parseFloat(lastRow.cumulative_sales);
  const avgDaily         = lastDayNum > 0 ? lastCumulative / lastDayNum : 0;

  const chartData = Array.from({ length: days_in_month }, (_, i) => {
    const d       = i + 1;
    const dateStr = `${yr}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const actual  = dailyMap[dateStr];
    return {
      day:              d,
      daily_sales:      actual ? parseFloat(actual.daily_sales)      : null,
      cumulative_sales: actual ? parseFloat(actual.cumulative_sales)  : null,
      budget_pace:      parseFloat(((monthly_budget / days_in_month) * d).toFixed(2)),
      trend_projection: d >= lastDayNum
        ? parseFloat((lastCumulative + avgDaily * (d - lastDayNum)).toFixed(2))
        : null,
    };
  });

  const fmtK = v => v == null ? "" : `$${(v / 1000).toFixed(0)}k`;

  const legendItems = [
    { color: "#A37B88", name: "Daily Sales (bars)" },
    { color: "#A37B88", name: "MTD Cumulative", dashed: false, line: true },
    { color: "#C8C4BE", name: "Budget Pace", dashed: true,  line: true },
    { color: "#2E7D32", name: "Trending",     dashed: true,  line: true },
  ];

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 14px", padding: "0 8px 6px", justifyContent: "center" }}>
        {legendItems.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            {item.line ? (
              <svg width="18" height="8">
                <line x1="0" y1="4" x2="18" y2="4"
                  stroke={item.color} strokeWidth="2"
                  strokeDasharray={item.dashed ? "4 3" : "none"} />
              </svg>
            ) : (
              <span style={{ width: 10, height: 10, borderRadius: 2, background: item.color, display: "inline-block", opacity: 0.7 }} />
            )}
            <span style={{ fontSize: 9, fontFamily: "'Josefin Sans', sans-serif", letterSpacing: "0.1em", textTransform: "uppercase", color: "#555" }}>
              {item.name}
            </span>
          </div>
        ))}
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 4, right: 24, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
            <XAxis
              dataKey="day"
              tick={{ fill: "#aaa", fontSize: 10, fontFamily: "'Josefin Sans', sans-serif" }}
              tickFormatter={d => (d % 5 === 1 || d === days_in_month) ? d : ""}
            />
            <YAxis
              yAxisId="left"
              tickFormatter={fmtK}
              tick={{ fill: "#aaa", fontSize: 10 }}
              width={52}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              tickFormatter={fmtK}
              tick={{ fill: "#aaa", fontSize: 10 }}
              width={52}
            />
            <Tooltip
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                return (
                  <div style={{ background: "#fff", border: "1px solid #E8E7E4", padding: "8px 12px", fontSize: 11, fontFamily: "'Josefin Sans', sans-serif", boxShadow: "0 2px 8px rgba(0,0,0,0.08)" }}>
                    <div style={{ fontWeight: 700, marginBottom: 4 }}>Day {label}</div>
                    {payload.map(p => p.value != null && (
                      <div key={p.dataKey} style={{ display: "flex", gap: 8, marginTop: 2, alignItems: "center" }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: p.fill || p.stroke, display: "inline-block" }} />
                        <span style={{ color: "#888" }}>{p.name}:</span>
                        <span style={{ marginLeft: "auto", fontFamily: "monospace", fontWeight: 600 }}>{fmt.currency(p.value)}</span>
                      </div>
                    ))}
                  </div>
                );
              }}
            />
            <Bar yAxisId="left" dataKey="daily_sales" name="Daily Sales" fill="#A37B88" opacity={0.65} radius={[2, 2, 0, 0]} />
            <Line yAxisId="right" type="monotone" dataKey="cumulative_sales"  name="MTD Cumulative" stroke="#A37B88" strokeWidth={2}   dot={false} connectNulls={false} />
            <Line yAxisId="right" type="monotone" dataKey="budget_pace"       name="Budget Pace"    stroke="#C8C4BE" strokeWidth={1.5} dot={false} strokeDasharray="4 3" />
            <Line yAxisId="right" type="monotone" dataKey="trend_projection"  name="Trending"       stroke="#2E7D32" strokeWidth={1.5} dot={false} strokeDasharray="6 4" connectNulls={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default RevenueTrendChart;