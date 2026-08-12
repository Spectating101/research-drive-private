import { useEffect, useMemo, useState } from "react";
import { queryDataset } from "@/v2/api";
import { detailFields, displayName, statusPillKind } from "@/v2/datasetMeta";
import { StatusPill } from "@/v2/StatusPill";
import { PageShell } from "@/v2/ui";

function value(...candidates) {
  return candidates.map((item) => String(item || "").trim()).find(Boolean) || "Not declared";
}

function fieldNames(dataset, fields) {
  const declared = Array.isArray(dataset?.fields)
    ? dataset.fields
    : Array.isArray(dataset?.columns)
      ? dataset.columns.map((item) => (typeof item === "string" ? item : item?.name))
      : [];
  return [...new Set([...(fields.joinKeys || []), ...declared].filter(Boolean))].slice(0, 12);
}

function limitation(dataset, fields) {
  return value(
    dataset?.limitations,
    dataset?.caveats,
    fields.limitations,
    statusPillKind(dataset).kind === "registered"
      ? "Registration does not establish a verified local query path."
      : "The registry does not declare a material limitation for this asset.",
  );
}

function AssetOverlay({ kind, dataset, fields, onClose }) {
  if (!kind) return null;
  const title = kind === "fields" ? "Fields and operations" : "Source and provenance";
  const names = fieldNames(dataset, fields);
  return (
    <div className="rd-v2-library-overlay-scrim" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="rd-v2-library-overlay" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <div>
            <span className="rd-v2-eyebrow">Library inspection</span>
            <h2>{title}</h2>
          </div>
          <button type="button" className="rd-v2-btn sm" onClick={onClose} aria-label="Close inspection">Close</button>
        </header>
        {kind === "fields" ? (
          <>
            <p>Declared fields and operations for {displayName(dataset)}. They are registry metadata until a local preview is observed.</p>
            {names.length ? (
              <div className="rd-v2-library-field-list">
                {names.map((name) => <code key={name}>{name}</code>)}
              </div>
            ) : (
              <p className="rd-v2-library-muted">No declared fields are available in the current registry record.</p>
            )}
            <dl className="rd-v2-library-overlay-facts">
              <div><dt>Grain</dt><dd>{value(dataset?.grain)}</dd></div>
              <div><dt>Coverage</dt><dd>{value(fields.coverage, dataset?.coverage)}</dd></div>
              <div><dt>Join keys</dt><dd>{names.filter((name) => (fields.joinKeys || []).includes(name)).join(" · ") || "Not declared"}</dd></div>
            </dl>
          </>
        ) : (
          <>
            <p>Recorded provenance for this Library asset. This does not add verification beyond the declared state.</p>
            <dl className="rd-v2-library-overlay-facts">
              <div><dt>Source</dt><dd>{value(fields.source, dataset?.source, dataset?.publisher)}</dd></div>
              <div><dt>Verification state</dt><dd>{statusPillKind(dataset).label}</dd></div>
              <div><dt>Access route</dt><dd>{value(dataset?.collect_via, dataset?.backend, fields.access)}</dd></div>
              <div><dt>Coverage</dt><dd>{value(fields.coverage, dataset?.coverage)}</dd></div>
            </dl>
            <details className="rd-v2-library-tech-disclosure">
              <summary>Technical details</summary>
              <dl className="rd-v2-library-overlay-facts compact">
                <div><dt>Dataset ID</dt><dd><code>{dataset?.dataset_id || "Not declared"}</code></dd></div>
                <div><dt>Vault path</dt><dd><code>{fields.vault || "Not declared"}</code></dd></div>
              </dl>
            </details>
          </>
        )}
      </section>
    </div>
  );
}

