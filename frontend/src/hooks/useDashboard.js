import { useState, useEffect, useCallback, useRef } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

function qs(obj) {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach(vi => p.append(k, vi));
    else if (v != null && v !== "") p.append(k, v);
  });
  return p.toString() ? "?" + p.toString() : "";
}

async function fetchJSON(path, signal) {
  const res = await fetch(API + path, { signal });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

// How long to wait after the last filter change before firing requests (ms).
// Prevents double-fetch when two filter keys change back-to-back (e.g. startDate + endDate).
const DEBOUNCE_MS = 300;

export function useDashboard() {
  const [viewMode, setViewMode] = useState("month");

  // null until /api/latest-date resolves — prevents any data fetch with wrong dates
  const [filters, setFilters] = useState(null);

  const [locations,         setLocations]         = useState([]);
  const [kpiHeader,         setKpiHeader]         = useState(null);
  const [dailyKpis,         setDailyKpis]         = useState([]);
  const [dailyMix,          setDailyMix]          = useState([]);
  const [mtdSummary,        setMtdSummary]        = useState([]);
  const [mtdMix,            setMtdMix]            = useState([]);
  const [monthlyTrend,      setMonthlyTrend]      = useState([]);
  const [operations,        setOperations]        = useState([]);
  const [revenueTrend,      setRevenueTrend]      = useState([]);
  const [categoryBreakdown, setCategoryBreakdown] = useState([]);
  const [employeeUtil,      setEmployeeUtil]      = useState([]);
  const [employeeRph,       setEmployeeRph]       = useState([]);
  const [employeeScorecard, setEmployeeScorecard] = useState([]);
  const [apptSummary,       setApptSummary]       = useState([]);
  const [apptByStatus,      setApptByStatus]      = useState([]);
  const [apptByCategory,    setApptByCategory]    = useState([]);
  const [apptByProvider,    setApptByProvider]    = useState([]);
  const [apptBySource,      setApptBySource]      = useState([]);
  const [apptCancelReasons, setApptCancelReasons] = useState([]);
  const [apptDailyTrend,    setApptDailyTrend]    = useState([]);
  const [apptRequestType,   setApptRequestType]   = useState([]);
  const [mtdDailyTrend,     setMtdDailyTrend]     = useState(null);

  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState(null);

  // Refs for debounce timer and in-flight AbortController
  const debounceTimer = useRef(null);
  const abortCtrl     = useRef(null);

  // ── On mount: resolve latest data date + locations in one shot ─────────────
  // This is the ONLY place locations and the initial date are fetched.
  // filters stays null until this resolves, which blocks all data fetches.
  useEffect(() => {
    Promise.all([
      fetchJSON("/api/latest-cash-date"),
      fetchJSON("/api/locations"),
    ])
      .then(([dateRes, locs]) => {
        const latest = dateRes.latest_date;          // e.g. "2026-06-13"
        const start  = latest.slice(0, 7) + "-01";  // e.g. "2026-06-01"
        setLocations(locs);
        setFilters({
          startDate: start,
          endDate:   latest,
          dayDate:   latest,
          locations: [],
        });
      })
      .catch(e => setError(e.message));
  }, []);

  // ── Core fetch ─────────────────────────────────────────────────────────────
  // Called after debounce settles. Receives a stable snapshot of filters +
  // viewMode so it doesn't need them as deps (avoids stale closure issues).
  const fetchAll = useCallback(async (snapshot, signal) => {
    const { filters: f, viewMode: vm } = snapshot;

    const loc    = f.locations.length ? f.locations : undefined;
    const locArg = loc ? { locations: loc } : {};

    const effectiveStart = vm === "day" ? f.dayDate : f.startDate;
    const effectiveEnd   = vm === "day" ? f.dayDate : f.endDate;

    const dateQ = qs({ date: effectiveEnd,                                ...locArg });
    const mtdQ  = qs({ start_date: effectiveStart, end_date: effectiveEnd, ...locArg });

    const [
      header, kpis, dmix,
      mtd, mmix, trend,
      ops, rev, cat,
      util, rph, scorecard,
      aSummary, aStatus, aCategory,
      aProvider, aSource, aCancelReasons,
      aDailyTrend, aRequestType,
      mtdTrend,
    ] = await Promise.all([
      fetchJSON(`/api/mtd-kpi-header${mtdQ}`,                      signal),
      fetchJSON(`/api/daily-kpis${dateQ}`,                         signal),
      fetchJSON(`/api/daily-sales-mix${dateQ}`,                    signal),
      fetchJSON(`/api/mtd-summary${mtdQ}`,                         signal),
      fetchJSON(`/api/mtd-sales-mix${mtdQ}`,                       signal),
      fetchJSON(`/api/monthly-trend${mtdQ}`,                       signal),
      fetchJSON(`/api/operations-summary${mtdQ}`,                  signal),
      fetchJSON(`/api/revenue-trend${mtdQ}`,                       signal),
      fetchJSON(`/api/category-breakdown${mtdQ}`,                  signal),
      fetchJSON(`/api/employee-utilization${mtdQ}`,                signal),
      fetchJSON(`/api/employee-rph${mtdQ}`,                        signal),
      fetchJSON(`/api/employee-scorecard${mtdQ}`,                  signal),
      fetchJSON(`/api/appointments/summary${mtdQ}`,                signal),
      fetchJSON(`/api/appointments/by-status${mtdQ}`,              signal),
      fetchJSON(`/api/appointments/by-category${mtdQ}`,            signal),
      fetchJSON(`/api/appointments/by-provider${mtdQ}`,            signal),
      fetchJSON(`/api/appointments/by-booking-source${mtdQ}`,      signal),
      fetchJSON(`/api/appointments/cancellation-reasons${mtdQ}`,   signal),
      fetchJSON(`/api/appointments/daily-trend${mtdQ}`,            signal),
      fetchJSON(`/api/appointments/request-type${mtdQ}`,           signal),
      fetchJSON(`/api/mtd-daily-trend${mtdQ}`,                     signal),
    ]);

    setKpiHeader(header);
    setDailyKpis(kpis);
    setDailyMix(dmix);
    setMtdSummary(mtd);
    setMtdMix(mmix);
    setMonthlyTrend(trend);
    setOperations(ops);
    setRevenueTrend(rev);
    setCategoryBreakdown(cat);
    setEmployeeUtil(util);
    setEmployeeRph(rph);
    setEmployeeScorecard(scorecard);
    setApptSummary(aSummary);
    setApptByStatus(aStatus);
    setApptByCategory(aCategory);
    setApptByProvider(aProvider);
    setApptBySource(aSource);
    setApptCancelReasons(aCancelReasons);
    setApptDailyTrend(aDailyTrend);
    setApptRequestType(aRequestType);
    setMtdDailyTrend(mtdTrend);
  }, []);

  // ── Debounced refresh ──────────────────────────────────────────────────────
  // Guards against null filters (before /api/latest-date resolves).
  // Cancels previous in-flight batch, waits DEBOUNCE_MS, fires fresh batch.
  const refresh = useCallback(() => {
    // Don't fire until the initial date resolution has completed
    if (!filters) return;

    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (abortCtrl.current) abortCtrl.current.abort();

    debounceTimer.current = setTimeout(() => {
      const controller = new AbortController();
      abortCtrl.current = controller;

      // Read current state at the moment the timer fires to avoid stale closures.
      setFilters(currentFilters => {
        setViewMode(currentViewMode => {
          setLoading(true);
          setError(null);

          fetchAll({ filters: currentFilters, viewMode: currentViewMode }, controller.signal)
            .catch(e => {
              // AbortError is expected when a newer request cancels this one — ignore it.
              if (e.name !== "AbortError") setError(e.message);
            })
            .finally(() => setLoading(false));

          return currentViewMode;
        });
        return currentFilters;
      });
    }, DEBOUNCE_MS);
  }, [filters, fetchAll]);

  // Re-run whenever filters or viewMode change.
  // The null guard in refresh() ensures this is a no-op until filters are ready.
  useEffect(() => {
    if (!filters) return;
    refresh();
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (abortCtrl.current)     abortCtrl.current.abort();
    };
  }, [filters, viewMode, refresh]);

  // ── Filter helpers ─────────────────────────────────────────────────────────

  function updateFilter(key, val) {
    setFilters(f => {
      if (!f) return f;
      if (key === "startDate") {
        const newEndDate = val > f.endDate ? val : f.endDate;
        return { ...f, startDate: val, endDate: newEndDate };
      }
      return { ...f, [key]: val };
    });
  }

  function updateDateRange(start, end) {
    setFilters(f => f ? { ...f, startDate: start, endDate: end } : f);
  }

  function toggleLocation(loc) {
    setFilters(f => {
      if (!f) return f;
      const locs = f.locations.includes(loc)
        ? f.locations.filter(l => l !== loc)
        : [...f.locations, loc];
      return { ...f, locations: locs };
    });
  }

  // Safe derived dates — empty string when filters not yet loaded,
  // so App.js date display shows nothing rather than crashing.
  const effectiveStart = filters
    ? (viewMode === "day" ? filters.dayDate : filters.startDate)
    : "";
  const effectiveEnd = filters
    ? (viewMode === "day" ? filters.dayDate : filters.endDate)
    : "";

  return {
    viewMode, setViewMode,
    filters, effectiveStart, effectiveEnd,
    locations,
    kpiHeader,
    dailyKpis, dailyMix,
    mtdSummary, mtdMix,
    monthlyTrend,
    operations,
    revenueTrend,
    categoryBreakdown,
    employeeUtil, employeeRph, employeeScorecard,
    apptSummary, apptByStatus, apptByCategory,
    apptByProvider, apptBySource, apptCancelReasons,
    apptDailyTrend, apptRequestType,
    mtdDailyTrend,
    loading, error,
    updateFilter, updateDateRange, toggleLocation, refresh,
  };
}