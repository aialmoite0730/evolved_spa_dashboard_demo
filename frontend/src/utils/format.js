export const fmt = {
  currency(val) {
    const n = Number(val);
    if (isNaN(n)) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(n);
  },

  number(val) {
    const n = Number(val);
    if (isNaN(n)) return "—";
    return new Intl.NumberFormat("en-US").format(Math.round(n));
  },

  pct(val, decimals = 1) {
    const n = Number(val);
    if (isNaN(n)) return "—";
    return n.toFixed(decimals) + "%";
  },

  signed(val) {
    const n = Number(val);
    if (isNaN(n)) return "—";
    const abs = fmt.currency(Math.abs(n));
    return n < 0 ? `(${abs})` : abs;
  },

  signedPct(val) {
    const n = Number(val);
    if (isNaN(n)) return "—";
    return (n >= 0 ? "+" : "") + n.toFixed(1) + "%";
  },
};

/** Return CSS class for utilization % */
export function ucls(val) {
  const n = Number(val);
  if (val == null || isNaN(n)) return "";
  if (n >= 75) return "c-hi";
  if (n >= 60) return "c-md";
  return "c-lo";
}

/** Return CSS class for goal% */
export function gcls(val) {
  const n = Number(val);
  if (val == null || isNaN(n)) return "";
  if (n >= 100) return "c-hi";
  if (n >= 80)  return "c-md";
  return "c-lo";
}

/** Return CSS class for rev per hour — isEsti flag */
export function rcls(val, isEsti) {
  const n = Number(val);
  if (val == null || isNaN(n)) return "";
  const hi = isEsti ? 175 : 550;
  const lo = isEsti ? 125 : 450;
  if (n >= hi) return "c-hi";
  if (n >= lo) return "c-md";
  return "c-lo";
}

/** Return CSS class for signed variance */
export function vcls(val) {
  const n = Number(val);
  if (val == null || isNaN(n)) return "";
  return n >= 0 ? "pos" : "neg";
}