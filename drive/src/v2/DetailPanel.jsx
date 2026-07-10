import { useState } from "react";
import { detailFields, displayName, formatMetaValue } from "@/v2/datasetMeta";
import { EmptyRailState } from "@/v2/EmptyRailState";
import {
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

function DetailSection({ label, defaultOpen = false, children }) {
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
      {open ? <div className="rd-v2-detail-section-body">{children}</div> : null}
    </div>
  );
}

function FieldRow({ label, value, loading, mono = false, hideEmpty = false }) {
  if (loading && value == null) {
    return (
      <div className="rd-v2-detail-row">
        <span className="rd-v2-detail-label">{label}</span>
        <FieldSkeleton />
      </div>
    );
  }
  if (hideEmpty && (value == null || value === "")) return null;
  const shown =
    value == null || value === "" ? <span className="rd-v2-field-empty">—</span> : value;
  return (
    <div className="rd-v2-detail-row">
      <span className="rd-v2-detail-label">{label}</span>
      <span className={`rd-v2-detail-val${mono ? " mono" : ""}`}>{shown}</span>
    </div>
  );
}

function isDatasetReady(readiness) {
  return /ready|query|instant|connected/i.test(String(readiness || ""));
}

function vaultPill(fields) {
  if (fields.vault || fields.access) return "local vault";
  return null;
}

function datasetFreshness(dataset) {
  const raw = dataset?.updated_at || dataset?.last_modified || dataset?.as_of || dataset?.generated_at;
  if (!raw) return "Registry current";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return formatMetaValue(raw);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function datasetProvenance(dataset) {
  return (
    dataset?.provenance ||
    dataset?.originating_job_id ||
    dataset?.job_id ||
    dataset?.collection?.job_id ||
    dataset?.collect_via ||
    dataset?.backend ||
    "Registered dataset record"
  );
}

export function DetailPanel({
  dataset,
  loading = false,
  onPreview,
  onAskAbout,
  onSeeCluster,
  onAddToLab,
}) {
  if (!dataset) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState />
        </div>
      </RailFrame>
    );
  }

  const fields = detailFields(dataset);
  const vaultLabel = vaultPill(fields);
  const grainLine = [formatMetaValue(dataset.grain), fields.joinKeys?.length ? fields.joinKeys.join(" + ") : null]
    .filter(Boolean)
    .join(" · ");

  return (
    <RailFrame>
      <RailEntityHeader
        id={dataset.dataset_id}
        title={displayName(dataset)}
        description={fields.description || null}
        pills={
          <>
            <StatusPill dataset={dataset} />
            {vaultLabel ? <span className="rd-v2-pill muted">{vaultLabel}</span> : null}
          </>
        }
      />

      <div className="rd-v2-rail-scroll">
        <section className="rd-v2-rail-value-brief" aria-label="Why this matters">
          <p className="rd-v2-rail-section-label">Why this matters</p>
          <p>
            {fields.use ||
              fields.description ||
              "Registered evidence can be inspected, queried, combined with related holdings, and reused without repeating collection work."}
          </p>
        </section>
        <div className="rd-v2-rail-fields" aria-label="Dataset fields">
          <FieldRow
            label="Source confidence"
            value={fields.source ? "High · registered source" : "Registered metadata"}
            loading={loading}
          />
          <FieldRow label="Freshness" value={datasetFreshness(dataset)} loading={loading} />
          <FieldRow label="Source" value={fields.source} loading={loading} />
          <FieldRow
            label="Access"
            value={fields.access || (isDatasetReady(dataset.analysis_readiness) ? "Query engine" : null)}
            loading={loading}
          />
          <FieldRow label="Coverage" value={fields.coverage || dataset.coverage || dataset.date_range} loading={loading} />
          <FieldRow label="Grain" value={grainLine || formatMetaValue(dataset.grain)} loading={loading} />
          <FieldRow label="Vault path" value={fields.vault} loading={loading} mono hideEmpty />
          <FieldRow label="Provenance" value={datasetProvenance(dataset)} loading={loading} />
          <FieldRow label="Use" value={fields.use} loading={loading} hideEmpty />
          <FieldRow label="Limitations" value={fields.limitations} loading={loading} hideEmpty />
          <FieldRow
            label="Next gap"
            value={fields.limitations || "Find complementary coverage"}
            loading={loading}
          />
          <FieldRow label="Readiness" value={formatMetaValue(dataset.analysis_readiness)} loading={loading} />
        </div>

        <DetailSection label="Schema & join keys">
          <div className="rd-v2-detail-row">
            <span className="rd-v2-detail-label">Join keys</span>
            <span className="rd-v2-detail-val">
              {loading && !fields.joinKeys ? <FieldSkeleton /> : <JoinKeyChips keys={fields.joinKeys} />}
            </span>
          </div>
          <FieldRow label="Partition" value={fields.partition} loading={loading} hideEmpty />
          <FieldRow
            label="Route"
            value={formatMetaValue(dataset.collect_via || dataset.backend || "local registry")}
            loading={loading}
          />
        </DetailSection>
      </div>

      <RailStickyFooter>
        <button type="button" className="rd-v2-btn primary sm" onClick={onPreview}>
          Preview rows
        </button>
        <button type="button" className="rd-v2-btn sm" onClick={onAskAbout}>
          Ask about this →
        </button>
        {onSeeCluster ? (
          <button type="button" className="rd-v2-btn sm" onClick={onSeeCluster}>
            See on Cluster →
          </button>
        ) : null}
        {onAddToLab ? (
          <button type="button" className="rd-v2-btn sm" onClick={() => onAddToLab(dataset)}>
            Add to lab
          </button>
        ) : null}
      </RailStickyFooter>
    </RailFrame>
  );
}
