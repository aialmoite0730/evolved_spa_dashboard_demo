import React, { useState, useEffect, useRef, useCallback } from "react";

const API_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent";

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

// ── Check if the relevant tab's data is present ───────────────────────────────
function hasData(tab, dash) {
  if (tab === "daily")        return (dash.dailyKpis        || []).length > 0;
  if (tab === "mtd")          return dash.kpiHeader?.mtd_revenue != null;
  if (tab === "ops")          return (dash.operations        || []).length > 0;
  if (tab === "appointments") return (dash.apptSummary       || []).length > 0;
  if (tab === "scorecard")    return (dash.employeeScorecard || []).length > 0;
  return false;
}

// ── Prompt builder ────────────────────────────────────────────────────────────
function buildPrompt(tab, dash, effectiveStart, effectiveEnd, viewMode) {
  const isDay = viewMode === "day";
  const dateRange = isDay
    ? `Single Day: ${effectiveEnd}`
    : `MTD Period: ${effectiveStart} to ${effectiveEnd}`;

  const base =
    `You are a senior business analyst for Evolve Med Spa, a multi-location med spa chain. ` +
    `Analyze the following REAL dashboard data and provide 4-6 specific, actionable insights. ` +
    (isDay
      ? `This is a SINGLE DAY snapshot. Focus on: which locations hit their daily revenue target, ` +
        `appointment volume, no-show and cancellation patterns, ASP vs benchmark, and one action for tomorrow. `
      : `This is a MONTH-TO-DATE report. Focus on: revenue trends, performance vs targets, ` +
        `locations standing out (high or low), utilization efficiency, and one concrete recommendation. `) +
    `Use actual numbers from the data. Do NOT say data is missing or zero if numbers are provided. ` +
    `Write in plain business English, short paragraphs, no bullet points, no markdown headers. ` +
    `Max 100 words.\n\n${dateRange}\n\n`;

  if (tab === "daily") {
    const h = dash.kpiHeader || {};
    const summary =
      `Overall: MTD Revenue ${currency(h.mtd_revenue)}, Avg Daily ${currency(h.avg_daily_revenue)}, ` +
      `YoY ${signedPct(h.same_store_yoy)}, ASP ${currency(h.blended_asp)}, ` +
      `New Clients ${num(h.new_client_count)}, Rebooking ${pct(h.rebooking_rate)}`;

    const rows = (dash.dailyKpis || []).map(r =>
      `  ${r.location}: Cash ${currency(r.cash_sales)}, Need ${currency(r.daily_need)}, ` +
      `ASP ${currency(r.asp)}, Appts ${num(r.appointment_count)}, ` +
      `New ${num(r.new_client_count)}, No-Shows ${num(r.no_shows)}, Cancels ${num(r.cancellations)}`
    ).join("\n");

    const mix = (dash.dailyMix || []).length > 0
      ? "Sales mix (top categories): " + (dash.dailyMix || []).slice(0, 3).map(r =>
          `${r.location} — Facials ${currency(r.facials)}, Injectables ${currency(Number(r.filler || 0) + Number(r.neurotoxins || 0) + Number(r.prf || 0))}, Total ${currency(r.total)}`
        ).join(" | ")
      : "";

    return base + `SUMMARY METRICS:\n${summary}\n\nDAILY KPIs BY LOCATION:\n${rows}\n\n${mix}`;
  }

  if (tab === "mtd") {
    const h = dash.kpiHeader || {};
    const daysInMonth = 30;
    const trending = h.avg_daily_revenue ? Number(h.avg_daily_revenue) * daysInMonth : null;
    const budgetVar = h.monthly_budget && trending
      ? Number(trending) - Number(h.monthly_budget) : null;

    const header =
      `MTD Revenue: ${currency(h.mtd_revenue)}\n` +
      `Full-Month Projection (Trending): ${currency(trending)}\n` +
      `Variance to Budget: ${budgetVar != null ? currency(budgetVar) + (budgetVar >= 0 ? " surplus" : " shortfall") : "No budget set"}\n` +
      `Same-Store YoY: ${signedPct(h.same_store_yoy)}\n` +
      `Blended ASP: ${currency(h.blended_asp)}\n` +
      `New Clients: ${num(h.new_client_count)}, Existing: ${num(h.existing_client_count)}\n` +
      `Rebooking Rate: ${pct(h.rebooking_rate)}\n` +
      `Provider Utilization: ${pct(h.provider_utilization)} (target 75%)\n` +
      `Esti Utilization: ${pct(h.esthetician_utilization)} (target 75%)\n` +
      `Provider Rev/Hr: ${currency(h.rev_per_provider)} (target $550)\n` +
      `Esti Rev/Hr: ${currency(h.rev_per_esthetician)} (target $175)\n` +
      `Gross Margin: ${pct(h.gross_margin_pct)}`;

    const rows = (dash.mtdSummary || []).map(r =>
      `  ${r.location}: ${currency(r.cash_sales)} MTD, Trending ${currency(r.trending)}, ` +
      `WoW ${signedPct(r.prior_week_variance_pct)}, vs PM ${signedPct(r.pm_variance_pct)}, vs PY ${signedPct(r.py_variance_pct)}`
    ).join("\n");

    const mix = (dash.mtdMix || []).slice(0, 2).map(r => {
      const total = Number(r.total) || 1;
      const inj = (Number(r.filler || 0) + Number(r.neurotoxins || 0) + Number(r.other_injectables || 0) + Number(r.prf || 0));
      return `  ${r.location}: Facials ${pct(Number(r.facials) / total * 100)}, Injectables ${pct(inj / total * 100)}, Memberships ${pct(Number(r.memberships || 0) / total * 100)}`;
    }).join("\n");

    return base +
      `KEY METRICS:\n${header}\n\n` +
      `BY LOCATION:\n${rows || "No location data"}\n\n` +
      `SALES MIX SAMPLE:\n${mix || "No mix data"}`;
  }

  if (tab === "ops") {
    const rows = (dash.operations || []).map(r =>
      `  ${r.location}: Rev ${currency(r.recognized_revenue)}, ` +
      `Prov Util ${pct(r.provider_utilization)} ${Number(r.provider_utilization) >= 75 ? "✓" : "↓"}, ` +
      `Esti Util ${pct(r.esthetician_utilization)} ${Number(r.esthetician_utilization) >= 75 ? "✓" : "↓"}, ` +
      `Rev/Hr(P) ${currency(r.rev_per_provider)} ${Number(r.rev_per_provider) >= 550 ? "✓" : "↓"}, ` +
      `Rev/Hr(E) ${currency(r.rev_per_esthetician)} ${Number(r.rev_per_esthetician) >= 175 ? "✓" : "↓"}, ` +
      `GM ${pct(r.gross_margin_pct)}, Rebook ${pct(r.rebooking_rate)}`
    ).join("\n");

    return base +
      `TARGETS: Provider Util ≥75%, Esti Util ≥75%, Rev/Hr(Provider) ≥$550, Rev/Hr(Esti) ≥$175\n\n` +
      `OPERATIONS BY LOCATION (✓ = on target, ↓ = below target):\n${rows || "No data"}`;
  }

  if (tab === "appointments") {
    const rows = (dash.apptSummary || []).map(r =>
      `  ${r.location}: Total ${num(r.total_appointments)}, Completed ${num(r.completed)} (${pct(Number(r.completed) / Number(r.total_appointments) * 100)}), ` +
      `No-Shows ${num(r.no_shows)} (${pct(r.no_show_rate)}), Cancels ${num(r.cancellations)} (${pct(r.cancellation_rate)}), ` +
      `Rebook ${pct(r.rebooking_rate)}, New Guests ${num(r.new_guests)}, Avg Duration ${Math.round(Number(r.avg_actual_duration) || 0)} min`
    ).join("\n");

    const cancelTop = (dash.apptCancelReasons || []).slice(0, 4).map(r =>
      `${r.reason}: ${num(r.count)}`
    ).join(", ");

    const catTop = (dash.apptByCategory || []).slice(0, 5).map(r =>
      `${r.category}: ${num(r.total)} appts, ${pct(r.completion_rate)} completion`
    ).join(" | ");

    return base +
      `APPOINTMENT SUMMARY BY LOCATION:\n${rows || "No data"}\n\n` +
      `CANCELLATION REASONS: ${cancelTop || "N/A"}\n\n` +
      `TOP SERVICE CATEGORIES: ${catTop || "N/A"}`;
  }

  if (tab === "scorecard") {
    const providers = (dash.employeeScorecard || []).filter(r => r.role === "Treatment Provider").slice(0, 5);
    const estis     = (dash.employeeScorecard || []).filter(r => r.role === "Esthetician").slice(0, 5);
    const fmt = r =>
      `  ${r.name} (${r.center}): Util ${pct(r.utilization)}, Rev/Hr ${currency(r.rev_per_hr)}, MTD Rev ${currency(r.total_revenue)}`;

    return base +
      `TREATMENT PROVIDERS (target: Util ≥75%, Rev/Hr ≥$550):\n${providers.map(fmt).join("\n") || "No data"}\n\n` +
      `ESTHETICIANS (target: Util ≥75%, Rev/Hr ≥$175):\n${estis.map(fmt).join("\n") || "No data"}`;
  }

  return base + "No data available.";
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function AiInsights({ tab, dash, effectiveStart, effectiveEnd }) {
  const [open,       setOpen]       = useState(true);
  const [aiLoading,  setAiLoading]  = useState(false);
  const [insight,    setInsight]    = useState("");
  const [error,      setError]      = useState("");

  // Track the last key we successfully generated insights for so we don't re-run
  // when an unrelated re-render happens (e.g. a sibling state update in App).
  const lastKeyRef  = useRef(null);
  const mountedRef  = useRef(true);
  const abortRef    = useRef(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  const apiKey = process.env.REACT_APP_GEMINI_API_KEY;

  const generate = useCallback(async () => {
    if (!apiKey) {
      setError("Add REACT_APP_GEMINI_API_KEY to your .env file.");
      setOpen(true);
      return;
    }
    if (!mountedRef.current) return;

    // Cancel any in-flight Gemini request
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setAiLoading(true);
    setError("");
    setInsight("");
    setOpen(true);

    try {
      const prompt = buildPrompt(tab, dash, effectiveStart, effectiveEnd, dash.viewMode);

      const res = await fetch(API_URL, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          "X-goog-api-key": apiKey,
        },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { temperature: 0.3, maxOutputTokens: 600 },
        }),
      });

      if (!mountedRef.current) return;

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 429) throw new Error("Rate limit — wait a moment then click ↺ Regenerate.");
        throw new Error(err?.error?.message || `HTTP ${res.status}`);
      }

      const data = await res.json();
      const text = data?.candidates?.[0]?.content?.parts?.[0]?.text || "";
      if (mountedRef.current) setInsight(text.trim());

    } catch (e) {
      if (e.name === "AbortError") return;
      if (mountedRef.current) setError(e.message);
    } finally {
      if (mountedRef.current) setAiLoading(false);
    }
  }, [tab, dash, effectiveStart, effectiveEnd, apiKey]); // eslint-disable-line

  // ── Auto-trigger: fires only after the dashboard finishes loading ─────────
  const pendingKeyRef = useRef(null);
  const isMountedOnce = useRef(false); // skip the very first render

  useEffect(() => {
    if (!isMountedOnce.current) {
      isMountedOnce.current = true;
      return;
    }

    const key = `${tab}|${dash.viewMode}|${effectiveStart}|${effectiveEnd}`;
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

  useEffect(() => {
    if (dash.loading) return;

    const key = `${tab}|${dash.viewMode}|${effectiveStart}|${effectiveEnd}`;

    if (pendingKeyRef.current !== key) return;
    if (lastKeyRef.current === key) return;

    lastKeyRef.current    = key;
    pendingKeyRef.current = null;
    generate();
  }, [dash.loading]); // eslint-disable-line

  // ── UI ────────────────────────────────────────────────────────────────────
  const tabLabel = {
    daily: "Daily KPIs", mtd: "MTD Performance", ops: "Operations",
    scorecard: "Employee Scorecard", appointments: "Appointments",
  }[tab] || tab;

  const dashLoading = dash.loading;

  return (
    <div className="ai-insights-wrap">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
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

        {!aiLoading && !dashLoading && (
          <button
            className="ai-insights-btn"
            onClick={generate}
            style={{ opacity: 0.6, fontSize: 9 }}
          >
            ↺ Regenerate
          </button>
        )}

        <span style={{
          fontSize: 8, color: "#aaa", letterSpacing: "0.1em",
          textTransform: "uppercase", fontFamily: "'Josefin Sans',sans-serif",
        }}>
          Gemini 2.0 Flash Lite · {tabLabel}
        </span>
      </div>

      {open && (
        <div className="ai-insights-panel">
          <div className="ai-insights-header">
            <span className="ai-insights-title">✦ AI Insights</span>
            <span className="ai-insights-meta">
              {tabLabel} · {dash.viewMode === "day"
                ? `Day · ${effectiveEnd}`
                : `MTD · ${effectiveStart} → ${effectiveEnd}`}
              &nbsp;· Gemini 2.0 Flash Lite
            </span>
            <button className="ai-insights-close" onClick={() => setOpen(false)}>✕</button>
          </div>

          {dashLoading && !aiLoading && (
            <div className="ai-insights-loading">
              <span className="ai-pulse">●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.2s" }}>●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.4s" }}>●</span>
              &nbsp; Waiting for dashboard data…
            </div>
          )}

          {aiLoading && (
            <div className="ai-insights-loading">
              <span className="ai-pulse">●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.2s" }}>●</span>
              <span className="ai-pulse" style={{ animationDelay: "0.4s" }}>●</span>
              &nbsp; Analyzing data…
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
              Waiting for data…
            </div>
          )}
        </div>
      )}
    </div>
  );
}