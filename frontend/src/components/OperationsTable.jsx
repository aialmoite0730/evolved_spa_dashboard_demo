import React from "react";
import { fmt, ucls, rcls, vcls } from "../utils/format";

const COLS = [
  { key: "location",                label: "Location",           type: "text" },
  { key: "recognized_revenue",      label: "Recog. Rev",         type: "cur" },
  { key: "avg_daily_revenue",       label: "Avg Daily",          type: "cur" },
  { key: "trending",                label: "Trending",           type: "cur" },
  { key: "cogs_pct",                label: "COGS %",             type: "pct" },
  { key: "payroll_pct",             label: "Payroll %",          type: "pct" },
  { key: "gross_margin_pct",        label: "Gross Margin %",     type: "gm" },
  { key: "asp",                     label: "ASP",                type: "cur" },
  { key: "asp_excl_memberships",    label: "ASP excl. Mem.",     type: "cur" },
  { key: "appointment_count",       label: "Appts",              type: "num" },
  { key: "new_client_count",        label: "New",                type: "num" },
  { key: "existing_client_count",   label: "Existing",           type: "num" },
  { key: "rev_per_provider",        label: "Rev / Hr (Prov)",    type: "rph_prov" },
  { key: "rev_per_esthetician",     label: "Rev / Hr (Esti)",    type: "rph_esti" },
  { key: "provider_utilization",    label: "Prov Util %",        type: "util" },
  { key: "esthetician_utilization", label: "Esti Util %",        type: "util" },
  { key: "rebooking_rate",          label: "Rebook %",           type: "pct" },
  { key: "review_count",            label: "Reviews",            type: "num" },
  { key: "avg_rating",              label: "Rating",             type: "rating" },
];

const AVG_KEYS = new Set(["asp","asp_excl_memberships","rev_per_provider","rev_per_esthetician",
  "provider_utilization","esthetician_utilization","rebooking_rate",
  "cogs_pct","payroll_pct","gross_margin_pct","avg_rating"]);

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
  if (type === "cur" || type === "rph_prov" || type === "rph_esti") return fmt.currency(val);
  if (type === "pct" || type === "util" || type === "gm") return n.toFixed(1) + "%";
  if (type === "num") return fmt.number(val);
  if (type === "rating") return `★ ${n.toFixed(1)}`;
  return val;
}

function cellCls(key, val, type) {
  const base = type !== "text" ? "r" : "";
  let extra = "";
  if (type === "util") extra = ucls(val);
  else if (type === "rph_prov") extra = rcls(val, false);
  else if (type === "rph_esti") extra = rcls(val, true);
  else if (type === "gm") {
    const n = Number(val);
    extra = !isNaN(n) ? (n >= 55 ? "pos" : n >= 45 ? "" : "neg") : "";
  }
  return [base, extra].filter(Boolean).join(" ");
}

export default function OperationsTable({ data }) {
  if (!data?.length) return <div className="empty-state">No operations data available.</div>;

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
                  <td key={c.key} className={cellCls(c.key, row[c.key], c.type)}>
                    {cellVal(row[c.key], c.type)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              {COLS.map(c => (
                <td key={c.key} className={cellCls(c.key, totals[c.key], c.type) || undefined}>
                  {c.type === "text" ? "Total" : cellVal(totals[c.key], c.type)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="footnote">
        COGS ≈ 20% | Payroll ≈ 22% gross + 12% burden (estimates).
        Utilization &amp; rebooking rate require Zenoti scheduling data not yet connected.<br />
        High Performer thresholds: Provider Rev/Hr ≥ $550, Esti Rev/Hr ≥ $175, Utilization ≥ 75%.
      </p>
    </>
  );
}
