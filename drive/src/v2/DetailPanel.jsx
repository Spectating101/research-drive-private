import { useEffect, useState } from "react";
import { fetchLiveIdentity } from "@/v2/api";
import { detailFields, displayName } from "@/v2/datasetMeta";
import { EmptyRailState } from "@/v2/EmptyRailState";
import { buildObjectEstateCrumb } from "@/v2/deskIntegration";
import { applyLiveIdentity, identityLookupFromRow } from "@/v2/liveIdentity";
import {
  RailDecisionSummary,
  RailEntityHeader,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";
import { StatusPill } from "@/v2/StatusPill";

function FieldSkeleton() {
  return (
    <div className="rd-v2-field-skeleton" aria-hidden>
      <div className="rd-v2-skel-line short" />
      <div className="rd-v2-skel-line" />
    </div>
  );
}

function JoinKeyChips({ keys }) {
  if (!keys?.length) return <span className="rd-v2-field-empty">—</span>;
  return (
    <span className="rd-v2-join-chips">
      {keys.map((k) => (
        <code key={k} className="rd-v2-join-chip">{k}</code>
      ))}
    </span>
  );
}

function DetailSection({ label, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rd-v2-detail-section">
      <button
        type="button"
        className="rd-v2-detail-section-hd"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span>{label}</span>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.15s" }}
          aria-hidden
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      {open ? <div className="rd-v2-detail-section-body">{children}</div> : null}
    </div>
  );
}

function FieldRow({ label, value, loading, mono = false }) {
  if (loading && value == null) return (
    <div className="rd-v2-detail-row">
      <span className="rd-v2-detail-label">{label}</span>
      <FieldSkeleton />
    </div>
  );
  const shown = value == null || value === "" ? <span className="rd-v2-field-empty">—</span> : value;
  return (
    <div className="rd-v2-detail-row">
      <span className="rd-v2-detail-label">{label}</span>
      <span className={`rd-v2-detail-val${mono ? " mono" : ""}`}>{shown}</span>
    </div>
  );
}

function GlanceRow({ label, value, mono = false }) {
  const shown = value == null || value === "" ? <span className="rd-v2-field-empty">—</span> : value;
  return (
    <div className="rd-v2-glance-row">
      <span>{label}</span>
      <strong className={mono ? "mono" : undefined}>{shown}</strong>
    </div>
  );
}

function AtAGlance({ dataset, fields }) {
  const estate = buildObjectEstateCrumb(dataset);
  const rowCount = dataset.rows || dataset.row_count || dataset.num_rows || dataset.records;
  const columnCount = dataset.columns || dataset.column_count || dataset.num_columns;
  const size = dataset.size || dataset.size_mb || dataset.size_gb || dataset.bytes;
  const owner = dataset.owner || dataset.publisher || dataset.domain;
  const rows = [
    ["Grain", dataset.grain || fields.partition],
    ["Coverage", fields.coverage || dataset.coverage || dataset.date_range],
    ["Source", fields.source],
    ["Location", estate.location || fields.vault || fields.access, true],
    ["Authority", estate.authority],
    ["Freshness", estate.freshness],
    ["Readiness", dataset.analysis_readiness || "unknown"],
    ["Rows", rowCount],
    ["Columns", columnCount],
    ["Owner", owner],
    ["Updated", dataset.updated_at || dataset.last_modified || dataset.as_of],
    ["Size", size],
  ].filter(([, value]) => value != null && value !== "");
  return (
    <section className="rd-v2-glance-list" aria-label="At a glance">
      <div className="rd-v2-rail-section-label">At a glance</div>
      {rows.map(([label, value, mono]) => (
        <GlanceRow key={label} label={label} value={value} mono={mono} />
      ))}
    </section>
  );
}

function EvidenceMap({ dataset, fields }) {
  const queryPath = dataset?.dataset_id ? `/query/${dataset.dataset_id}?limit=50` : "";
  const nodes = [
    ["Registry", dataset?.dataset_id || "not registered"],
    ["Vault", fields.vault || fields.access || "no vault path"],
    ["Source", fields.source || "unknown source"],
    ["Preview", queryPath || "select dataset"],
  ];
  return (
    <div className="rd-v2-evidence-map">
      <div className="rd-v2-evidence-head">
        <span>Evidence chain</span>
        <strong>{fields.joinKeys?.length ? `${fields.joinKeys.length} join keys` : "schema pending"}</strong>
      </div>
      <ol>
        {nodes.map(([label, value], i) => (
          <li key={label} className={i === 0 ? "on" : ""}>
            <span>{label}</span>
            <code>{value}</code>
          </li>
        ))}
      </ol>
    </div>
  );
}

function EvidenceFiles({ dataset, fields }) {
  const base = fields.vault || fields.access || dataset?.local_root || dataset?.dataset_id || "registry entry";
  const joins = fields.joinKeys?.length ? `${fields.joinKeys.length} join keys` : "schema pending";
  const files = [
    ["collection", base],
    ["manifest", dataset?.dataset_id ? `${dataset.dataset_id}.manifest.json` : "pending"],
    ["schema", joins],
    ["lineage", dataset?.source || fields.source || "registry metadata"],
  ];
  return (
    <section className="rd-v2-evidence-files" aria-label="Evidence and files">
      <div className="rd-v2-rail-section-label">Evidence & files</div>
      <ul>
        {files.map(([label, value]) => (
          <li key={label}>
            <span>{label}</span>
            <code>{value}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ProvenanceBlock({ dataset, fields }) {
  return (
    <section className="rd-v2-provenance-block" aria-label="Provenance">
      <div className="rd-v2-rail-section-label">Provenance</div>
      <GlanceRow label="Route" value={dataset.collect_via || dataset.backend || "local registry"} />
      <GlanceRow label="Source system" value={fields.source || dataset.source} />
      <GlanceRow label="Vault state" value={fields.vault ? "archived" : "registry metadata"} />
      <GlanceRow label="Upstream" value={dataset.upstream || dataset.source_url || dataset.url} mono />
    </section>
  );
}

function isDatasetReady(readiness) {
  return /ready|query|instant|connected/i.test(String(readiness || ""));
}

function datasetUseStatus(dataset, fields) {
  if (isDatasetReady(dataset.analysis_readiness)) return "Ready";
  return "Needs review";
}

function datasetPrimary(dataset, fields) {
  const ready = isDatasetReady(dataset.analysis_readiness);
  let line = ready ? "Yes — preview rows or ask questions" : "Not yet confirmed";
  if (fields.vault || fields.access) {
    line = ready ? `${line} · registered in vault` : `${line} · vault path pending review`;
  }
  return line;
}

function datasetRisk(dataset, fields) {
  if (isDatasetReady(dataset.analysis_readiness)) return "Low";
  return "Schema or access pending";
}

function datasetNextAction(dataset, fields) {
  if (fields.joinKeys?.length) {
    return "Preview rows, compare/join, or ask about coverage";
  }
  if (isDatasetReady(dataset.analysis_readiness)) {
    return "Preview rows or ask for schema/coverage";
  }
  return "Confirm schema and access before analysis";
}

export function DetailPanel({
  dataset,
  loading = false,
  onPreview,
  onAskAbout,
  onSeeCluster,
  onAddToLab,
}) {
  const [liveIdentity, setLiveIdentity] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const { datasetId, jobId } = identityLookupFromRow(dataset || {});
    if (!datasetId && !jobId) {
      setLiveIdentity(null);
      return undefined;
    }
    setLiveIdentity(null);
    fetchLiveIdentity({ datasetId, jobId })
      .then((identity) => {
        if (!cancelled) setLiveIdentity(identity);
      })
      .catch(() => {
        if (!cancelled) setLiveIdentity(null);
      });
    return () => {
      cancelled = true;
    };
  }, [dataset?.dataset_id, dataset?.job_id, dataset?.originating_job_id]);

  if (!dataset) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState />
        </div>
      </RailFrame>
    );
  }

  const view = applyLiveIdentity(dataset, liveIdentity) || dataset;
  const fields = detailFields(view);
  const identity = view.live_identity;

  return (
    <RailFrame>
      <RailEntityHeader
        id={view.dataset_id}
        title={displayName(view)}
        description={fields.description || null}
        pills={<StatusPill dataset={view} />}
      />

      <RailDecisionSummary
        status={datasetUseStatus(view, fields)}
        primary={datasetPrimary(view, fields)}
        risk={datasetRisk(view, fields)}
        next={datasetNextAction(view, fields)}
      />

      <div className="rd-v2-rail-scroll">
        <AtAGlance dataset={view} fields={fields} />
        <EvidenceFiles dataset={view} fields={fields} />
        <EvidenceMap dataset={view} fields={fields} />
        <ProvenanceBlock dataset={view} fields={fields} />

        {identity ? (
          <DetailSection label="Live identity" defaultOpen>
            <FieldRow label="Readiness" value={identity.synthesis_expectation?.badge || identity.readiness} />
            <FieldRow label="Worker" value={identity.worker_id} mono hideEmpty />
            <FieldRow label="Run" value={identity.run_id} mono hideEmpty />
            <FieldRow label="Attempt" value={identity.attempt ? String(identity.attempt) : null} hideEmpty />
            <FieldRow label="Job" value={identity.job_id} mono hideEmpty />
            <FieldRow label="Manifest" value={identity.manifest_id} mono hideEmpty />
            <FieldRow label="Vault" value={identity.vault_suffix} mono hideEmpty />
            <FieldRow
              label="Archive"
              value={
                identity.archive_verified == null
                  ? null
                  : identity.archive_verified
                    ? "Verified"
                    : "Unverified"
              }
              hideEmpty
            />
          </DetailSection>
        ) : null}

        <DetailSection label="Coverage">
          <FieldRow label="Period" value={fields.coverage || view.coverage} loading={loading} />
          <FieldRow label="Grain" value={view.grain} loading={loading} />
          <FieldRow label="Partition" value={fields.partition} loading={loading} />
        </DetailSection>

        <DetailSection label="Access">
          <FieldRow label="Source" value={fields.source} loading={loading} />
          <FieldRow label="Location" value={fields.access} loading={loading} mono />
          <FieldRow
            label="Readiness"
            value={identity?.synthesis_expectation?.badge || view.analysis_readiness}
            loading={loading}
          />
        </DetailSection>

        <DetailSection label="Schema">
          <div className="rd-v2-detail-row">
            <span className="rd-v2-detail-label">Join keys</span>
            <span className="rd-v2-detail-val">
              {loading && !fields.joinKeys ? <FieldSkeleton /> : <JoinKeyChips keys={fields.joinKeys} />}
            </span>
          </div>
          {fields.vault ? (
            <FieldRow label="Vault path" value={fields.vault} loading={loading} mono />
          ) : null}
        </DetailSection>

        {(fields.limitations || fields.use) ? (
          <DetailSection label="Notes" defaultOpen={false}>
            {fields.limitations ? <FieldRow label="Limitations" value={fields.limitations} loading={loading} /> : null}
            {fields.use ? <FieldRow label="Recommended use" value={fields.use} loading={loading} /> : null}
          </DetailSection>
        ) : null}
      </div>

      <RailStickyFooter>
        <button type="button" className="rd-v2-btn primary sm" onClick={() => onPreview?.(view)}>
          Preview rows
        </button>
        <button type="button" className="rd-v2-btn sm" onClick={() => onAskAbout?.(view)}>
          Ask about this →
        </button>
        {onSeeCluster ? (
          <button type="button" className="rd-v2-btn sm" onClick={() => onSeeCluster(view)}>
            See on Cluster →
          </button>
        ) : null}
        {onAddToLab ? (
          <button type="button" className="rd-v2-btn sm" onClick={() => onAddToLab(view)}>
            Add to lab
          </button>
        ) : null}
      </RailStickyFooter>
    </RailFrame>
  );
}
