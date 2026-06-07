import { useState, useEffect, useCallback } from "react";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

function today()      { return new Date().toISOString().slice(0, 10); }
function monthStart() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
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
  const [filters, setFilters] = useState({
    startDate: monthStart(),
    endDate:   today(),
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
  // Employee-level data (from schedule + sales join)
  const [employeeUtil,      setEmployeeUtil]      = useState([]);
  const [employeeRph,       setEmployeeRph]       = useState([]);
  const [employeeScorecard, setEmployeeScorecard] = useState([]);
  const [loading,           setLoading]           = useState(false);
  const [error,             setError]             = useState(null);

  // Load location list once
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

    const dateQ = qs({ date: filters.endDate, ...locArg });
    const mtdQ  = qs({ start_date: filters.startDate, end_date: filters.endDate, ...locArg });

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
  }, [filters]);

  useEffect(() => { refresh(); }, [refresh]);

  function updateFilter(key, val) {
    setFilters(f => ({ ...f, [key]: val }));
  }

  function toggleLocation(loc) {
    setFilters(f => {
      const locs = f.locations.includes(loc)
        ? f.locations.filter(l => l !== loc)
        : [...f.locations, loc];
      return { ...f, locations: locs };
    });
  }

  return {
    filters, locations,
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