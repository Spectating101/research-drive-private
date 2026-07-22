/** Unified inspector rail layout — header / judgment / facts / evidence / sticky footer. */

import { useState } from "react";

export function RailFrame({ children, className = "", ...rest }) {
  const extra = className ? ` ${className}` : "";
  return (
    <div className={`rd-v2-rail-panel rd-v2-rail-panel-on${extra}`} {...rest}>
      {children}
    </div>
  );
}

/** Compact identity + status for Detail. Prefer short description; avoid essay headers. */
export function RailEntityHeader({ id, title, pills, description, compact = false }) {
  return (
    <div className={`rd-v2-rail-ehead${compact ? " rd-v2-rail-ehead--compact" : ""}`}>
      {id ? <p className="rd-v2-rail-id mono">{id}</p> : null}
      {title ? <h2 className="rd-v2-rail-title">{title}</h2> : null}
      {pills ? <div className="rd-v2-rail-pills">{pills}</div> : null}
      {description ? <p className="rd-v2-rail-desc">{description}</p> : null}
    </div>
  );
}

export function RailCtas({ children }) {
  if (!children) return null;
  return <div className="rd-v2-rail-ctas">{children}</div>;
}

export function RailFieldGrid({ children }) {
  return <div className="rd-v2-rail-fieldgrid">{children}</div>;
}

export function RailField({ label, value, mono = false }) {
  const shown = value == null || value === "" ? <span className="rd-v2-field-empty">—</span> : value;
  return (
    <div className="rd-v2-detail-row">
      <span className="rd-v2-detail-label">{label}</span>
      <span className={`rd-v2-detail-val${mono ? " mono" : ""}`}>{shown}</span>
    </div>
  );
}

export function RailStickyFooter({ children }) {
  if (!children) return null;
  return <div className="rd-v2-rail-sticky">{children}</div>;
}

/** One judgment sentence under the identity header. */
export function RailJudgment({ children, label = null }) {
  if (children == null || children === "") return null;
  return (
    <section className="rd-v2-rail-judgment" aria-label={label || "Judgment"} data-testid="rail-judgment">
      {label ? <p className="rd-v2-rail-section-label">{label}</p> : null}
      <p className="rd-v2-rail-judgment-text">{children}</p>
    </section>
  );
}

/**
 * Divider-led fact section (Confirmed / Unknown). Renders nothing when empty.
 * items: string[] or { label, value }[]
 */
export function RailFactSection({ title, items = [], testId }) {
  const rows = (items || []).filter((item) => {
    if (item == null || item === "") return false;
    if (typeof item === "string") return Boolean(item.trim());
    return Boolean(item.label || item.value);
  });
  if (!rows.length) return null;

  return (
    <section className="rd-v2-rail-fact-section" aria-label={title} data-testid={testId || undefined}>
      <h3 className="rd-v2-rail-fact-heading">{title}</h3>
      <ul className="rd-v2-rail-fact-list">
        {rows.map((item, index) => {
          if (typeof item === "string") {
            return <li key={`${item}-${index}`}>{item}</li>;
          }
          const key = `${item.label || "fact"}-${index}`;
          return (
            <li key={key}>
              {item.label ? (
                <span className="rd-v2-rail-fact-pair">
                  <span className="rd-v2-detail-label">{item.label}</span>
                  <span className={`rd-v2-detail-val${item.mono ? " mono" : ""}`}>{item.value}</span>
                </span>
              ) : (
                item.value
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Collapsible technical / provenance evidence — only mount when children exist. */
export function RailEvidenceDetails({ label = "Technical evidence", defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  if (children == null || children === false) return null;

  return (
    <div className="rd-v2-rail-evidence">
      <button
        type="button"
        className="rd-v2-rail-evidence-hd"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        data-testid="rail-evidence-toggle"
      >
        <span>{label}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.15s" }}
          aria-hidden
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open ? <div className="rd-v2-rail-evidence-body">{children}</div> : null}
    </div>
  );
}

/**
 * Sticky footer: one primary control, then at most two text secondary actions.
 * primary / secondary items: { key, label, onClick, disabled, busy, testId, busyLabel }
 */
export function RailActionFooter({ primary = null, secondary = [] }) {
  const secondaries = (secondary || []).filter(Boolean).slice(0, 2);
  if (!primary && !secondaries.length) return null;

  return (
    <div className="rd-v2-rail-sticky rd-v2-rail-action-footer">
      {primary ? (
        <button
          type="button"
          className="rd-v2-btn sm primary"
          disabled={primary.disabled}
          data-testid={primary.testId}
          onClick={primary.onClick}
        >
          {primary.busy && primary.busyLabel ? primary.busyLabel : primary.label}
        </button>
      ) : null}
      {secondaries.length ? (
        <div className="rd-v2-rail-secondary-actions">
          {secondaries.map((action) => (
            <button
              key={action.key || action.label}
              type="button"
              className="rd-v2-rail-text-action"
              disabled={action.disabled}
              data-testid={action.testId}
              onClick={action.onClick}
            >
              {action.busy && action.busyLabel ? action.busyLabel : action.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const DECISION_ROWS = [
  ["status", "Status"],
  ["primary", "Use now"],
  ["risk", "Risk"],
  ["next", "Next"],
];

export function RailDecisionSummary({ status, primary, risk, next }) {
  const rows = DECISION_ROWS.map(([key, label]) => [label, { status, primary, risk, next }[key]])
    .filter(([, value]) => value != null && String(value).trim() !== "");
  if (!rows.length) return null;

  return (
    <section className="rd-v2-rail-decision" aria-label="Decision summary">
      {rows.map(([label, value]) => {
        const tone =
          label === "Use now" && /yes|ready|available|registered/i.test(String(value))
            ? "ok"
            : label === "Risk" && /low/i.test(String(value))
              ? "ok"
              : label === "Risk" && /needs|pending|offline|attention|no query/i.test(String(value))
                ? "warn"
                : label === "Status" && /needs|offline|check/i.test(String(value))
                  ? "warn"
                  : "";
        return (
          <div key={label} className="rd-v2-rail-decision-row">
            <span className="rd-v2-rail-decision-label">{label}</span>
            <span className={`rd-v2-rail-decision-value${tone ? ` ${tone}` : ""}`}>{value}</span>
          </div>
        );
      })}
    </section>
  );
}
