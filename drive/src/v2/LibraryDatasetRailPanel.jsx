import { canIUseDecision, detailFields, displayName, statusPillKind } from "@/v2/datasetMeta";
import { assetTypeLabel } from "@/v2/libraryEstate";
import { RailEntityHeader, RailFrame, RailStickyFooter } from "@/v2/RailFrame";
import { StatusPill } from "@/v2/StatusPill";

export function decisionFor(dataset) {
  return canIUseDecision(dataset);
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

function sourceAuthorityLine(dataset, fields) {
  if (dataset?.self_provided || dataset?.upload) return "Self-provided";
  if (fields.source || dataset?.source || dataset?.source_system) {
    return fields.source || dataset.source || dataset.source_system;
  }
  if (dataset?.collect_via || dataset?.backend) return dataset.collect_via || dataset.backend;
  return "Source authority absent";
}

function verificationBlock(dataset) {
  const kind = statusPillKind(dataset).kind;
  if (kind === "query-ready") {
    return {
      headline: "Matched",
      body: "Archive and registry correspondence supports query use.",
      checks: ["Identifiers present", "Registry readiness declared", "Local query path available"],
      unknowns: [],
    };
  }
  if (dataset?.archive_verified === true) {
    return {
      headline: "Archived",
      body: "Vault archive confirmed. Query readiness may still be pending.",
      checks: ["Archive verified"],
      unknowns: ["Query readiness not confirmed"],
    };
  }
  if (kind === "connected") {
    return {
      headline: "Connected",
      body: "Source route is connected. Full verification is not complete.",
      checks: ["Route connected"],
      unknowns: ["Row-level correspondence not established"],
    };
  }
  return {
    headline: "Unverified",
    body: "Verification record is not established for this asset.",
    checks: [],
    unknowns: ["Source match", "Coverage correspondence", "Query readiness"],
  };
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
  const verification = verificationBlock(dataset);

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
        <section className="rd-v2-library-inspector-block" aria-label="Source" data-testid="library-rail-source">
          <p className="rd-v2-rail-section-label">Source</p>
          <h3 className="rd-v2-library-rail-module-title">{sourceAuthorityLine(dataset, fields)}</h3>
          <div className="rd-v2-library-inspector-facts">
            <Fact label="Route" value={route} />
            <Fact label="Vault" value={fields.vault ? "Archived in lab" : "Local archive not confirmed"} />
            <Fact label="Updated" value={updated} />
          </div>
        </section>

        <section className="rd-v2-library-inspector-block" aria-label="Verification" data-testid="library-rail-verification">
          <p className="rd-v2-rail-section-label">Verification</p>
          <h3 className="rd-v2-library-rail-module-title">{verification.headline}</h3>
          <p className="rd-v2-library-inspector-prose">{verification.body}</p>
          {verification.checks.length ? (
            <ul className="rd-v2-library-verify-list known">
              {verification.checks.map((item) => (
                <li key={item}><span aria-hidden>✓</span>{item}</li>
              ))}
            </ul>
          ) : null}
          {verification.unknowns.length ? (
            <ul className="rd-v2-library-verify-list unknown">
              {verification.unknowns.map((item) => (
                <li key={item}><span aria-hidden>?</span>{item}</li>
              ))}
            </ul>
          ) : null}
        </section>

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
