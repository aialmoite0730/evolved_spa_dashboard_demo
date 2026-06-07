import React from "react";

/**
 * RoleToggle — a crisp segmented control replacing the dull pill buttons.
 *
 * Usage:
 *   <RoleToggle value={roleFilter} onChange={setRoleFilter} />
 *
 * Renders three segments: All · Providers · Estheticians
 * Styling is fully self-contained via the <style> block below so it works
 * regardless of whatever global .pill / .pills CSS exists.
 */

const SEGMENTS = [
  { value: "all",                label: "All"          },
  { value: "Treatment Provider", label: "Providers"    },
  { value: "Esthetician",        label: "Estheticians" },
];

export default function RoleToggle({ value, onChange }) {
  return (
    <>
      <style>{`
        .rt-wrap {
          display: inline-flex;
          align-items: center;
          background: transparent;
          border: 1px solid #bbb;
          border-radius: 4px;
          padding: 0;
          gap: 0;
          overflow: hidden;
        }

        .rt-btn {
          position: relative;
          padding: 4px 14px;
          border: none;
          border-right: 1px solid #bbb;
          border-radius: 0;
          background: transparent;
          color: #888;
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          cursor: pointer;
          transition: color 0.15s ease, background 0.15s ease;
          white-space: nowrap;
          line-height: 1.7;
          outline: none;
          user-select: none;
        }

        .rt-btn:last-child {
          border-right: none;
        }

        .rt-btn:hover:not(.rt-btn--active) {
          color: #333;
          background: rgba(0,0,0,0.04);
        }

        .rt-btn--active {
          background: #222;
          color: #fff;
          font-weight: 700;
          letter-spacing: 0.07em;
        }
      `}</style>

      <div className="rt-wrap" role="group" aria-label="Filter by role">
        {SEGMENTS.map(({ value: v, label }) => (
          <button
            key={v}
            className={`rt-btn${value === v ? " rt-btn--active" : ""}`}
            onClick={() => onChange(v)}
            aria-pressed={value === v}
          >
            {label}
          </button>
        ))}
      </div>
    </>
  );
}