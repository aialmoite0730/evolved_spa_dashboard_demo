import React from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell, ReferenceLine,
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
export function LocationBarChart({
  data, xKey, yKey, label,
  yType = "cur", target,
  secondaryKey, secondaryLabel,
}) {
  if (!data?.length) return <div className="empty-state">No data.</div>;

  const hasSecondary = Boolean(secondaryKey);

  // Build legend items manually so we can show target color info
  const legendItems = [];
  if (hasSecondary) {
    legendItems.push({ color: SECONDARY_COLOR, name: secondaryLabel || "Budget / Target" });
  }
  // For target-colored bars show one legend entry per tier
  if (target) {
    legendItems.push({ color: "#1a5c34", name: `≥ ${yType === "pct" ? target + "%" : fmt.currency(target)} (on target)` });
    legendItems.push({ color: "#7c3a00", name: `≥ ${yType === "pct" ? (target * 0.85).toFixed(0) + "%" : fmt.currency(target * 0.85)} (near target)` });
    legendItems.push({ color: "#7f1d1d", name: "Below target" });
  } else {
    legendItems.push({ color: "#A37B88", name: label });
  }

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column" }}>
      {/* Custom legend */}
      <div style={{
        display: "flex", flexWrap: "wrap", gap: "10px 16px",
        padding: "0 8px 6px", justifyContent: "center",
      }}>
        {legendItems.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{
              width: 10, height: 10, borderRadius: 2,
              background: item.color, display: "inline-block", flexShrink: 0,
            }} />
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
          <BarChart
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

            {/* Secondary bar (budget / daily need) — rendered first so it sits behind */}
            {hasSecondary && (
              <Bar
                dataKey={secondaryKey}
                name={secondaryLabel}
                fill={SECONDARY_COLOR}
                radius={[2, 2, 0, 0]}
              />
            )}

            {/* Primary bar */}
            <Bar dataKey={yKey} name={label} radius={[2, 2, 0, 0]}>
              {data.map((entry, i) => (
                <Cell key={i} fill={primaryColor(entry[yKey], target)} />
              ))}
            </Bar>

            {/* Reference line for target */}
            {target && (
              <ReferenceLine
                y={target}
                stroke={yType === "pct" ? "#1a5c34" : "#A37B88"}
                strokeDasharray="4 3"
                strokeWidth={1}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default RevenueTrendChart;