function DataGlimpse({ dataset, enabled, onPreview }) {
  const [state, setState] = useState({ loading: false, rows: [], error: "" });
  useEffect(() => {
    let cancelled = false;
    if (!enabled || !dataset?.dataset_id) {
      setState({ loading: false, rows: [], error: "" });
      return undefined;
    }
    setState({ loading: true, rows: [], error: "" });
    queryDataset(dataset.dataset_id, 3)
      .then((payload) => {
        if (!cancelled) setState({ loading: false, rows: Array.isArray(payload?.rows) ? payload.rows : [], error: "" });
      })
      .catch(() => {
        if (!cancelled) setState({ loading: false, rows: [], error: "Preview is not available right now." });
      });
    return () => { cancelled = true; };
  }, [dataset?.dataset_id, enabled]);

  if (!enabled) return null;
  const columns = state.rows[0] ? Object.keys(state.rows[0]).slice(0, 5) : [];
  return (
    <section className="rd-v2-library-workspace-section" aria-label="Data glimpse">
      <div className="rd-v2-library-section-heading">
        <div><span className="rd-v2-eyebrow">Data glimpse</span><h2>Observed local sample</h2></div>
        <button type="button" className="rd-v2-btn sm" onClick={onPreview}>Preview rows</button>
      </div>
      {state.loading ? <p className="rd-v2-library-muted">Loading a bounded local sample…</p> : null}
      {!state.loading && state.error ? <p className="rd-v2-library-muted">{state.error}</p> : null}
      {!state.loading && !state.error && !state.rows.length ? <p className="rd-v2-library-muted">No sample rows were returned by the local query path.</p> : null}
      {columns.length ? (
        <div className="rd-v2-library-glimpse-table-wrap">
          <table className="rd-v2-library-glimpse-table">
            <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
            <tbody>{state.rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

export function LibraryAssetWorkspace({ dataset, onBack, onPreview, onAsk, onOpenQuery, onPrepare }) {
  const [overlay, setOverlay] = useState("");
  const fields = useMemo(() => detailFields(dataset), [dataset]);
  const state = statusPillKind(dataset);
  const canQuery = state.kind === "query-ready";
  const names = useMemo(() => fieldNames(dataset, fields), [dataset, fields]);
  const rowCount = dataset?.rows || dataset?.row_count || dataset?.num_rows || dataset?.records;
  const purpose = value(dataset?.recommended_use, dataset?.description, fields.use, "Research use is not described in the current registry metadata.");

  return (
    <PageShell
      className="rd-v2-library-workspace"
      title="Library"
      lead="Understand and use evidence the Library owns or is actively preparing."
      headExtra={<button type="button" className="rd-v2-btn sm" onClick={onBack}>← All Library assets</button>}
    >
      <article className="rd-v2-library-asset-canvas" data-testid="library-asset-workspace">
        <header className="rd-v2-library-asset-header">
          <div>
            <span className="rd-v2-eyebrow">Selected Library asset</span>
            <h1>{displayName(dataset)}</h1>
            <p>{value(dataset?.description, dataset?.summary, dataset?.recommended_use, "This asset has no plain-language description in the current registry.")}</p>
          </div>
          <StatusPill dataset={dataset} />
        </header>

        <div className="rd-v2-library-workspace-actions" aria-label="Asset actions">
          {canQuery ? <button type="button" className="rd-v2-btn primary" onClick={onOpenQuery}>Open query</button> : null}
          {canQuery ? <button type="button" className="rd-v2-btn" onClick={onPreview}>Preview rows</button> : null}
          <button type="button" className="rd-v2-btn" onClick={() => setOverlay("fields")}>View fields</button>
          <button type="button" className="rd-v2-btn" onClick={() => setOverlay("provenance")}>Source record</button>
          {!canQuery && state.kind === "registered" && onPrepare ? (
            <button type="button" className="rd-v2-btn primary" onClick={onPrepare}>Prepare local copy</button>
          ) : null}
          {!canQuery && onAsk ? <button type="button" className="rd-v2-btn" onClick={onAsk}>Ask about access</button> : null}
        </div>

        <section className="rd-v2-library-workspace-section" aria-label="What you have">
          <div className="rd-v2-library-section-heading"><div><span className="rd-v2-eyebrow">What you have</span><h2>Declared evidence shape</h2></div></div>
          <dl className="rd-v2-library-evidence-facts">
            <div><dt>Unit / grain</dt><dd>{value(dataset?.grain)}</dd></div>
            <div><dt>Period</dt><dd>{value(fields.coverage, dataset?.date_range, dataset?.temporal_coverage)}</dd></div>
            <div><dt>Scope</dt><dd>{value(dataset?.scope, dataset?.universe, dataset?.geography, dataset?.entity_universe)}</dd></div>
            <div><dt>Meaningful keys</dt><dd>{(fields.joinKeys || []).join(" · ") || "Not declared"}</dd></div>
            <div><dt>Declared scale</dt><dd>{rowCount ? `${rowCount} rows` : "Not declared"}</dd></div>
          </dl>
        </section>

        <div className="rd-v2-library-workspace-duo">
          <section className="rd-v2-library-workspace-section" aria-label="What this supports">
            <span className="rd-v2-eyebrow">What this supports</span>
            <h2>Research use</h2>
            <p>{purpose}</p>
          </section>
          <section className="rd-v2-library-workspace-section limitation" aria-label="What this does not establish">
            <span className="rd-v2-eyebrow">What this does not establish</span>
            <h2>Boundary</h2>
            <p>{limitation(dataset, fields)}</p>
          </section>
        </div>

        <DataGlimpse dataset={dataset} enabled={canQuery} onPreview={onPreview} />

        <section className="rd-v2-library-workspace-section" aria-label="Fields and operations">
          <div className="rd-v2-library-section-heading">
            <div><span className="rd-v2-eyebrow">Fields / operations</span><h2>Declared structure</h2></div>
            <button type="button" className="rd-v2-btn sm" onClick={() => setOverlay("fields")}>Inspect fields</button>
          </div>
          {names.length ? <div className="rd-v2-library-field-list">{names.slice(0, 8).map((name) => <code key={name}>{name}</code>)}</div> : <p className="rd-v2-library-muted">No declared field list is available yet.</p>}
        </section>
      </article>
      <AssetOverlay kind={overlay} dataset={dataset} fields={fields} onClose={() => setOverlay("")} />
    </PageShell>
  );
}
