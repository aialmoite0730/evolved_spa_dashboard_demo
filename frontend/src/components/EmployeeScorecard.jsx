import React, { useState } from "react";
import { fmt } from "../utils/format";
import RoleToggle from "./RoleToggle";

// Performance tier logic:
// Provider: High = util ≥75% AND rev/hr ≥$550 | Esti: High = util ≥75% AND rev/hr ≥$175
function getTier(role, util, rph) {
  if (util == null || rph == null) return "lo";
  const u = Number(util), r = Number(rph);
  const isEsti = role === "Esthetician";
  if (u >= 75 && r >= (isEsti ? 175 : 550)) return "hi";
  if (u >= 60 && r >= (isEsti ? 125 : 450)) return "md";
  return "lo";
}

function utilCls(util) {
  if (util == null) return "";
  const n = Number(util);
  return n >= 75 ? "g" : n >= 60 ? "w" : "b";
}

function rphCls(role, rph) {
  if (rph == null) return "";
  const n = Number(rph);
  const isEsti = role === "Esthetician";
  return n >= (isEsti ? 175 : 550) ? "g" : n >= (isEsti ? 125 : 450) ? "w" : "b";
}

function pct(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return Number(v).toFixed(1) + "%";
}
function cur(v) {
  if (v == null || isNaN(Number(v))) return "—";
  return fmt.currency(Math.round(Number(v)));
}

const TIER_LABELS = { hi: "High Performer", md: "Average", lo: "Needs Focus" };

export default function EmployeeScorecard({ data = [] }) {
  const [roleFilter, setRoleFilter] = useState("all");

  const filtered = (roleFilter === "all"
    ? data
    : data.filter(r => r.role === roleFilter)
  ).map((r, idx) => ({ ...r, _rank: idx + 1, _tier: getTier(r.role, r.utilization, r.rev_per_hr) }))
   .sort((a, b) => (Number(b.total_revenue) || 0) - (Number(a.total_revenue) || 0))
   .map((r, idx) => ({ ...r, _rank: idx + 1 }));

  return (
    <>
      <div className="sec-hdr" style={{ flexWrap: "wrap", gap: 10 }}>
        <span>Employee Scorecard — MTD Leaderboard</span>

        {/* Replaced .pills buttons with the shared segmented control */}
        <RoleToggle value={roleFilter} onChange={setRoleFilter} />
      </div>

      <div className="sc-legend">
        <div className="sc-legend-item">
          <span className="tier-badge t-hi">High Performer</span>
          Providers: Util ≥ 75% &amp; Rev/Hr ≥ $550 &nbsp;·&nbsp; Estheticians: Util ≥ 75% &amp; Rev/Hr ≥ $175
        </div>
        <div className="sc-legend-item">
          <span className="tier-badge t-md">Average</span>
          Within expected ranges
        </div>
        <div className="sc-legend-item">
          <span className="tier-badge t-lo">Needs Focus</span>
          Below performance thresholds
        </div>
      </div>

      {!filtered.length ? (
        <div className="empty-state">
          Employee scorecard requires Zenoti scheduling integration (employee_schedule table).
        </div>
      ) : (
        <div className="sc-grid">
          {filtered.map((row, i) => {
            const tier   = row._tier;
            const rank   = row._rank;
            const isEsti = row.role === "Esthetician";
            const util   = Number(row.utilization);
            const rph    = Number(row.rev_per_hr);
            const utilBarW = Math.min(100, util || 0);
            const rphTarget = isEsti ? 175 : 550;
            const rphBarW = Math.min(100, rph ? (rph / rphTarget) * 100 : 0);

            return (
              <div key={i} className={`sc-card t-${tier}`}>
                <div className={`sc-rank${rank <= 3 ? ` r${rank}` : ""}`}>
                  {rank}
                </div>
                <div className="sc-role">
                  <span className={`tier-badge t-${tier}`}>{TIER_LABELS[tier]}</span>
                </div>
                <div className="sc-name">{row.name}</div>
                <div className="sc-loc">{row.center}</div>
                <div style={{
                  fontSize: 8, textTransform: "uppercase", letterSpacing: "0.14em",
                  color: "#A37B88", fontWeight: 300, marginBottom: 10,
                }}>
                  {row.role}
                </div>
                <div className="sc-metrics">
                  <div>
                    <div className="sc-m-lbl">Utilization</div>
                    <div className={`sc-m-val ${utilCls(row.utilization)}`}>{pct(row.utilization)}</div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{
                        width: `${utilBarW}%`,
                        background: util >= 75 ? "var(--g-text)" : util >= 60 ? "var(--a-text)" : "var(--r-text)",
                      }} />
                    </div>
                  </div>
                  <div>
                    <div className="sc-m-lbl">Rev / Hr</div>
                    <div className={`sc-m-val ${rphCls(row.role, row.rev_per_hr)}`}>{cur(row.rev_per_hr)}</div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{
                        width: `${rphBarW}%`,
                        background: rph >= rphTarget ? "var(--g-text)" : rph >= rphTarget * 0.8 ? "var(--a-text)" : "var(--r-text)",
                      }} />
                    </div>
                  </div>
                  <div>
                    <div className="sc-m-lbl">MTD Revenue</div>
                    <div className="sc-m-val">{cur(row.total_revenue)}</div>
                    <div style={{ fontSize: 9, color: "#aaa", marginTop: 3 }}>
                      {Number(row.booked_hours || 0).toFixed(1)} hrs booked
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}