import React, { useState } from "react";
import { fmt } from "../utils/format";
import RoleToggle from "./RoleToggle";

// rc() = rev/hr cell class
// Provider: ≥550 hi, ≥450 md, else lo
// Esti:     ≥175 hi, ≥125 md, else lo
function rc(v, isEsti) {
  if (v == null || isNaN(Number(v))) return "";
  const n = Number(v);
  if (isEsti) return n >= 175 ? "c-hi" : n >= 125 ? "c-md" : "c-lo";
  return n >= 550 ? "c-hi" : n >= 450 ? "c-md" : "c-lo";
}

function cur(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return fmt.currency(Math.round(Number(v)));
}

export default function EmployeeRphTable({ data = [] }) {
  const [roleFilter, setRoleFilter] = useState("all");

  if (!data.length) {
    return (
      <div className="empty-state">
        Employee Rev/Hr requires Zenoti scheduling integration (employee_schedule table).
      </div>
    );
  }

  const filtered = roleFilter === "all"
    ? data
    : data.filter(r => r.role === roleFilter);

  const maxDay = Object.keys(data[0] || {})
    .filter(k => /^d\d+$/.test(k))
    .map(k => parseInt(k.slice(1), 10))
    .reduce((a, b) => Math.max(a, b), 0);

  const dayCols = Array.from({ length: maxDay }, (_, i) => `d${i + 1}`);

  return (
    <>
      <div className="sec-hdr mt3" style={{ flexWrap: "wrap", gap: 8 }}>
        <span>Revenue per Utilized Hour — MTD</span>

        {/* Replaced .pills buttons with the shared segmented control */}
        <RoleToggle value={roleFilter} onChange={setRoleFilter} />

        <div className="legend">
          <span className="leg lo">Under-Performing</span>
          <span className="leg md">Average</span>
          <span className="leg hi">High-Performing</span>
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
            {filtered.map((row, i) => {
              const isEsti = row.role === "Esthetician";
              return (
                <tr key={i}>
                  <td>{row.center}</td>
                  <td>{row.role}</td>
                  <td>{row.name}</td>
                  {dayCols.map(col => (
                    <td key={col} className={`r ${rc(row[col], isEsti)}`}>
                      {cur(row[col])}
                    </td>
                  ))}
                  <td className={`r ${rc(row.tot, isEsti)}`}>
                    <b>{cur(row.tot)}</b>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}