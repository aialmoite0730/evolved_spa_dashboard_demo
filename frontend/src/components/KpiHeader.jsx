import React from "react";

function fmtCur(n) {
  if (n == null || isNaN(Number(n))) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(Number(n));
}
function fmtPct(n, d = 1) {
  if (n == null || isNaN(Number(n))) return "—";
  return Number(n).toFixed(d) + "%";
}
function fmtNum(n) {
  if (n == null || isNaN(Number(n))) return "—";
  return new Intl.NumberFormat("en-US").format(Math.round(Number(n)));
}
function sign(n) { return Number(n) >= 0 ? "+" : ""; }

function Tile({ label, val, sub, subClass, tileClass, placeholder }) {
  return (
    <div className={`tile${tileClass ? " " + tileClass : ""}${placeholder ? " tile-placeholder" : ""}`}>
      <div className="tile-lbl">{label}</div>
      <div className="tile-val">{val}</div>
      {sub && <div className={`tile-sub${subClass ? " " + subClass : ""}`}>{sub}</div>}
    </div>
  );
}

export default function KpiHeader({ data }) {
  if (!data) {
    return (
      <div className="tiles">
        <div className="tiles-row" style={{ alignItems: "center", paddingLeft: 24 }}>
          <span style={{ fontSize: 10, color: "#aaa", fontWeight: 300, letterSpacing: "0.1em", textTransform: "uppercase" }}>
            Loading KPIs…
          </span>
        </div>
      </div>
    );
  }

  // Compute trending = avg_daily * days in month
  const now = new Date();
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const trending = data.avg_daily_revenue
    ? Number(data.avg_daily_revenue) * daysInMonth
    : null;

  const yoyN    = Number(data.same_store_yoy);
  const yoyGood = !isNaN(yoyN) && yoyN >= 0;
  const trendingN = Number(trending);
  const budgetN   = Number(data.monthly_budget);
  const varToGoal = (!isNaN(trendingN) && !isNaN(budgetN) && data.monthly_budget)
    ? trendingN - budgetN : null;

  const pctTrending = (!isNaN(trendingN) && !isNaN(budgetN) && budgetN)
    ? (trendingN / budgetN * 100) : null;

  // MTD vs budget
  const mtdN  = Number(data.mtd_revenue);
  const mtdPct = (!isNaN(mtdN) && !isNaN(budgetN) && budgetN)
    ? (mtdN / budgetN * 100) : null;
  const mtdBad = mtdPct != null && mtdPct < 90;

  const provUtil = Number(data.provider_utilization);
  const estiUtil = Number(data.esthetician_utilization);
  const provRev  = Number(data.rev_per_provider);
  const estiRev  = Number(data.rev_per_esthetician);
  const gm       = Number(data.gross_margin_pct);

  return (
    <div className="tiles">
      {/* ── Row 1: Revenue & Client Acquisition ── */}
      <div className="tiles-row">
        <Tile
          label="MTD Revenue"
          val={fmtCur(data.mtd_revenue)}
          sub={mtdPct != null
            ? `${sign(mtdPct - 100)}${(mtdPct - 100).toFixed(1)}% vs budget`
            : data.py_revenue ? `vs ${fmtCur(data.py_revenue)} PY` : undefined}
          subClass={mtdBad ? "neg" : undefined}
          tileClass={mtdBad ? "bad" : undefined}
        />
        <Tile
          label="Trending"
          val={fmtCur(trending)}
          sub={pctTrending != null
            ? `${sign(pctTrending - 100)}${(pctTrending - 100).toFixed(1)}% vs goal · ${fmtPct(pctTrending, 1)}`
            : "full-month projection"}
          subClass={pctTrending != null && pctTrending < 100 ? "neg" : undefined}
          tileClass={pctTrending != null && pctTrending < 90 ? "bad" : undefined}
        />
        <Tile
          label="Var. to Goal"
          val={varToGoal != null ? (varToGoal < 0 ? `(${fmtCur(Math.abs(varToGoal))})` : fmtCur(varToGoal)) : "—"}
          sub={pctTrending != null ? `${fmtPct(pctTrending, 1)} · trending` : undefined}
          subClass={varToGoal != null && varToGoal < 0 ? "neg" : "pos"}
          tileClass={varToGoal != null && varToGoal < 0 ? "bad" : undefined}
        />
        <Tile
          label="Same-Store YoY"
          val={data.same_store_yoy != null ? `${sign(yoyN)}${fmtPct(data.same_store_yoy)}` : "—"}
          sub={data.py_revenue ? `vs ${fmtCur(data.py_revenue)} PY` : undefined}
          subClass={yoyGood ? "pos" : "neg"}
          tileClass={yoyGood ? "good" : "bad"}
        />
        <Tile
          label="Yesterday Revenue"
          val={fmtCur(data.yesterday_revenue)}
          sub={data.yesterday_clients != null ? `${fmtNum(data.yesterday_clients)} clients` : undefined}
        />
        <Tile
          label="Total Customer Count"
          val={fmtNum(data.total_client_count)}
          sub={data.yesterday_clients != null
            ? `${fmtNum(data.yesterday_clients)} yesterday · MTD unique clients`
            : "MTD unique clients"}
        />
        <Tile
          label="New Customer Count"
          val={fmtNum(data.new_client_count)}
          sub="MTD new clients"
        />
        <Tile
          label="Existing Customer Count"
          val={fmtNum(data.existing_client_count)}
          sub="MTD returning"
        />
        <Tile label="MTD Ad Spend"    val="—" sub="connect ad platform" placeholder />
        <Tile label="Blended CAC"     val="—" sub="ad spend ÷ new clients" placeholder />
      </div>

      {/* ── Row 2: Performance & Engagement ── */}
      <div className="tiles-row">
        <Tile
          label="Blended ASP"
          val={fmtCur(data.blended_asp)}
          sub="excl. memberships"
        />
        <Tile label="ASP — New Clients"      val="—" sub="requires segmented Zenoti data" placeholder />
        <Tile label="ASP — Existing Clients" val="—" sub="requires segmented Zenoti data" placeholder />
        <Tile
          label="Prebook Rate"
          val={data.rebooking_rate != null ? fmtPct(data.rebooking_rate) : "—"}
          sub="MTD rebooking avg"
        />
        <Tile
          label="Membership Adoption Rate"
          val={fmtPct(data.membership_adoption_rate)}
          sub={data.new_members != null
            ? `${fmtNum(data.new_members)} new mem. · ${fmtNum(data.member_count)} non-member guests`
            : undefined}
        />
        <Tile
          label="Provider Utilization"
          val={!isNaN(provUtil) ? fmtPct(provUtil) : "—"}
          sub="MTD avg · target ≥75%"
          subClass={!isNaN(provUtil) && provUtil >= 75 ? "pos" : undefined}
          tileClass={!isNaN(provUtil) ? (provUtil >= 75 ? "good" : provUtil >= 60 ? "warn" : "bad") : undefined}
        />
        <Tile
          label="Esti Utilization"
          val={!isNaN(estiUtil) ? fmtPct(estiUtil) : "—"}
          sub="MTD avg · target ≥75%"
          tileClass={!isNaN(estiUtil) ? (estiUtil >= 75 ? "good" : estiUtil >= 60 ? "warn" : "bad") : undefined}
        />
        <Tile
          label="Provider Rev / Util Hr"
          val={!isNaN(provRev) ? fmtCur(provRev) : "—"}
          sub="MTD avg · target ≥$550"
          subClass={!isNaN(provRev) && provRev >= 550 ? "pos" : undefined}
          tileClass={!isNaN(provRev) ? (provRev >= 550 ? "good" : "warn") : undefined}
        />
        <Tile
          label="Esti Rev / Util Hr"
          val={!isNaN(estiRev) ? fmtCur(estiRev) : "—"}
          sub="MTD avg · target ≥$175"
          subClass={!isNaN(estiRev) && estiRev >= 175 ? "pos" : undefined}
          tileClass={!isNaN(estiRev) ? (estiRev >= 175 ? "good" : "warn") : undefined}
        />
        <Tile
          label="Gross Margin"
          val={!isNaN(gm) ? fmtPct(gm) : "—"}
          sub="MTD avg · excl. bonuses"
          subClass={!isNaN(gm) && gm >= 50 ? "pos" : undefined}
          tileClass={!isNaN(gm) ? (gm >= 50 ? "good" : "warn") : undefined}
        />
      </div>
    </div>
  );
}
