import React from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell,
} from "recharts";
import { fmt } from "../utils/format";

// ── Shared tooltip ────────────────────────────────────────────────────────────
const ChartTooltip = ({ active, payload, label, yType }) => {
  if (!active || !payload?.length) return null;
  const fmtVal = v => yType === "pct" ? v.toFixed(1) + "%" : yType === "cur" ? fmt.currency(v) : fmt.number(v);
  return (
    <div style={{
      background: "#fff", border: "1px solid #E8E7E4",
      padding: "8px 12px", fontSize: 11,
      fontFamily: "'Josefin Sans', sans-serif",
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: "flex", gap: 8, marginTop: 2 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: p.color, display: "inline-block", marginTop: 3, flexShrink: 0 }} />
          <span style={{ color: "#aaa" }}>{p.name}:</span>
          <span style={{ marginLeft: "auto", fontFamily: "monospace" }}>{fmtVal(p.value)}</span>
        </div>
      ))}
    </div>
  );
};

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
        <YAxis yAxisId="left"  tickFormatter={v => `$${(v/1000).toFixed(0)}k`}
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <YAxis yAxisId="right" orientation="right"
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <Tooltip content={<ChartTooltip />} />
        <Legend iconType="circle" iconSize={7}
          formatter={v => <span style={{ fontSize: 10, fontFamily: "'Josefin Sans', sans-serif", letterSpacing: "0.08em", textTransform: "uppercase" }}>{v}</span>} />
        <Area yAxisId="left"  type="monotone" dataKey="daily_revenue"
          name="Revenue" stroke="#A37B88" fill="url(#revGrad)" strokeWidth={2} dot={false} />
        <Area yAxisId="right" type="monotone" dataKey="appointments"
          name="Appointments" stroke="#2E2E2E" fill="url(#apptGrad)" strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Generic Bar chart (used for util / rev-per-hr by location) ────────────────
export function LocationBarChart({ data, xKey, yKey, label, yType = "cur", target }) {
  if (!data?.length) return <div className="empty-state">No data.</div>;

  const barColor = v => {
    if (!target) return "#A37B88";
    const n = Number(v);
    if (n >= target)         return "#1a5c34";
    if (n >= target * 0.85)  return "#7c3a00";
    return "#7f1d1d";
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      {/* Updated margin to provide more space for labels */}
      <BarChart data={data} margin={{ top: 6, right: 16, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E8E7E4" vertical={false} />
        <XAxis dataKey={xKey}
          tick={{ fill: "#666", fontSize: 9, fontFamily: "'Josefin Sans', sans-serif" }} // Slightly darker tick color for readability
          // Updated rotation and spacing settings
          angle={-45} // Reduced rotation angle from -35 to -45 for potentially better fit
          textAnchor="end"
          interval={0} // Show all labels, Recharts will manage crowding
          height={60} // Explicitly define XAxis height to reserve space
        />
        <YAxis tickFormatter={v => yType === "pct" ? v + "%" : yType === "cur" ? `$${(v/1000).toFixed(0)}k` : v}
          tick={{ fill: "#aaa", fontSize: 10 }} />
        <Tooltip content={<ChartTooltip yType={yType} />} />
        <Bar dataKey={yKey} name={label} radius={[2, 2, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={barColor(entry[yKey])} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export default RevenueTrendChart;