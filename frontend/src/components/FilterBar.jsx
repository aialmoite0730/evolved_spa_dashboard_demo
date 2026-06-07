import React from "react";

/**
 * FilterBar — location chip strip shown below the tab bar.
 * Date filters have been moved into the top bar (App.js).
 */
export default function FilterBar({ filters, locations, updateFilter, toggleLocation }) {
  if (!locations?.length) return null;

  return (
    <div style={{
      background: "#fff",
      borderBottom: "1px solid #E8E7E4",
      padding: "6px 24px",
      display: "flex",
      alignItems: "center",
      gap: 8,
      flexWrap: "wrap",
    }}>
      <span style={{
        fontSize: 8, textTransform: "uppercase", letterSpacing: "0.15em",
        color: "#A37B88", fontWeight: 300, fontFamily: "'Josefin Sans', sans-serif",
      }}>
        Locations
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
        {locations.map(loc => (
          <button
            key={loc}
            className={`pill${filters.locations.includes(loc) ? " on" : ""}`}
            onClick={() => toggleLocation(loc)}
          >
            {loc}
          </button>
        ))}
        {filters.locations.length > 0 && (
          <button
            className="pill"
            style={{ borderColor: "#7f1d1d", color: "#7f1d1d" }}
            onClick={() => updateFilter("locations", [])}
          >
            ✕ Clear
          </button>
        )}
      </div>
    </div>
  );
}
