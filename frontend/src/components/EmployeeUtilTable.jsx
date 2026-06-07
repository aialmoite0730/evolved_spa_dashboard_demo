import React, { useState } from "react";
import RoleToggle from "./RoleToggle";

// uc() = utilization cell class: ≥75 hi, ≥60 md, <60 lo
function uc(v) {
  if (v == null || isNaN(Number(v))) return "";
  const n = Number(v);
  return n >= 75 ? "c-hi" : n >= 60 ? "c-md" : "c-lo";
}

function pct(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toFixed(1) + "%";
}

export default function EmployeeUtilTable({ data = [] }) {
  const [roleFilter, setRoleFilter] = useState("all");

  if (!data.length) {
    return (
      <div className="empty-state">
        Employee utilization requires Zenoti scheduling integration (employee_schedule table).
      </div>
    );
  }

  const filtered = roleFilter === "all"
    ? data
    : data.filter(r => r.role === roleFilter);

  // Detect how many daily columns exist (d1, d2, ... up to d31)
  const maxDay = Object.keys(data[0] || {})
    .filter(k => /^d\d+$/.test(k))
    .map(k => parseInt(k.slice(1), 10))
    .reduce((a, b) => Math.max(a, b), 0);

  const dayCols = Array.from({ length: maxDay }, (_, i) => `d${i + 1}`);

  return (
    <>
      <div className="sec-hdr mt3" style={{ flexWrap: "wrap", gap: 8 }}>
        <span>Utilization by Employee — MTD</span>

        {/* Replaced .pills buttons with the shared segmented control */}
        <RoleToggle value={roleFilter} onChange={setRoleFilter} />

        <div className="legend">
          <span className="leg lo">Under-Utilized &lt; 60%</span>
          <span className="leg md">Average 60–74.9%</span>
          <span className="leg hi">Highly-Utilized ≥ 75%</span>
        </div>
      </div>

      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Center</th>
              <th>Role</th>
              <th>Employee</th>
              {dayCols.map((_, i) => (
                <th key={i} className="r">Day {i + 1}</th>
              ))}
              <th className="r">MTD Total</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row, i) => (
              <tr key={i}>
                <td>{row.center}</td>
                <td>{row.role}</td>
                <td>{row.name}</td>
                {dayCols.map(col => (
                  <td key={col} className={`r ${uc(row[col])}`}>
                    {pct(row[col])}
                  </td>
                ))}
                <td className={`r ${uc(row.tot)}`}>
                  <b>{pct(row.tot)}</b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}