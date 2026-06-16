import React, { useState, useEffect, useRef, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

// ── Formatters ────────────────────────────────────────────────────────────────
function currency(n) {
  if (n == null || isNaN(Number(n))) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(Number(n));
}
function pct(n, d = 1) {
  if (n == null || isNaN(Number(n))) return "N/A";
  return Number(n).toFixed(d) + "%";
}
function num(n) {
  if (n == null || isNaN(Number(n))) return "N/A";
  return new Intl.NumberFormat("en-US").format(Math.round(Number(n)));
}
function signedPct(n) {
  if (n == null || isNaN(Number(n))) return "N/A";
  const v = Number(n);
  return (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
}
function valOrMissing(n, formatter) {
  if (n == null || isNaN(Number(n))) return "MISSING";
  return formatter(n);
}

// ── Shared grounding rules ────────────────────────────────────────────────────
const GROUNDING_RULES =
  `RULES FOR THIS ANALYSIS:\n` +
  `- Only use the numbers given below. Do not invent, estimate, or assume any figure not explicitly provided.\n` +
  `- "MISSING" or "N/A" means the data point is genuinely unavailable — say so plainly or skip it. Do not guess a value.\n` +
  `- "0" or "0%" is a real, reported value — treat it as a true result, not as missing data.\n` +
  `- Do not speculate about causes unless explicitly stated in the data.\n` +
  `- When flagging an outlier, name the specific location and cite the specific number.\n` +
  `- Recommendations must be tied to a specific number cited earlier — no generic advice.\n` +
  `- Write in plain business English, short paragraphs, no bullet points, no markdown headers, no emojis.\n` +
  `- Max 110 words.\n`;

// ── Prompt builder ────────────────────────────────────────────────────────────
function buildPrompt(tab, dash, effectiveStart, effectiveEnd, viewMode) {
  const isDay = viewMode === "day";
  const dateRange = isDay
    ? `Single Day Snapshot: ${effectiveEnd}`
    : `Month-to-Date Period: ${effectiveStart} to ${effectiveEnd}`;

  const role =
    `You are a senior business analyst for Evolve Med Spa, a multi-location med spa chain. ` +
    `Analyze ONLY the real dashboard data provided below and write 4-6 specific, data-backed insights.\n\n`;

  const base = role + GROUNDING_RULES + `\n${dateRange}\n\n`;

  if (tab === "daily") {
    const h = dash.kpiHeader || {};
    const summary =
      `MTD Revenue: ${currency(h.mtd_revenue)}\n` +
      `Avg Daily Revenue (MTD): ${currency(h.avg_daily_revenue)}\n` +
      `Same-Store YoY: ${signedPct(h.same_store_yoy)}\n` +
      `Blended ASP (MTD, excl. memberships): ${currency(h.blended_asp)}\n` +
      `New Clients (MTD): ${num(h.new_client_count)}\n` +
      `Rebooking Rate (MTD): ${pct(h.rebooking_rate)}`;

    const rows = (dash.dailyKpis || []).map(r => {
      const target = Number(r.daily_need);
      const cash   = Number(r.cash_sales);
      const toGoal = !isNaN(target) && !isNaN(cash) ? cash - target : null;
      return (
        `  ${r.location}: Cash Sales ${currency(r.cash_sales)}, Daily Need ${currency(r.daily_need)}` +
        (toGoal != null ? ` (${toGoal >= 0 ? "+" : ""}${currency(toGoal)} vs need)` : "") +
        `, ASP ${currency(r.asp)}, Appointments ${num(r.appointment_count)}, ` +
        `New Clients ${num(r.new_client_count)}, No-Shows ${num(r.no_shows)}, Cancellations ${num(r.cancellations)}`
      );
    }).join("\n");

    const mix = (dash.dailyMix || []).length > 0
      ? (dash.dailyMix || []).map(r => {
          const inj = Number(r.filler || 0) + Number(r.neurotoxins || 0) + Number(r.other_injectables || 0) + Number(r.prf || 0);
          return `  ${r.location}: Total ${currency(r.total)} — Facials ${currency(r.facials)}, Injectables ${currency(inj)}, Memberships ${currency(r.memberships)}, Body Contouring ${currency(r.body_contouring)}, Laser Hair Removal ${currency(r.laser_hair_removal)}, Skin Rejuvenation ${currency(r.skin_rejuvenation)}, Retail ${currency(r.retail)}, Other ${currency(r.other)}`;
        }).join("\n")
      : "  No sales-mix data for this date.";

    return base +
      `Note: "Daily Need" is currently a placeholder equal to recognized revenue (no per-location daily budget is connected yet) — do not frame it as a true budget target in your analysis.\n\n` +
      `OVERALL MTD CONTEXT (for trend framing only — the focus is the single day below):\n${summary}\n\n` +
      `PRIOR-DAY KPIs BY LOCATION (this is the day being analyzed):\n${rows || "  No location data returned for this date."}\n\n` +
      `SALES MIX BY LOCATION (same day):\n${mix}`;
  }

  if (tab === "mtd") {
    const h = dash.kpiHeader || {};
    const header =
      `MTD Revenue (all selected locations): ${currency(h.mtd_revenue)}\n` +
      `Avg Daily Revenue (MTD): ${currency(h.avg_daily_revenue)}\n` +
      `Combined Monthly Budget: ${currency(h.monthly_budget)}\n` +
      `MTD Revenue vs Budget: ${h.mtd_revenue != null && h.monthly_budget
        ? `${signedPct((Number(h.mtd_revenue) / Number(h.monthly_budget) - 1) * 100)} (${currency(Number(h.mtd_revenue) - Number(h.monthly_budget))})`
        : "N/A"}\n` +
      `Same-Store YoY: ${signedPct(h.same_store_yoy)}\n` +
      `Blended ASP (excl. memberships): ${currency(h.blended_asp)}\n` +
      `New Clients: ${num(h.new_client_count)}, Existing Clients: ${num(h.existing_client_count)}, Members: ${num(h.member_count)}\n` +
      `Membership Adoption Rate: ${pct(h.membership_adoption_rate)}\n` +
      `Rebooking Rate: ${pct(h.rebooking_rate)}\n` +
      `Provider Utilization: ${pct(h.provider_utilization)} (target ≥75%)\n` +
      `Esthetician Utilization: ${pct(h.esthetician_utilization)} (target ≥75%)\n` +
      `Provider Revenue/Util Hr: ${currency(h.rev_per_provider)} (target ≥$550)\n` +
      `Esthetician Revenue/Util Hr: ${currency(h.rev_per_esthetician)} (target ≥$175)\n` +
      `Gross Margin: ${pct(h.gross_margin_pct)}\n` +
      `Last Month Total Revenue: ${currency(h.last_month_revenue)}`;

    const rows = (dash.mtdSummary || []).map(r => (
      `  ${r.location}: MTD Sales ${currency(r.cash_sales)} of ${currency(r.monthly_budget)} budget ` +
      `(${valOrMissing(r.pct_to_goal_mtd, v => pct(v))} to goal MTD, ` +
      `trending to ${valOrMissing(r.pct_to_goal_total, v => pct(v))} of goal). ` +
      `Surplus/Shortfall vs budget: ${r.surplus_shortfall != null ? currency(r.surplus_shortfall) : "MISSING"}. ` +
      `WoW: ${signedPct(r.prior_week_variance_pct)}, vs Prior Month: ${signedPct(r.pm_variance_pct)}, vs Prior Year: ${signedPct(r.py_variance_pct)}. ` +
      `Membership adoption: ${pct(r.membership_adoption)}.`
    )).join("\n");

    const mix = (dash.mtdMix || []).map(r => {
      const total = Number(r.total) || 0;
      if (!total) return `  ${r.location}: No sales-mix data.`;
      const inj = (Number(r.filler || 0) + Number(r.neurotoxins || 0) + Number(r.other_injectables || 0) + Number(r.prf || 0));
      return `  ${r.location}: Facials ${pct(Number(r.facials) / total * 100)}, Injectables ${pct(inj / total * 100)}, Memberships ${pct(Number(r.memberships || 0) / total * 100)}, Laser Hair Removal ${pct(Number(r.laser_hair_removal || 0) / total * 100)}, Body Contouring ${pct(Number(r.body_contouring || 0) / total * 100)}, Skin Rejuvenation ${pct(Number(r.skin_rejuvenation || 0) / total * 100)}`;
    }).join("\n");

    return base +
      `COMBINED KEY METRICS:\n${header}\n\n` +
      `PER-LOCATION BUDGET PACING:\n${rows || "  No location data returned."}\n\n` +
      `SALES MIX % BY LOCATION:\n${mix || "  No mix data returned."}`;
  }

  if (tab === "ops") {
    const rows = (dash.operations || []).map(r =>
      `  ${r.location}: Recognized Revenue ${currency(r.recognized_revenue)}, Trending ${currency(r.trending)}, ` +
      `ASP excl. memberships ${currency(r.asp_excl_memberships)}, Appointments ${num(r.appointment_count)}, ` +
      `New Clients ${num(r.new_client_count)}, Existing Clients ${num(r.existing_client_count)}, ` +
      `Provider Utilization ${valOrMissing(r.provider_utilization, pct)} (target ≥75%), ` +
      `Esthetician Utilization ${valOrMissing(r.esthetician_utilization, pct)} (target ≥75%), ` +
      `Provider Rev/Hr ${valOrMissing(r.rev_per_provider, currency)} (target ≥$550), ` +
      `Esthetician Rev/Hr ${valOrMissing(r.rev_per_esthetician, currency)} (target ≥$175), ` +
      `Gross Margin ${pct(r.gross_margin_pct)}, Rebooking Rate ${valOrMissing(r.rebooking_rate, pct)}`
    ).join("\n");

    return base +
      `TARGETS: Provider Utilization ≥75%, Esthetician Utilization ≥75%, Provider Rev/Hr ≥$550, Esthetician Rev/Hr ≥$175.\n\n` +
      `OPERATIONS BY LOCATION:\n${rows || "  No data returned."}\n\n` +
      `Focus on which locations are below target on utilization and/or rev/hr, by how much, and which locations are exceeding targets — cite the actual numbers.`;
  }

  if (tab === "appointments") {
    const rows = (dash.apptSummary || []).map(r => {
      const completionRate = (r.total_appointments && r.completed != null)
        ? (Number(r.completed) / Number(r.total_appointments) * 100) : null;
      return (
        `  ${r.location}: Total ${num(r.total_appointments)}, Completed ${num(r.completed)}` +
        (completionRate != null ? ` (${pct(completionRate)} completion)` : "") +
        `, No-Shows ${num(r.no_shows)} (${pct(r.no_show_rate)}), Cancellations ${num(r.cancellations)} (${pct(r.cancellation_rate)}), ` +
        `Rebooking Rate ${pct(r.rebooking_rate)}, New Guests ${num(r.new_guests)}, ` +
        `Avg Actual Duration ${valOrMissing(r.avg_actual_duration, v => Math.round(v) + " min")}, ` +
        `Late Check-In Rate ${valOrMissing(r.late_checkin_rate, pct)}`
      );
    }).join("\n");

    const cancelTop = (dash.apptCancelReasons || []).length > 0
      ? (dash.apptCancelReasons || []).map(r => `${r.reason}: ${num(r.count)}`).join(", ")
      : "No cancellations recorded";

    const catTop = (dash.apptByCategory || []).length > 0
      ? (dash.apptByCategory || []).slice(0, 8).map(r => `${r.category}: ${num(r.total)} total, ${pct(r.completion_rate)} completion`).join(" | ")
      : "No category data";

    return base +
      `APPOINTMENT SUMMARY BY LOCATION:\n${rows || "  No data returned."}\n\n` +
      `CANCELLATION REASONS:\n${cancelTop}\n\n` +
      `TOP SERVICE CATEGORIES:\n${catTop}\n\n` +
      `Focus on no-show/cancellation rates by location vs. the chain average implied above, the dominant cancellation reason, and rebooking-rate gaps.`;
  }

  if (tab === "scorecard") {
    const allProviders = (dash.employeeScorecard || []).filter(r => r.role === "Treatment Provider");
    const allEstis     = (dash.employeeScorecard || []).filter(r => r.role === "Esthetician");
    const fmtRow = r =>
      `  ${r.name} (${r.center}): Utilization ${pct(r.utilization)}, Rev/Hr ${currency(r.rev_per_hr)}, MTD Revenue ${currency(r.total_revenue)}, Booked Hours ${valOrMissing(r.booked_hours, num)}, Scheduled Hours ${valOrMissing(r.scheduled_hours, num)}`;

    return base +
      `TARGETS — Treatment Providers: Utilization ≥75%, Rev/Hr ≥$550. Estheticians: Utilization ≥75%, Rev/Hr ≥$175.\n\n` +
      `TREATMENT PROVIDERS (top ${Math.min(8, allProviders.length)} of ${allProviders.length}):\n${allProviders.slice(0, 8).map(fmtRow).join("\n") || "  No data."}\n\n` +
      `ESTHETICIANS (top ${Math.min(8, allEstis.length)} of ${allEstis.length}):\n${allEstis.slice(0, 8).map(fmtRow).join("\n") || "  No data."}\n\n` +
      `Focus on individuals significantly above or below the utilization/rev-per-hour targets, and name them specifically.`;
  }

  return base + "No data available for this view.";
}

// ── Date display helper ───────────────────────────────────────────────────────
function fmtShort(dateStr) {
  if (!dateStr) return "";
  return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function AiInsights({ tab, dash, effectiveStart, effectiveEnd }) {
  const [open,      setOpen]      = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [insight,   setInsight]   = useState("");
  const [error,     setError]     = useState("");

  const lastKeyRef       = useRef(null);
  const pendingKeyRef    = useRef(null);
  const mountedRef       = useRef(true);
  const abortRef         = useRef(null);
  const firstLoadDoneRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // ── Generate via backend ──────────────────────────────────────────────────
  const generate = useCallback(async () => {
    if (!mountedRef.current) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setAiLoading(true);
    setError("");
    setInsight("");
    setOpen(true);

    const prompt = buildPrompt(tab, dash, effectiveStart, effectiveEnd, dash.viewMode);

    try {
      const res = await fetch(`${API}/api/insights`, {
        method: "POST",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tab,
          prompt,
          view_mode:  dash.viewMode,
          start_date: tab === "daily" ? effectiveEnd : effectiveStart,
          end_date:   effectiveEnd,
          locations:  dash.filters?.locations || [],
        }),
      });

      if (!mountedRef.current) return;

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.detail?.error || err?.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      setInsight(data.insight || "");
    } catch (e) {
      if (e.name === "AbortError") return;
      if (!mountedRef.current) return;
      setError(e.message);
    }

    setAiLoading(false);
  }, [tab, dash, effectiveStart, effectiveEnd]); // eslint-disable-line

  // ── Auto-trigger: fires on tab/date changes, never on first load ──────────
  useEffect(() => {
    if (!firstLoadDoneRef.current) return;

    // Daily KPIs only cares about the single day (effectiveEnd).
    // All other tabs care about the full range (effectiveStart → effectiveEnd).
    const key = tab === "daily"
      ? `${tab}|${dash.viewMode}|${effectiveEnd}`
      : `${tab}|${dash.viewMode}|${effectiveStart}|${effectiveEnd}`;
    setInsight("");
    setError("");
    if (lastKeyRef.current === key) return;

    if (!dash.loading) {
      lastKeyRef.current    = key;
      pendingKeyRef.current = null;
      generate();
    } else {
      pendingKeyRef.current = key;
    }
  }, [tab, effectiveStart, effectiveEnd]); // eslint-disable-line

  // ── Pick up pending request once dashboard finishes loading ───────────────
  useEffect(() => {
    if (dash.loading) return;

    if (!firstLoadDoneRef.current) {
      firstLoadDoneRef.current = true;
      return;
    }

    const key = tab === "daily"
      ? `${tab}|${dash.viewMode}|${effectiveEnd}`
      : `${tab}|${dash.viewMode}|${effectiveStart}|${effectiveEnd}`;
    if (pendingKeyRef.current !== key) return;
    if (lastKeyRef.current === key) return;

    lastKeyRef.current    = key;
    pendingKeyRef.current = null;
    generate();
  }, [dash.loading]); // eslint-disable-line

  // ── Derived display values ────────────────────────────────────────────────
  const TAB_LABELS = {
    daily: "Daily KPIs", mtd: "MTD Performance", ops: "Operations",
    scorecard: "Employee Scorecard", appointments: "Appointments",
  };
  const tabLabel    = TAB_LABELS[tab] || tab;
  const isDay       = dash.viewMode === "day";
  const dashLoading = dash.loading;

  // Daily KPIs tab always analyzes a single day (effectiveEnd), regardless of view mode.
  // All other tabs analyze the full MTD range.
  const dateChip = (tab === "daily" || isDay)
    ? fmtShort(effectiveEnd)
    : `${fmtShort(effectiveStart)} – ${fmtShort(effectiveEnd)}`;

  return (
    <div className="ai-insights-wrap">

      {/* ── Trigger button + context chips ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button
          className="ai-insights-btn"
          onClick={() => open ? setOpen(false) : (insight ? setOpen(true) : generate())}
          disabled={aiLoading || dashLoading}
        >
          {dashLoading
            ? "⟳ Loading data…"
            : aiLoading
            ? "⟳ Analyzing…"
            : open
            ? "▾ Hide Insights"
            : "✦ Show Insights"}
        </button>

        {/* Context chip — only shown when panel is closed so user knows what was last analyzed */}
        {!open && insight && (
          <span style={{
            padding: "3px 10px",
            background: "#f4ecee",
            color: "#8a6272",
            fontSize: 9,
            fontFamily: "'Josefin Sans', sans-serif",
            fontWeight: 600,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            lineHeight: 1.6,
          }}>
            {tabLabel} · {dateChip}
          </span>
        )}
      </div>

      {/* ── Panel ── */}
      {open && (
        <div className="ai-insights-panel">

          {/* Header */}
          <div className="ai-insights-header">
            <span className="ai-insights-title">✦ AI Insights</span>
            <span className="ai-insights-meta">{tabLabel} · {dateChip}</span>

            <button className="ai-insights-close" onClick={() => setOpen(false)}>✕</button>
          </div>

          {/* Loading: waiting for dashboard data */}
          {dashLoading && !aiLoading && (
            <div className="ai-insights-loading">
              <span className="ai-pulse">●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.2s" }}>●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.4s" }}>●</span>
              &nbsp; Waiting for dashboard data…
            </div>
          )}

          {/* Loading: AI analyzing */}
          {aiLoading && (
            <div className="ai-insights-loading">
              <span className="ai-pulse">●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.2s" }}>●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.4s" }}>●</span>
              &nbsp; Analyzing {tabLabel}…
            </div>
          )}

          {error && <div className="ai-insights-error">⚠ {error}</div>}

          {insight && !aiLoading && (
            <div className="ai-insights-body">
              {insight.split("\n").filter(Boolean).map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          )}

          {!dashLoading && !aiLoading && !error && !insight && (
            <div className="ai-insights-loading" style={{ color: "#aaa" }}>
              Click "✦ Show Insights" to analyze this view.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
