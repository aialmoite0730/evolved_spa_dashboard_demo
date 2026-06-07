import React from "react";
import { fmt, gcls, vcls } from "../utils/format";

const COLS = [
  { key: "location",                label: "Location",               type: "text" },
  { key: "cash_sales",              label: "Cash Sales",             type: "cur" },
  { key: "avg_daily_sales",         label: "Avg Daily",              type: "cur" },
  { key: "trending",                label: "Trending",               type: "cur" },
  { key: "monthly_budget",          label: "Budget",                 type: "cur" },
  { key: "surplus_shortfall",       label: "Surplus / (Shortfall)",  type: "signed" },
  { key: "pct_to_goal_mtd",         label: "% to Goal",              type: "pct_goal" },
  { key: "pct_to_goal_total",       label: "% Trending",             type: "pct_goal" },
  { key: "current_week_revenue",    label: "Cur. Week",              type: "cur" },
  { key: "prior_week_revenue",      label: "Prior Week",             type: "cur" },
  { key: "prior_week_variance",     label: "WoW $",                  type: "signed" },
  { key: "prior_week_variance_pct", label: "WoW %",                  type: "spct" },
  { key: "pm_revenue",              label: "PM Rev",                 type: "cur" },
  { key: "pm_variance",             label: "PM Var $",               type: "signed" },
  { key: "pm_variance_pct",         label: "PM Var %",               type: "spct" },
  { key: "py_revenue",              label: "PY Rev",                 type: "cur" },
  { key: "py_variance",             label: "PY Var $",               type: "signed" },
  { key: "py_variance_pct",         label: "PY Var %",               type: "spct" },
  { key: "new_members",             label: "New Mem.",               type: "num" },
  { key: "non_members",             label: "Guests",                 type: "num" },
  { key: "membership_adoption",     label: "Mem. Adopt.",            type: "pct" },
];

const SUM_KEYS = new Set(["cash_sales","avg_daily_sales","monthly_budget",
  "current_week_revenue","prior_week_revenue","prior_week_variance",
  "pm_revenue","pm_variance","py_revenue","py_variance","new_members","non_members"]);
const AVG_KEYS = new Set(["pct_to_goal_mtd","pct_to_goal_total",
  "prior_week_variance_pct","pm_variance_pct","py_variance_pct","membership_adoption"]);

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
  // Recompute surplus/trending from sums
  if (t.cash_sales && t.monthly_budget) {
    t.surplus_shortfall  = t.cash_sales - t.monthly_budget;
    t.pct_to_goal_mtd    = (t.cash_sales / t.monthly_budget) * 100;
  }
  return t;
}

function cellVal(val, type) {
  if (val == null || val === "") return "—";
  const n = Number(val);
  if (isNaN(n) && type !== "text") return "—";
  switch (type) {
    case "cur":      return fmt.currency(val);
    case "signed":   return n < 0 ? `(${fmt.currency(Math.abs(n))})` : fmt.currency(n);
    case "pct":
    case "pct_goal": return n.toFixed(1) + "%";
    case "spct":     return (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
    case "num":      return fmt.number(val);
    default:         return val;
  }
}

function cellCls(val, type) {
  if (type === "signed" || type === "spct") return vcls(val);
  if (type === "pct_goal") return gcls(val);
  return "";
}

export default function MTDSummaryTable({ data }) {
  if (!data?.length) return <div className="empty-state">No MTD data available.</div>;

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
                {COLS.map(c => {
                  const cls = [c.type !== "text" ? "r" : "", cellCls(row[c.key], c.type)]
                    .filter(Boolean).join(" ");
                  return <td key={c.key} className={cls}>{cellVal(row[c.key], c.type)}</td>;
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              {COLS.map(c => {
                const cls = cellCls(totals[c.key], c.type);
                return (
                  <td key={c.key} className={cls || undefined}>
                    {c.type === "text" ? "Total" : cellVal(totals[c.key], c.type)}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="footnote">
        * Budget columns not yet connected — they will show "—" until a budgets data source is integrated.<br />
        ¹ WoW = current week vs same 7-day window prior week.<br />
        ² PM/PY variances compare same elapsed days in prior month / prior year.
      </p>
    </>
  );
}
