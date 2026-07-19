import { useEffect, useMemo, useRef, useState } from "react";
import { downloadText, openQueryInNewTab, queryDataset, rowsToCsv } from "@/v2/api";
import { buildSchemaRows, displayName, statusPill } from "@/v2/datasetMeta";
import { previewSampleRows } from "@/v2/deskSeed";
import "@/v2/preview.css";

const MAX_PREVIEW_ROWS = 50;

function compactParts(parts) {
  return parts
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .filter((part, index, all) => all.indexOf(part) === index);
}

function sourceUrl(dataset) {
  if (dataset?.url) return String(dataset.url);
  if (dataset?.doi) return `https://doi.org/${String(dataset.doi).replace(/^https?:\/\/doi\.org\//i, "")}`;
  return "";
}

function previewAssetUrl(dataset) {
  return String(
    dataset?.preview_url ||
      dataset?.content_url ||
      dataset?.file_url ||
      dataset?.download_url ||
      "",
  ).trim();
}

function inferredKind(dataset, isExternal) {
  if (isExternal) return "source";
  const assetUrl = previewAssetUrl(dataset);
  const haystack = compactParts([
    dataset?.mime_type,
    dataset?.content_type,
    dataset?.media_type,
    dataset?.format,
    dataset?.extension,
    dataset?.name,
    dataset?.title,
    assetUrl,
  ])
    .join(" ")
    .toLowerCase();

  if (/image\//.test(haystack) || /\.(png|jpe?g|gif|webp|svg)(?:$|[?#])/.test(haystack)) return "image";
  if (/application\/pdf/.test(haystack) || /\.pdf(?:$|[?#])/.test(haystack)) return "document";
  if (dataset?.dataset_id) return "table";
  return "file";
}

function kindLabel(kind) {
  if (kind === "source") return "External source preview";
  if (kind === "document") return "Document preview";
  if (kind === "image") return "Image preview";
  if (kind === "table") return "Dataset preview";
  return "Evidence preview";
}

function kindIcon(kind) {
  if (kind === "source") return "◉";
  if (kind === "document") return "▤";
  if (kind === "image") return "▧";
  return "▦";
}

function openExternal(url) {
  if (!url) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

function SourceRecord({ dataset }) {
  const rows = [
    ["Publisher", dataset?.source || dataset?.publisher || dataset?.domain || "Not specified"],
    ["Coverage", dataset?.coverage || dataset?.date_range || dataset?.temporal_coverage || "Not specified"],
    ["Grain", dataset?.grain || dataset?.format || "Not specified"],
    ["Access", dataset?.access_mode || dataset?.collect_via || "Source-specific"],
    ["License", dataset?.license || "See source terms"],
  ];

  return (
    <div className="rd-preview-source-record">
      <div className="rd-preview-source-brand">
        <span>{dataset?.source || dataset?.publisher || "External source"}</span>
        <strong>{displayName(dataset)}</strong>
      </div>
      <dl className="rd-preview-source-fields">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {dataset?.description ? <p className="rd-preview-description">{dataset.description}</p> : null}
      <div className="rd-preview-boundary">
        <strong>Source record only</strong>
        <span>No rows or document contents have been collected or observed yet.</span>
      </div>
    </div>
  );
}

function UnavailablePreview({ dataset, error, onRetry }) {
  const remaining = compactParts([
    dataset?.source || dataset?.publisher ? `Source · ${dataset?.source || dataset?.publisher}` : "",
    dataset?.coverage || dataset?.date_range ? `Coverage · ${dataset?.coverage || dataset?.date_range}` : "",
    dataset?.grain ? `Grain · ${dataset.grain}` : "",
    dataset?.local_root || dataset?.local_path ? "Archive record · available" : "",
  ]);

  return (
    <div className="rd-preview-unavailable">
      <div className="rd-preview-unavailable-mark">!</div>
      <h3>Preview unavailable</h3>
      <p>{error || "The backing evidence could not be rendered."}</p>
      {remaining.length ? (
        <div className="rd-preview-unavailable-meta">
          <strong>What remains available</strong>
          <ul>
            {remaining.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      {onRetry ? (
        <button type="button" className="rd-preview-link-button" onClick={onRetry}>
          Retry preview
        </button>
      ) : null}
    </div>
  );
}

export function PreviewModal({
  open,
  dataset,
  mode = "lab",
  initialTab = "preview",
  usingSeed = false,
  onClose,
  onAskAbout,
  onPrevious,
  onNext,
}) {
  const [tab, setTab] = useState(initialTab === "schema" ? "fields" : "rows");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [demoNotice, setDemoNotice] = useState("");
  const [retryToken, setRetryToken] = useState(0);
  const closeButtonRef = useRef(null);

  const isExternal = mode === "external";
  const kind = useMemo(() => inferredKind(dataset, isExternal), [dataset, isExternal]);
  const assetUrl = previewAssetUrl(dataset);
  const externalUrl = sourceUrl(dataset);
  const cols = rows[0] ? Object.keys(rows[0]).slice(0, 8) : [];
  const schemaRows = buildSchemaRows(dataset, rows[0]);
  const title = displayName(dataset);
  const readiness = isExternal ? "Source record" : statusPill(dataset);
  const metaParts = compactParts([
    dataset?.source || dataset?.publisher || dataset?.backend,
    dataset?.grain || dataset?.format,
    dataset?.coverage || dataset?.date_range || dataset?.temporal_coverage,
    readiness,
  ]);

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      if (previousFocus && typeof previousFocus.focus === "function") previousFocus.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setTab(initialTab === "schema" ? "fields" : "rows");
    setRows([]);
    setError("");
    setDemoNotice("");
  }, [open, initialTab, dataset?.dataset_id, dataset?.url, dataset?.doi]);

  useEffect(() => {
    if (!open || !dataset?.dataset_id || isExternal || kind !== "table") return undefined;
    let cancelled = false;
    setLoading(true);
    setError("");
    setDemoNotice("");
    queryDataset(dataset.dataset_id, MAX_PREVIEW_ROWS)
      .then((data) => {
        if (!cancelled) setRows(Array.isArray(data?.rows) ? data.rows : []);
      })
      .catch(() => {
        if (cancelled) return;
        if (usingSeed) {
          setRows(previewSampleRows(dataset));
          setDemoNotice("Demo sample — connect the query engine for live rows.");
          setError("");
        } else {
          setRows([]);
          setError("The query engine could not return a sample for this registered dataset.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, dataset?.dataset_id, isExternal, kind, usingSeed, retryToken]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (event.key === "ArrowLeft" && onPrevious) {
        event.preventDefault();
        onPrevious();
      } else if (event.key === "ArrowRight" && onNext) {
        event.preventDefault();
        onNext();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, onPrevious, onNext]);

  if (!open || !dataset) return null;

  const retry = () => setRetryToken((value) => value + 1);
  const exportRows = () => {
    const csv = rowsToCsv(rows);
    if (csv) downloadText(`${dataset.dataset_id || "evidence"}-preview.csv`, csv, "text/csv");
  };

  return (
    <div className="rd-preview-scrim" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      {onPrevious ? (
        <button type="button" className="rd-preview-adjacent previous" onClick={onPrevious} aria-label="Preview previous item">
          ‹
        </button>
      ) : null}
      <section
        className={`rd-preview-shell kind-${kind}`}
        role="dialog"
        aria-modal="true"
        aria-label={`${title} preview`}
      >
        <header className="rd-preview-header">
          <div className="rd-preview-identity">
            <span className="rd-preview-icon" aria-hidden="true">{kindIcon(kind)}</span>
            <div>
              <strong>{title}</strong>
              <span>{kindLabel(kind)}</span>
            </div>
          </div>
          <button ref={closeButtonRef} type="button" className="rd-preview-close" onClick={onClose} aria-label="Close preview">
            ×
          </button>
        </header>

        {metaParts.length ? (
          <div className="rd-preview-meta-strip" aria-label="Preview metadata">
            {metaParts.map((part) => <span key={part}>{part}</span>)}
          </div>
        ) : null}

        {kind === "table" ? (
          <nav className="rd-preview-tabs" aria-label="Dataset preview views">
            <button type="button" className={tab === "rows" ? "active" : ""} onClick={() => setTab("rows")}>Rows</button>
            <button type="button" className={tab === "fields" ? "active" : ""} onClick={() => setTab("fields")}>Fields</button>
          </nav>
        ) : null}

        <div className="rd-preview-body">
          {kind === "source" ? <SourceRecord dataset={dataset} /> : null}

          {kind === "table" && tab === "rows" ? (
            <>
              {loading ? (
                <div className="rd-preview-loading" role="status">
                  <span />
                  <p>Loading observed rows…</p>
                </div>
              ) : null}
              {!loading && error ? <UnavailablePreview dataset={dataset} error={error} onRetry={retry} /> : null}
              {!loading && !error && demoNotice ? <p className="rd-preview-demo">{demoNotice}</p> : null}
              {!loading && !error && rows.length === 0 ? (
                <UnavailablePreview dataset={dataset} error="The query completed, but no rows were returned for this sample." onRetry={retry} />
              ) : null}
              {!loading && !error && rows.length > 0 ? (
                <div className="rd-preview-table-wrap">
                  <table className="rd-preview-table">
                    <thead>
                      <tr>{cols.map((column) => <th key={column}>{column}</th>)}</tr>
                    </thead>
                    <tbody>
                      {rows.slice(0, 12).map((row, rowIndex) => (
                        <tr key={rowIndex}>
                          {cols.map((column) => <td key={column}>{String(row[column] ?? "").slice(0, 100)}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </>
          ) : null}

          {kind === "table" && tab === "fields" ? (
            <div className="rd-preview-fields">
              <div className="rd-preview-section-heading">
                <strong>Field inventory</strong>
                <span>Registry metadata plus observed sample fields</span>
              </div>
              {schemaRows.length ? (
                <table className="rd-preview-table fields">
                  <thead>
                    <tr><th>Field</th><th>Type</th><th>Authority</th></tr>
                  </thead>
                  <tbody>
                    {schemaRows.map((row) => (
                      <tr key={row.name}>
                        <td>{row.name}</td>
                        <td>{row.type}</td>
                        <td>{row.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <UnavailablePreview dataset={dataset} error="No field metadata or observed rows are available yet." />
              )}
              <p className="rd-preview-field-note">
                Field types are derived from registry metadata and the observed sample; they are not a database-schema guarantee.
              </p>
            </div>
          ) : null}

          {kind === "image" && assetUrl ? (
            <div className="rd-preview-image-stage"><img src={assetUrl} alt={title} /></div>
          ) : null}

          {kind === "document" && assetUrl ? (
            <iframe className="rd-preview-document" src={assetUrl} title={`${title} document`} />
          ) : null}

          {(kind === "image" || kind === "document" || kind === "file") && !assetUrl ? (
            <UnavailablePreview dataset={dataset} error="The evidence record exists, but no renderable backing URL is available." />
          ) : null}
        </div>

        <footer className="rd-preview-footer">
          <div className="rd-preview-footnote">
            {kind === "table" && rows.length ? `Observed sample · ${Math.min(rows.length, 12)} displayed · ${MAX_PREVIEW_ROWS}-row request` : null}
            {kind === "source" ? "Source record only · row-level contents not observed" : null}
            {(kind === "document" || kind === "image") && assetUrl ? "Backing evidence rendered from its current preview URL" : null}
          </div>
          <div className="rd-preview-actions">
            {kind === "table" ? (
              <>
                <button type="button" onClick={exportRows} disabled={!rows.length}>Export sample</button>
                {onAskAbout ? <button type="button" onClick={() => onAskAbout(dataset)}>Ask about data</button> : null}
                <button type="button" className="primary" onClick={() => dataset?.dataset_id && openQueryInNewTab(dataset.dataset_id)}>
                  Open query
                </button>
              </>
            ) : null}
            {kind === "source" ? (
              <>
                <button type="button" disabled={!externalUrl} onClick={() => openExternal(externalUrl)}>View source</button>
                {onAskAbout ? <button type="button" className="primary" onClick={() => onAskAbout(dataset)}>Ask about source</button> : null}
              </>
            ) : null}
            {(kind === "document" || kind === "image" || kind === "file") ? (
              <>
                {onAskAbout ? <button type="button" onClick={() => onAskAbout(dataset)}>Ask about evidence</button> : null}
                <button type="button" className="primary" disabled={!assetUrl} onClick={() => openExternal(assetUrl)}>Open original</button>
              </>
            ) : null}
          </div>
        </footer>
      </section>
      {onNext ? (
        <button type="button" className="rd-preview-adjacent next" onClick={onNext} aria-label="Preview next item">
          ›
        </button>
      ) : null}
    </div>
  );
}
