const BASE = process.env.REACT_APP_API_URL || "";

function buildParams(obj) {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v === undefined || v === null) return;
    if (Array.isArray(v)) v.forEach(val => p.append(k, val));
    else p.append(k, v);
  });
  return p.toString();
}

export async function fetchAPI(path, params = {}) {
  const qs = buildParams(params);
  const url = `${BASE}${path}${qs ? "?" + qs : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json();
}
