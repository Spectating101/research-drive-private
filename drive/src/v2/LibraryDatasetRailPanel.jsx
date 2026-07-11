import { detailFields, displayName, statusPillKind } from "@/v2/datasetMeta";
import { assetTypeLabel } from "@/v2/libraryEstate";
import { RailEntityHeader, RailFrame, RailStickyFooter } from "@/v2/RailFrame";
import { StatusPill } from "@/v2/StatusPill";

function decisionFor(dataset) {
  const state = statusPillKind(dataset);
  if (state.kind === "query-ready") {
    return {
      headline: "Query ready",
      body: "You can preview and query this dataset now.",
    };
  }
  if (state.kind === "connected") {
    return {
      headline: "Connected",
      body: "A live source connection exists. Instant local query access is not confirmed.",
    };
  }
  if (state.kind === "remote") {
    return {
      headline: "Metadata only",
      body: "This record supports discovery and acquisition. A queryable local asset is not confirmed.",
    };
  }
  if (state.kind === "queued") {
    return {
      headline: "Queued",
      body: "Acquisition or registration work is still pending.",
    };
  }
  if (state.kind === "warn") {
    return {
      headline: "Review required",
      body: "The current asset needs review before analysis.",
    };
  }
  if (state.kind === "failed") {
    return {
      headline: "Failed",
      body: "The current asset path failed and needs attention before use.",
    };
  }
  if (state.kind === "external") {
    return {
      headline: "External source",
      body: "This source is not confirmed as a usable local lab asset.",
    };
  }
  return {
    headline: "Readiness unknown",
    body: "Current metadata does not establish a usable query path.",
  };
}

function usefulFor(dataset) {
  const explicit = String(dataset?.recommended_use || dataset?.description || dataset?.subtitle || "").trim();
  if (explicit) return explicit;
  if (dataset?.grain) return `Research at ${dataset.grain} grain.`;
  return "Research purpose is not described in the current registry metadata.";
}

function unknowns(dataset, fields) {
  const out = [];
  if (!dataset?.updated_at && !dataset?.last_modified && !dataset?.as_of) {
    out.push("Freshness / last refresh not described");
  }
  if (!dataset?.limitations && !dataset?.caveats) out.push("Known caveats not described");
  if (!fields.joinKeys?.length) out.push("Join keys / schema relationship not described");
  if (!fields.coverage && !dataset?.coverage && !dataset?.date_range) out.push("Coverage not described");
  if (!fields.source && !dataset?.source && !dataset?.source_system) out.push("Source provenance not described");
  return out;
}

function Fact({ label, value, mono = false }) {
  if (value == null || value === "") return null;
  return (
    <div className="rd-v2-library-inspector-fact">
      <span>{label}</span>
      <strong className={mono ? "mono" : undefined}>{value}</strong>
    </div>
  );
}

function JoinKeys({ keys }) {
  if (!keys?.length) return null;
  return (
    <div className="rd-v2-library-inspector-joins">
      {keys.map((key) => <code key={key}>{key}</code>)}
    </div>
  );
}

export function LibraryDatasetRailPanel({ dataset, onPreview, onAskAbout }) {
  if (!dataset) return null;
  const fields = detailFields(dataset);
  const state = statusPillKind(dataset);
  const decision = decisionFor(dataset);
  const missing = unknowns(dataset, fields);
  const rowCount = dataset.rows || dataset.row_count || dataset.num_rows || dataset.records;
  const columnCount = dataset.columns || dataset.column_count || dataset.num_columns;
  const updated = dataset.updated_at || dataset.last_modified || dataset.as_of;
  const route = dataset.collect_via || dataset.backend;
  const canPreview = state.kind === "query-ready";

  return (
    <RailFrame>
      <RailEntityHeader
        title={displayName(dataset)}
        description={assetTypeLabel(dataset)}
        pills={<StatusPill dataset={dataset} />}
      />

      <section className={`rd-v2-library-inspector-decision rd-v2-library-inspector-decision-${state.kind}`} aria-label="Can I use this?">
        <p className="rd-v2-rail-section-label">Can I use this?</p>
        <h3>{decision.headline}</h3>
        <p>{decision.body}</p>
      </section>

      <div className="rd-v2-rail-scroll rd-v2-library-inspector-scroll">
        <section className="rd-v2-library-inspector-block" aria-label="Useful for">
          <p className="rd-v2-rail-section-label">Useful for</p>
          <p className="rd-v2-library-inspector-prose">{usefulFor(dataset)}</p>
        </section>

        {(fields.coverage || dataset.grain || rowCount || columnCount) ? (
          <section className="rd-v2-library-inspector-block" aria-label="Coverage and grain">
            <p className="rd-v2-rail-section-label">Coverage & grain</p>
            <div className="rd-v2-library-inspector-facts">
              <Fact label="Coverage" value={fields.coverage || dataset.coverage || dataset.date_range} />
              <Fact label="Grain" value={dataset.grain} />
              <Fact label="Rows" value={rowCount} />
              <Fact label="Columns" value={columnCount} />
            </div>
          </section>
        ) : null}

        {fields.joinKeys?.length ? (
          <section className="rd-v2-library-inspector-block" aria-label="Join keys">
            <p className="rd-v2-rail-section-label">Join keys</p>
            <JoinKeys keys={fields.joinKeys} />
          </section>
        ) : null}

        <section className="rd-v2-library-inspector-block" aria-label="Provenance">
          <p className="rd-v2-rail-section-label">Provenance</p>
          <div className="rd-v2-library-inspector-facts">
            <Fact label="Source" value={fields.source || dataset.source_system} />
            <Fact label="Route" value={route} />
            <Fact label="Vault state" value={fields.vault ? "Archived in lab" : "Local archive not confirmed"} />
            <Fact label="Updated" value={updated} />
          </div>
        </section>

        {missing.length ? (
          <section className="rd-v2-library-inspector-block rd-v2-library-inspector-unknown" aria-label="Still unknown">
            <p className="rd-v2-rail-section-label">Still unknown</p>
            <ul>
              {missing.map((item) => <li key={item}><span aria-hidden>?</span>{item}</li>)}
            </ul>
          </section>
        ) : null}

        <details className="rd-v2-library-inspector-tech">
          <summary>Technical details</summary>
          <div className="rd-v2-library-inspector-tech-body">
            <Fact label="Dataset ID" value={dataset.dataset_id} mono />
            <Fact label="Registry readiness" value={dataset.analysis_readiness || "not declared"} mono />
            <Fact label="Backend" value={dataset.backend} mono />
            <Fact label="Vault path" value={fields.vault} mono />
            <Fact label="Query path" value={dataset.dataset_id ? `/query/${dataset.dataset_id}?limit=50` : null} mono />
          </div>
        </details>
      </div>

      <RailStickyFooter>
        {canPreview ? (
          <>
            <button type="button" className="rd-v2-btn primary sm" onClick={onPreview}>Preview rows</button>
            <button type="button" className="rd-v2-btn sm" onClick={onAskAbout}>Ask about this →</button>
          </>
        ) : (
          <button type="button" className="rd-v2-btn primary sm" onClick={onAskAbout}>Ask about access →</button>
        )}
      </RailStickyFooter>
    </RailFrame>
  );
}
