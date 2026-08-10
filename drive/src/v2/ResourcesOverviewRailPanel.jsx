import {
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";
import {
  countOpsAttention,
  resourcesOpsPill,
  resourcesOpsPosture,
} from "@/v2/attentionModel";

export function ResourcesOverviewRailPanel({ rollup, onViewActivity }) {
  if (rollup === null) {
    return (
      <RailFrame>
        <RailEntityHeader
          id="resources"
          title="Resources"
          description="Live desk capability data is unavailable."
          pills={<span className="rd-v2-pill warn">Not reported</span>}
        />
        <div className="rd-v2-rail-scroll">
          <RailFieldGrid>
            <RailField label="Status" value="Live capability data unavailable" />
            <RailField label="Source access" value="Not reported" />
            <RailField label="Workers & storage" value="Not reported" />
            <RailField label="Next" value="Use Refresh to check again" />
          </RailFieldGrid>
        </div>
      </RailFrame>
    );
  }

  const workers = rollup?.hero?.workers || {};
  const vault = rollup?.hero?.vault || {};
  const query = rollup?.hero?.query_engine || {};
  const jobs = rollup?.motion?.jobs || rollup?.hero?.jobs || {};
  const counts = countOpsAttention({
    issues: rollup?.issues || [],
    jobs,
  });
  const sourceCount = rollup?.connect?.source_count;
  const reportedSources = Array.isArray(rollup?.connect?.sources) ? rollup.connect.sources : [];
  const collectorCount = workers.online ?? workers.joined ?? workers.busy ?? workers.total;
  const collectorState = workers.total != null && collectorCount != null
    ? `${collectorCount}/${workers.total} ${workers.busy != null ? "busy" : "available"}`
    : collectorCount != null
      ? `${collectorCount} available`
      : "State pending";
  const vaultState = vault.used_tb != null
    ? `${vault.used_tb}/${vault.cap_tb ?? "?"} TB`
    : vault.cap_tb != null
      ? `${vault.cap_tb} TB capacity`
      : "Usage pending";
  const posture = resourcesOpsPosture(counts);
  const pill = resourcesOpsPill(counts, query.up);

  return (
    <RailFrame>
      <RailEntityHeader
        id="resources"
        title="Lab capacity"
        description="Access, current usage, and research capability across the lab."
        pills={
          <span className={`rd-v2-pill${pill.warn ? " warn" : ""}`}>
            {pill.label}
          </span>
        }
      />
      <div className="rd-v2-rail-scroll">
        <section className={`rd-v2-resource-posture${pill.warn ? " warn" : ""}`}>
          <span>Now</span>
          <strong>{posture}</strong>
          <p>
            {query.up === false
              ? "Catalog and query service is offline."
              : reportedSources.length
                ? `Access states are reported for ${reportedSources.length} desk routes.`
                : sourceCount != null
                  ? `${sourceCount} source routes are declared; individual access is not reported.`
                  : "Source routes and collection capacity are not reported."}
          </p>
        </section>
        <p className="rd-v2-rail-section-label">Current capacity</p>
        <RailFieldGrid>
          <RailField
            label="Ops issues"
            value={counts.opsTotal ? String(counts.opsTotal) : "Clear"}
          />
          <RailField
            label="Decisions"
            value={counts.decisions ? String(counts.decisions) : "None"}
          />
          <RailField label="Running" value={counts.running ? String(counts.running) : "None"} />
          <RailField label="Collectors" value={collectorState} />
          <RailField label="Vault" value={vaultState} />
          <RailField
            label="Source access"
            value={reportedSources.length ? `${reportedSources.length} routes reported` : "Not reported"}
          />
          <RailField label="Desk connection" value={query.up === false ? "Offline" : "Connected"} />
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        <button type="button" className="rd-v2-btn sm primary" onClick={() => onViewActivity?.(null)}>
          Open activity
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}
