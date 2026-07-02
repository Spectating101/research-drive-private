/** Unified inspector rail layout — header / CTAs / scroll / sticky footer. */

export function RailFrame({ children }) {
  return <div className="rd-v2-rail-panel rd-v2-rail-panel-on">{children}</div>;
}

export function RailEntityHeader({ id, title, pills, description }) {
  return (
    <div className="rd-v2-rail-ehead">
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
