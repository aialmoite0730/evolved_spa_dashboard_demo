import { useState, useEffect, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

function today() { return new Date().toISOString().slice(0, 10); }
function yesterday() {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}
function monthStart() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

// Returns dateStr minus 1 day (used to find last completed day in month view)
function dateMinus1(dateStr) {
  const d = new Date(dateStr + "T00:00:00");
  d.setDate(d.getDate() - 1);
  return d.toISOString().slice(0, 10);
}

function qs(obj) {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (Array.isArray(v)) v.forEach(vi => p.append(k, vi));
    else if (v != null && v !== "") p.append(k, v);
  });
  return p.toString() ? "?" + p.toString() : "";
}

async function fetchJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`);
  return res.json();
}

export function useDashboard() {
  // viewMode: "day" | "month"
  const [viewMode, setViewMode] = useState("month");

  const [filters, setFilters] = useState({
    // Month view
    startDate: monthStart(),
    endDate:   today(),
    // Day view
    dayDate:   yesterday(),
    // Shared
    locations: [],
  });

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
  const [loading,           setLoading]           = useState(false);
  const [error,             setError]             = useState(null);

  useEffect(() => {
    fetchJSON("/api/locations")
      .then(setLocations)
      .catch(e => setError(e.message));
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    const loc    = filters.locations.length ? filters.locations : undefined;
    const locArg = loc ? { locations: loc } : {};

    // In day view, use dayDate as both start and end so all endpoints
    // treat it as a single-day range — no special backend changes needed.
    const effectiveStart = viewMode === "day" ? filters.dayDate : filters.startDate;
    const effectiveEnd   = viewMode === "day" ? filters.dayDate : filters.endDate;

    // Daily endpoints always query the last completed day:
    //   - Day view:   the selected dayDate
    //   - Month view: endDate - 1, because endDate (e.g. May 31 = today)
    //                 has no data yet, so we show the prior closed day instead.
    const dailyDate = viewMode === "day" ? effectiveEnd : dateMinus1(effectiveEnd);

    const dateQ = qs({ date: dailyDate, ...locArg });
    const mtdQ  = qs({ start_date: effectiveStart, end_date: effectiveEnd, ...locArg });

    try {
      const [
        header, kpis, dmix,
        mtd, mmix, trend,
        ops, rev, cat,
        util, rph, scorecard,
      ] = await Promise.all([
        fetchJSON(`/api/mtd-kpi-header${mtdQ}`),
        fetchJSON(`/api/daily-kpis${dateQ}`),
        fetchJSON(`/api/daily-sales-mix${dateQ}`),
        fetchJSON(`/api/mtd-summary${mtdQ}`),
        fetchJSON(`/api/mtd-sales-mix${mtdQ}`),
        fetchJSON(`/api/monthly-trend${mtdQ}`),
        fetchJSON(`/api/operations-summary${mtdQ}`),
        fetchJSON(`/api/revenue-trend${mtdQ}`),
        fetchJSON(`/api/category-breakdown${mtdQ}`),
        fetchJSON(`/api/employee-utilization${mtdQ}`),
        fetchJSON(`/api/employee-rph${mtdQ}`),
        fetchJSON(`/api/employee-scorecard${mtdQ}`),
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
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [filters, viewMode]);

  useEffect(() => { refresh(); }, [refresh]);

  function updateFilter(key, val) {
    setFilters(f => {
      if (key === "startDate") {
        // Prevent MTD To from going earlier than MTD From
        const newEndDate = val > f.endDate ? val : f.endDate;
        return { ...f, startDate: val, endDate: newEndDate };
      }
      return { ...f, [key]: val };
    });
  }

  function toggleLocation(loc) {
    setFilters(f => {
      const locs = f.locations.includes(loc)
        ? f.locations.filter(l => l !== loc)
        : [...f.locations, loc];
      return { ...f, locations: locs };
    });
  }

  // Expose effective dates so App.js labels always reflect what was queried
  const effectiveStart = viewMode === "day" ? filters.dayDate : filters.startDate;
  const effectiveEnd   = viewMode === "day" ? filters.dayDate : filters.endDate;

  // The actual date used for daily-kpis / daily-sales-mix — shown in the
  // "Prior Day KPIs" section header so the label matches the data.
  const effectiveDailyDate = viewMode === "day" ? filters.dayDate : dateMinus1(filters.endDate);

  return {
    viewMode, setViewMode,
    filters, effectiveStart, effectiveEnd, effectiveDailyDate,
    locations,
    kpiHeader,
    dailyKpis, dailyMix,
    mtdSummary, mtdMix,
    monthlyTrend,
    operations,
    revenueTrend,
    categoryBreakdown,
    employeeUtil,
    employeeRph,
    employeeScorecard,
    loading, error,
    updateFilter, toggleLocation, refresh,
  };
}