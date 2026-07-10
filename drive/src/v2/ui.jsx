/** Shared v2 page chrome — matches docs/design/references/desk-v2-1440.html */

export function PageShell({ title, lead, headExtra, toolbar, footer, children, narrow = false, className = "" }) {
  return (
    <div className={`rd-v2-page${narrow ? " narrow" : ""}${className ? ` ${className}` : ""}`}>
      {(title || lead || headExtra) ? (
        <header className="rd-v2-page-head">
          {title ? <h1>{title}</h1> : null}
          {lead ? <p className="rd-v2-lead">{lead}</p> : null}
          {headExtra}
        </header>
      ) : null}
      {toolbar ? <div className="rd-v2-toolbar">{toolbar}</div> : null}
      <div className="rd-v2-body-scroll">{children}</div>
      {footer ? <div className="rd-v2-scroll-foot">{footer}</div> : null}
    </div>
  );
}

export function Chip({ active, warn, children, onClick, className = "" }) {
  const cls = [
    "rd-v2-chip",
    active ? "on" : "",
    warn ? "warn" : "",
    onClick ? "clickable" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  if (onClick) {
    return (
      <button type="button" className={cls} onClick={onClick}>
        {children}
      </button>
    );
  }
  return <span className={cls}>{children}</span>;
}

export function SectionTitle({ title, actionLabel, onAction }) {
  return (
    <div className="rd-v2-section-title">
      <span>{title}</span>
      {actionLabel ? (
        <button type="button" className="rd-v2-text-link" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function Strip({ warn, children, actionLabel, onAction }) {
  return (
    <div className={`rd-v2-strip${warn ? " warn" : ""}`}>
      <span>{children}</span>
      {actionLabel ? (
        <button type="button" className="rd-v2-text-link" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

export function Card({ title, children, actions }) {
  return (
    <div className="rd-v2-card">
      {title ? <h3>{title}</h3> : null}
      {children}
      {actions ? <div className="rd-v2-card-actions">{actions}</div> : null}
    </div>
  );
}

export function LedgerSection({ title }) {
  return <div className="rd-v2-ledger-section">{title}</div>;
}

export function LedgerRow({ label, status, metric, progress, active, onClick }) {
  const Tag = onClick ? "button" : "div";
  const statusCls = status === "WARN" ? "warn" : status === "FAIL" ? "fail" : "ok";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      className={`rd-v2-ledger-row${active ? " on" : ""}`}
      onClick={onClick}
    >
      <span className="rd-v2-ledger-label">{label}</span>
      <span className="rd-v2-ledger-mid">
        {progress != null ? (
          <span className="rd-v2-progress" aria-hidden>
            <span className="rd-v2-progress-fill" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
          </span>
        ) : metric ? (
          <span className="rd-v2-ledger-metric">{metric}</span>
        ) : null}
      </span>
      {status ? <span className={`rd-v2-status-badge ${statusCls}`}>{status}</span> : <span />}
    </Tag>
  );
}

export function StatCard({ label, value, tone = "neutral" }) {
  return (
    <div className={`rd-v2-stat-card ${tone}`}>
      <span className="rd-v2-stat-value">{value}</span>
      <span className="rd-v2-stat-label">{label}</span>
    </div>
  );
}

export function CatalogHeader({ columns }) {
  return (
    <div className="rd-v2-catalog-hd" role="row">
      {columns.map((col) => (
        <span key={col} className="rd-v2-catalog-hd-cell">{col}</span>
      ))}
    </div>
  );
}

export function SourceRibbon({ source }) {
  const key = String(source || "web").toLowerCase();
  let label = "WEB";
  let tone = "neutral";
  if (key.includes("collection_index") || key.includes("local_open") || key === "local") {
    label = "LAB";
    tone = "lab";
  }
  else if (key.includes("registry")) { label = "REG"; tone = "reg"; }
  else if (key.includes("queue") || key.includes("job")) { label = "JOB"; tone = "job"; }
  else if (key.includes("mops")) { label = "MOPS"; tone = "tw"; }
  else if (key.includes("twse")) { label = "TWSE"; tone = "tw"; }
  else if (key.includes("hugging")) { label = "HF"; tone = "hf"; }
  else if (key.includes("sec")) { label = "SEC"; tone = "sec"; }
  else if (key.includes("bigquery") || key === "bq") { label = "BQ"; tone = "bq"; }
  else if (key.includes("zenodo")) { label = "ZENODO"; tone = "doi"; }
  else if (key.includes("datacite") || key.includes("doi")) { label = "DOI"; tone = "doi"; }
  else if (key.includes("gdelt")) { label = "GDELT"; tone = "gdelt"; }
  return <span className={`rd-v2-source-ribbon ${tone}`}>{label}</span>;
}

export function SettingsCard({ title, children }) {
  return (
    <section className="rd-v2-settings-card">
      {title ? <h3>{title}</h3> : null}
      {children}
    </section>
  );
}

export function ChipRow({ children }) {
  return <div className="rd-v2-chips-row">{children}</div>;
}

export function StatementSection({ title, action, children, className = "" }) {
  return (
    <section className={`rd-v2-statement-section${className ? ` ${className}` : ""}`}>
      <div className="rd-v2-statement-head">
        <h2>{title}</h2>
        {action}
      </div>
      <div className="rd-v2-statement-body">{children}</div>
    </section>
  );
}

export function StatementRow({ label, metric, sublabel, detail, warn, active, onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      type={onClick ? "button" : undefined}
      className={`rd-v2-statement-row${warn ? " warn" : ""}${active ? " on" : ""}`}
      onClick={onClick}
    >
      <span className="rd-v2-statement-label">{label}</span>
      <strong className="rd-v2-statement-metric">{metric || "—"}</strong>
      <span className="rd-v2-statement-sub">{sublabel || "—"}</span>
      <span className="rd-v2-statement-detail">{detail || "—"}</span>
    </Tag>
  );
}

export function EmptyPanel({ title, hint, action }) {
  return (
    <div className="rd-v2-empty-panel">
      <strong>{title}</strong>
      {hint ? <p>{hint}</p> : null}
      {action}
    </div>
  );
}

export function WorkbenchIntro({ eyebrow, title, body, actions }) {
  return (
    <section className="rd-v2-workbench-intro">
      <div>
        {eyebrow ? <span className="rd-v2-workbench-eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
        {body ? <p>{body}</p> : null}
      </div>
      {actions ? <div className="rd-v2-workbench-actions">{actions}</div> : null}
    </section>
  );
}
