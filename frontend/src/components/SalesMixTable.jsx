import React from "react";
import { fmt } from "../utils/format";

const MIX_COLS = [
  { key: "body_contouring",    label: "Body Cont." },
  { key: "facials",            label: "Facials" },
  { key: "filler",             label: "Filler" },
  { key: "laser_hair_removal", label: "Laser Hair" },
  { key: "memberships",        label: "Memberships" },
  { key: "neurotoxins",        label: "Neurotoxins" },
  { key: "other",              label: "Other" },
  { key: "other_injectables",  label: "Other Inject." },
  { key: "prf",                label: "PRF" },
  { key: "retail",             label: "Retail" },
  { key: "skin_rejuvenation",  label: "Skin Rejuv" },
];

function buildTotals(rows) {
  const t = { location: "Total" };
  MIX_COLS.forEach(c => {
    t[c.key] = rows.reduce((a, r) => a + (Number(r[c.key]) || 0), 0);
  });
  t.total = rows.reduce((a, r) => a + (Number(r.total) || 0), 0);
  return t;
}

export default function SalesMixTable({ data }) {
  if (!data?.length) return <div className="empty-state">No sales mix data.</div>;

  const totals = buildTotals(data);
  const grandTotal = totals.total || 1;

  return (
    <div className="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Location</th>
            {MIX_COLS.map(c => <th key={c.key} className="r">{c.label}</th>)}
            <th className="r">Total</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => {
            const rowTotal = MIX_COLS.reduce((a, c) => a + (Number(row[c.key]) || 0), 0);
            return (
              <tr key={i}>
                <td>{row.location}</td>
                {MIX_COLS.map(c => {
                  const v = Number(row[c.key]) || 0;
                  return (
                    <td key={c.key} className="r">
                      {v !== 0 ? fmt.currency(v) : "—"}
                    </td>
                  );
                })}
                <td className="r"><b>{fmt.currency(row.total || rowTotal)}</b></td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td>Total</td>
            {MIX_COLS.map(c => (
              <td key={c.key}>{totals[c.key] ? fmt.currency(totals[c.key]) : "—"}</td>
            ))}
            <td>{fmt.currency(totals.total)}</td>
          </tr>
          <tr style={{ background: "transparent" }}>
            <td style={{ fontWeight: 300, fontStyle: "italic", fontSize: 9, textAlign: "left" }}>% of Total</td>
            {MIX_COLS.map(c => {
              const pct = grandTotal ? ((totals[c.key] || 0) / grandTotal * 100) : 0;
              return (
                <td key={c.key} style={{ fontWeight: 300, fontSize: 9, textAlign: "right", color: "#aaa" }}>
                  {pct > 0 ? pct.toFixed(1) + "%" : "—"}
                </td>
              );
            })}
            <td style={{ fontWeight: 300, fontSize: 9, color: "#aaa" }}>100%</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
