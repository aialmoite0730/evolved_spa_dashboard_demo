import React from "react";
import { fmt } from "../utils/format";

const COLS = [
  { key: "location",              label: "Location",            type: "text" },
  { key: "cash_sales",            label: "Cash Sales",          type: "cur" },
  { key: "recognized_revenue",    label: "Recog. Rev",          type: "cur" },
  { key: "daily_need",            label: "Daily Need",          type: "cur" },
  { key: "cash_sales_excl_mbr",   label: "Sales excl. Mem.",    type: "cur" },
  { key: "asp",                   label: "ASP",                 type: "cur" },
  { key: "asp_excl_memberships",  label: "ASP excl. Mem.",      type: "cur" },
  { key: "appointment_count",     label: "Appts",               type: "num" },
  { key: "service_count",         label: "Services",            type: "num" },
  { key: "services_per_appt",     label: "Svc / Appt",          type: "dec" },
  { key: "new_client_count",      label: "New",                 type: "num" },
  { key: "existing_client_count", label: "Existing",            type: "num" },
  { key: "total_client_count",    label: "Total Clients",       type: "num" },
  { key: "closed_invoice_count",  label: "Closed Inv.",         type: "num" },
  { key: "no_shows",              label: "No-Shows",            type: "num" },
  { key: "cancellations",         label: "Cancels",             type: "num" },
];

const AVG_KEYS = new Set(["asp", "asp_excl_memberships", "daily_need", "services_per_appt"]);

function buildTotals(rows) {
  const t = { location: "Total" };
  COLS.slice(1).forEach(({ key, type }) => {
    const vals = rows.filter(r => r[key] != null && !isNaN(Number(r[key])));
    if (AVG_KEYS.has(key)) {
      t[key] = vals.length ? vals.reduce((a, r) => a + Number(r[key]), 0) / vals.length : null;
    } else {
      t[key] = vals.reduce((a, r) => a + (Number(r[key]) || 0), 0);
    }
  });
  return t;
}

function cell(val, type) {
  if (val == null || val === "") return "—";
  const n = Number(val);
  if (type === "cur") return fmt.currency(val);
  if (type === "num") return fmt.number(val);
  if (type === "dec") return isNaN(n) ? "—" : n.toFixed(2);
  return val;
}

export default function DailyKPITable({ data }) {
  if (!data?.length) return <div className="empty-state">No data for selected date / locations.</div>;

  const totals = buildTotals(data);

  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            {COLS.map(c => (
              <th key={c.key} className={c.type !== "text" ? "r" : ""}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={i}>
              {COLS.map(c => (
                <td key={c.key} className={c.type !== "text" ? "r" : ""}>
                  {cell(row[c.key], c.type)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            {COLS.map(c => (
              <td key={c.key}>
                {c.type === "text" ? "Total" : cell(totals[c.key], c.type)}
              </td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
