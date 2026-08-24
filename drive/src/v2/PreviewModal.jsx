import { useEffect, useState } from "react";
import { downloadText, openQueryInNewTab, queryDataset, rowsToCsv } from "@/v2/api";
import { buildSchemaRows, displayName } from "@/v2/datasetMeta";
import { previewSampleRows } from "@/v2/deskSeed";

export function PreviewModal({
  open,
  dataset,
  mode = "lab",
  initialTab = "preview",
  usingSeed = false,
  onClose,
  onAskAbout,
}) {
  const [tab, setTab] = useState(initialTab);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [demoNotice, setDemoNotice] = useState("");

  useEffect(() => {
    if (!open) return;
    setTab(initialTab);
  }, [open, initialTab, dataset?.dataset_id]);

  useEffect(() => {
    if (!open || !dataset?.dataset_id) return;
    if (mode === "external") return;
    if (tab !== "preview" && tab !== "query") return;
    let cancelled = false;
    setLoading(true);
    setError("");
    setDemoNotice("");
    queryDataset(dataset.dataset_id, 25)
      .then((data) => {
        if (cancelled) return;
        const rows = data?.rows || [];
        setRows(rows);
        if (!rows.length) {
          const msg = data?.meta?.message || data?.message;
          if (msg) setError(String(msg));
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (usingSeed) {
          const sample = previewSampleRows(dataset);
          setRows(sample);
          setDemoNotice("Demo sample — connect the query engine for live rows.");
          setError("");
          return;
        }
        setRows([]);
        const msg = String(err?.message || "");
        if (/not present in the loaded query catalog|reconciliation|not query_ready|query_ready/i.test(msg)) {
          setError(
            "Registered in the vault, but not query-ready yet. Open Ask to hydrate from GDrive or reconcile the registry row.",
          );
        } else if (/Unauthorized|Desk access token/i.test(msg)) {
          setError("Desk session missing — reload after desk auth bootstrap.");
        } else {
          setError(msg || "Preview unavailable. The query engine may be offline.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, dataset?.dataset_id, tab, usingSeed, mode]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !dataset) return null;

  const isExternal = mode === "external";
  const cols = rows[0] ? Object.keys(rows[0]).slice(0, 8) : [];
  const schemaRows = buildSchemaRows(dataset, rows[0]);
  const sql = isExternal
    ? `-- External dataset — procure before querying\n-- ${dataset.dataset_id || dataset.title}`
    : `-- ${dataset.dataset_id}\nSELECT * FROM ${dataset.dataset_id} LIMIT 50`;

  return (
    <div className="rd-v2-preview-scrim" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="rd-v2-preview-modal" onClick={(e) => e.stopPropagation()}>
        <div className="rd-v2-preview-head">
          <strong>Preview — {displayName(dataset)}</strong>
          <button type="button" className="rd-v2-btn sm" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="rd-v2-preview-tabs">
          {["preview", "schema", ...(isExternal ? [] : ["query"])].map((t) => (
            <button
              key={t}
              type="button"
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t === "preview" ? "Preview" : t === "schema" ? "Schema" : "Query"}
            </button>
          ))}
        </div>
        <div className="rd-v2-preview-body">
          {tab === "preview" && (
            <>
              {isExternal ? (
                <div className="rd-v2-preview-ext-meta">
                  <p>
                    <strong>Publisher:</strong> {dataset.publisher || dataset.source || dataset.provider || dataset.collect_via || "—"}
                  </p>
                  <p>
                    <strong>Access:</strong> {dataset.access_mode || dataset.license || "See source terms"}
                  </p>
                  <p>
                    <strong>Preview status:</strong>{" "}
                    {dataset.source_preview?.status || (dataset.preview_supported ? "supported" : "metadata only")}
                  </p>
                  <p>
                    <strong>Coverage:</strong>{" "}
                    {Array.isArray(dataset.source_preview?.coverage)
                      ? dataset.source_preview.coverage.join(" · ")
                      : dataset.coverage || (Array.isArray(dataset.capabilities) ? dataset.capabilities.slice(0, 4).join(" · ") : "—")}
                  </p>
                  {dataset.source_preview?.notes ? <p>{dataset.source_preview.notes}</p> : null}
                  {dataset.description && !dataset.source_preview?.notes ? <p>{dataset.description}</p> : null}
                  {Array.isArray(dataset.source_preview?.sample_rows) && dataset.source_preview.sample_rows.length ? (
                    <table className="rd-v2-preview-table" aria-label="Source preview sample">
                      <thead>
                        <tr>
                          {Object.keys(dataset.source_preview.sample_rows[0] || {}).slice(0, 8).map((c) => (
                            <th key={c}>{c}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.source_preview.sample_rows.slice(0, 25).map((row, i) => (
                          <tr key={i}>
                            {Object.keys(dataset.source_preview.sample_rows[0] || {}).slice(0, 8).map((c) => (
                              <td key={c}>{String(row[c] ?? "")}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <p className="rd-v2-preview-muted">
                      {dataset.source_preview?.status === "schema_only"
                        ? "Schema/access facts only — no live sample claimed."
                        : dataset.source_preview?.status === "access_required"
                          ? "Access required before a bounded sample can be shown."
                          : "Bounded sample unavailable; Detail explains the next valid action."}
                    </p>
                  )}
                </div>
              ) : (
                <>
              {loading && <p className="rd-v2-preview-muted">Loading preview…</p>}
              {error && (
                <div className="rd-v2-preview-error">
                  <p>{error}</p>
                  <button type="button" className="rd-v2-btn sm" onClick={() => setTab("preview")}>
                    Retry
                  </button>
                  {onAskAbout ? (
                    <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout(dataset)}>
                      Ask about this
                    </button>
                  ) : null}
                </div>
              )}
              {demoNotice ? <p className="rd-v2-preview-demo">{demoNotice}</p> : null}
              {!loading && !error && rows.length === 0 && (
                <p className="rd-v2-preview-muted">No sample rows yet for this asset (vault/metadata-only, missing local file, or preview timed out). Try an instant dataset like SEC tickers or GDELT, or Ask to hydrate.</p>
              )}
              {rows.length > 0 && (
                <table className="rd-v2-preview-table">
                  <thead>
                    <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 25).map((row, i) => (
                      <tr key={i}>
                        {cols.map((c) => (
                          <td key={c}>{String(row[c] ?? "").slice(0, 80)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
                </>
              )}
            </>
          )}
          {tab === "schema" && (
            <table className="rd-v2-preview-table">
              <thead>
                <tr>
                  <th>Column</th>
                  <th>Type</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {schemaRows.map((r) => (
                  <tr key={r.name}>
                    <td>{r.name}</td>
                    <td>{r.type}</td>
                    <td>{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === "query" && (
            <>
              <textarea readOnly value={sql} rows={6} style={{ width: "100%", fontFamily: "monospace" }} />
              <p className="rd-v2-preview-muted small">
                Run uses the registry query engine on this dataset.
              </p>
              {error && <p className="rd-v2-preview-muted">{error}</p>}
            </>
          )}
        </div>
        <div className="rd-v2-preview-foot">
          {isExternal ? (
            <button type="button" className="rd-v2-btn sm" onClick={onClose}>
              Close
            </button>
          ) : (
            <>
          <button
            type="button"
            className="rd-v2-btn sm"
            disabled={!rows.length}
            onClick={() => {
              const csv = rowsToCsv(rows);
              if (csv) {
                downloadText(`${dataset.dataset_id}-preview.csv`, csv, "text/csv");
              }
            }}
          >
            Export CSV
          </button>
          <button
            type="button"
            className="rd-v2-btn sm primary"
            onClick={() => dataset?.dataset_id && openQueryInNewTab(dataset.dataset_id)}
          >
            Open query engine
          </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
