import React from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { fmt } from "../utils/format";

// Brand-aware palette: pinks, grays, earth tones
const COLORS = [
  "#A37B88", "#2E2E2E", "#c4a0ac", "#6b7280",
  "#8a6272", "#e8d8dc", "#4a4a4a", "#d4b8c0",
  "#9e8a6a", "#b5a9a9", "#7a6a6a",
];

const TooltipContent = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div style={{
      background: "#fff", border: "1px solid #E8E7E4",
      padding: "8px 12px", fontSize: 11,
      fontFamily: "'Josefin Sans', sans-serif",
    }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{d.item_category}</div>
      <div style={{ color: "#aaa" }}>Revenue: <span style={{ color: "#2E2E2E" }}>{fmt.currency(d.revenue)}</span></div>
      <div style={{ color: "#aaa" }}>Count: <span style={{ color: "#2E2E2E" }}>{fmt.number(d.count)}</span></div>
    </div>
  );
};

export default function CategoryBreakdown({ data }) {
  if (!data?.length) return <div className="empty-state">No category data.</div>;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie
          data={data}
          dataKey="revenue"
          nameKey="item_category"
          cx="50%" cy="50%"
          innerRadius={55}
          outerRadius={90}
          paddingAngle={2}
        >
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Pie>
        <Tooltip content={<TooltipContent />} />
        <Legend iconType="circle" iconSize={7}
          formatter={v => (
            <span style={{ fontSize: 9, fontFamily: "'Josefin Sans', sans-serif",
              letterSpacing: "0.08em", textTransform: "uppercase", color: "#2E2E2E" }}>
              {v}
            </span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
