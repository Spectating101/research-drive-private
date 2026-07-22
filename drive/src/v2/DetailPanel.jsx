import { detailFields, displayName, formatMetaValue } from "@/v2/datasetMeta";
import { PAGE_DETAIL_EMPTY } from "@/v2/discoverRailPresentation";
import { EmptyRailState } from "@/v2/EmptyRailState";
import {
  RailActionFooter,
  RailEntityHeader,
  RailEvidenceDetails,
  RailFactSection,
  RailField,
  RailFrame,
  RailJudgment,
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

function isDatasetReady(readiness) {
  return /ready|query|instant|connected/i.test(String(readiness || ""));
}

function datasetFreshness(dataset) {
  const raw = dataset?.updated_at || dataset?.last_modified || dataset?.as_of || dataset?.generated_at;
  if (!raw) return "";
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
    ""
  );
}

function pushFact(list, label, value) {
  const text = value == null || value === "" ? "" : String(value).trim();
  if (!text || text === "—") return;
  list.push({ label, value: text });
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
          <EmptyRailState title={PAGE_DETAIL_EMPTY.library} minimal />
        </div>
      </RailFrame>
    );
  }

  const fields = detailFields(dataset);
  const ready = isDatasetReady(dataset.analysis_readiness);
  const grainLine = [formatMetaValue(dataset.grain), fields.joinKeys?.length ? fields.joinKeys.join(" + ") : null]
    .filter(Boolean)
    .join(" · ");
  const coverage = fields.coverage || dataset.coverage || dataset.date_range;
  const provenance = datasetProvenance(dataset);
  const freshness = datasetFreshness(dataset);

  const confirmed = [];
  pushFact(confirmed, "Readiness", formatMetaValue(dataset.analysis_readiness) || (ready ? "Query-ready" : "Registered"));
  pushFact(confirmed, "Grain", grainLine || formatMetaValue(dataset.grain));
  pushFact(confirmed, "Coverage", formatMetaValue(coverage));
  pushFact(confirmed, "Source", fields.source);
  pushFact(
    confirmed,
    "Access",
    fields.access || (ready ? "Query engine" : ""),
  );
  pushFact(confirmed, "Vault path", fields.vault);
  pushFact(confirmed, "Provenance", provenance);
  pushFact(confirmed, "Freshness", freshness);
  pushFact(confirmed, "Use", fields.use);

  const unknowns = [];
  if (!coverage) pushFact(unknowns, "Coverage", "Not reported");
  if (!grainLine && !dataset.grain) pushFact(unknowns, "Grain", "Not reported");
  if (!provenance) pushFact(unknowns, "Provenance", "Not reported beyond registry");
  if (fields.limitations) pushFact(unknowns, "Limitations", fields.limitations);

  const judgment = ready
    ? "Query-ready holding — open rows or reuse in Cluster / Synthesis."
    : fields.limitations
      ? `Registered holding — ${String(fields.limitations).slice(0, 120)}`
      : "Registered holding — inspect readiness and provenance before analysis.";

  const secondary = [];
  if (onAskAbout) {
    secondary.push({ key: "ask", label: "Ask about this →", onClick: onAskAbout });
  }
  if (onSeeCluster && secondary.length < 2) {
    secondary.push({ key: "cluster", label: "See on Cluster →", onClick: onSeeCluster });
  }

  return (
    <RailFrame>
      <RailEntityHeader
        compact
        id={dataset.dataset_id}
        title={displayName(dataset)}
        pills={<StatusPill dataset={dataset} />}
      />
      <RailJudgment>{judgment}</RailJudgment>
      <div className="rd-v2-rail-scroll">
        {loading && !confirmed.length ? (
          <div className="rd-v2-rail-fields" aria-label="Loading fields">
            <div className="rd-v2-detail-row">
              <span className="rd-v2-detail-label">Readiness</span>
              <FieldSkeleton />
            </div>
          </div>
        ) : (
          <>
            <RailFactSection title="Confirmed" items={confirmed} testId="rail-confirmed" />
            <RailFactSection title="Unknown" items={unknowns} testId="rail-unknown" />
          </>
        )}
        <RailEvidenceDetails label="Schema & join keys">
          <div className="rd-v2-detail-row">
            <span className="rd-v2-detail-label">Join keys</span>
            <span className="rd-v2-detail-val">
              {loading && !fields.joinKeys ? <FieldSkeleton /> : <JoinKeyChips keys={fields.joinKeys} />}
            </span>
          </div>
          {fields.partition ? <RailField label="Partition" value={fields.partition} /> : null}
          <RailField
            label="Route"
            value={formatMetaValue(dataset.collect_via || dataset.backend || "local registry")}
          />
        </RailEvidenceDetails>
      </div>
      <RailActionFooter
        primary={
          onPreview
            ? { key: "preview", label: "Preview rows", onClick: onPreview }
            : onAddToLab
              ? { key: "add", label: "Add to lab", onClick: () => onAddToLab(dataset) }
              : null
        }
        secondary={secondary}
      />
    </RailFrame>
  );
}
