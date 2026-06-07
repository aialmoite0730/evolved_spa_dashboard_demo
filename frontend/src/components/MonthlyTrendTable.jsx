import React from "react";
import { fmt } from "../utils/format";

const COLS = [
  { key: "location",              label: "Location",                  type: "text" },
  { key: "recognized_revenue",    label: "Recognized Revenue",        type: "cur" },
  { key: "avg_daily_revenue",     label: "Avg Daily Revenue",         type: "cur" },
  { key: "trending",              label: "Trending",                  type: "cur" },
  { key: "cogs_est",              label: "COGS (est.)",               type: "cur" },
  { key: "payroll_costs_est",     label: "Payroll Costs (est.)¹",     type: "cur" },
  { key: "gross_margin",          label: "Gross Margin ($)",          type: "cur" },
  { key: "cogs_margin",           label: "COGS Margin (est.)",        type: "pct" },
  { key: "payroll_margin",        label: "Payroll Margin (est.)",     type: "pct" },
  { key: "gross_margin_pct",      label: "Gross Margin (%)",          type: "gm" },
  { key: "asp_excl_memberships",  label: "ASP (excl. Memberships)",   type: "cur" },
  { key: "appointment_count",     label: "Appointment Count",         type: "num" },
  { key: "new_client_count",      label: "New Client Count³",         type: "num" },
  { key: "existing_client_count", label: "Existing Client Count",     type: "num" },
  { key: "total_client_count",    label: "Total Clients",             type: "num" },
  { key: "rev_per_provider",      label: "Revenue per Provider",      type: "cur" },
  { key: "rev_per_esthetician",   label: "Revenue per Esthetician",   type: "cur" },
  { key: "provider_utilization",  label: "Provider Utilization",      type: "pct" },
  { key: "esthetician_utilization",label:"Esthetician Utilization",   type: "pct" },
  { key: "rebooking_rate",        label: "Rebooking Rate",            type: "pct" },
  { key: "review_count",          label: "Review Count",              type: "num" },
  { key: "avg_rating",            label: "Avg. Rating",               type: "rating" },
];

const AVG_KEYS = new Set(["cogs_margin","payroll_margin","gross_margin_pct","asp_excl_memberships",
  "rev_per_provider","rev_per_esthetician","provider_utilization","esthetician_utilization",
  "rebooking_rate","avg_rating"]);

function buildTotals(rows) {
  const t = { location: "Total" };
  COLS.slice(1).forEach(({ key }) => {
    const vals = rows.filter(r => r[key] != null && !isNaN(Number(r[key])));
    if (AVG_KEYS.has(key)) {
      t[key] = vals.length ? vals.reduce((a, r) => a + Number(r[key]), 0) / vals.length : null;
    } else {
      t[key] = vals.reduce((a, r) => a + (Number(r[key]) || 0), 0);
    }
  });
  return t;
}

function cellVal(val, type) {
  if (val == null || val === "") return "—";
  const n = Number(val);
  if (isNaN(n) && type !== "text") return "—";
  if (type === "cur") return fmt.currency(val);
  if (type === "pct" || type === "gm") return n.toFixed(1) + "%";
  if (type === "num") return fmt.number(val);
  if (type === "rating") {
    const stars = "★".repeat(Math.min(5, Math.round(n))) + "☆".repeat(Math.max(0, 5 - Math.round(n)));
    return `${stars} ${n.toFixed(2)}`;
  }
  return val;
}

function cellCls(type, val) {
  const base = type !== "text" ? "r" : "";
  if (type === "gm") {
    const n = Number(val);
    if (!isNaN(n)) return base + (n >= 55 ? " pos" : n >= 45 ? "" : " neg");
  }
  return base;
}

export default function MonthlyTrendTable({ data }) {
  if (!data?.length) return <div className="empty-state">No monthly trend data.</div>;

  const totals = buildTotals(data);

  return (
    <>
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
                  <td key={c.key} className={cellCls(c.type, row[c.key])}>
                    {cellVal(row[c.key], c.type)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              {COLS.map(c => (
                <td key={c.key} className={cellCls(c.type, totals[c.key]) || undefined}>
                  {c.type === "text" ? "Total" : cellVal(totals[c.key], c.type)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="footnote">
        ASP = Cash Sales / Guest Count<br />
        ¹ Assumes additional 12% of Gross Payroll Costs attributable to Payroll Taxes, Benefits, and Processing Fees<br />
        ² Total includes impact of medical supply (COGS) and incurred costs attributable to month and performance bonuses<br />
        ³ New Client Count limited by Zenoti reporting (defined as First Visit = 2nd Closed Invoice by Guest).
      </p>
    </>
  );
}
