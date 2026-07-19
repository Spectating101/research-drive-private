import {
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

function countJobs(jobs = {}) {
  const running = Number(jobs.running ?? 0);
  const pending = Number(jobs.pending_approval ?? jobs.pending ?? 0);
  const failed = Number(jobs.failed ?? 0);
  return { running, pending, failed };
}

export function ResourcesOverviewRailPanel({ rollup, onViewActivity }) {
  const workers = rollup?.hero?.workers || {};
  const vault = rollup?.hero?.vault || {};
  const query = rollup?.hero?.query_engine || {};
  const jobs = countJobs(rollup?.motion?.jobs || rollup?.hero?.jobs || {});
  const issueCount = Array.isArray(rollup?.issues) ? rollup.issues.length : 0;
  const attention = issueCount + jobs.pending + jobs.failed;
  const sourceCount = rollup?.connect?.source_count;
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
  const posture = attention > 0
    ? `${attention} item${attention === 1 ? "" : "s"} need attention`
    : jobs.running > 0
      ? `${jobs.running} collection${jobs.running === 1 ? "" : "s"} running`
      : "Desk ready";

  return (
    <RailFrame>
      <RailEntityHeader
        id="resources"
        title="Lab capacity"
        description="Access, current usage, and research capability across the lab."
        pills={
          <span className={`rd-v2-pill${attention > 0 ? " warn" : ""}`}>
            {attention > 0 ? "Attention" : query.up === false ? "Offline" : "Ready"}
          </span>
        }
      />
      <div className="rd-v2-rail-scroll">
        <section className={`rd-v2-resource-posture${attention > 0 ? " warn" : ""}`}>
          <span>Now</span>
          <strong>{posture}</strong>
          <p>
            {query.up === false
              ? "Catalog and query service is offline."
              : sourceCount != null
                ? `${sourceCount} source routes are reachable through the desk.`
                : "Source routes and collection capacity are available for inspection."}
          </p>
        </section>
        <p className="rd-v2-rail-section-label">Current capacity</p>
        <RailFieldGrid>
          <RailField label="Attention" value={attention ? String(attention) : "Clear"} />
          <RailField label="Running" value={jobs.running ? String(jobs.running) : "None"} />
          <RailField label="Collectors" value={collectorState} />
          <RailField label="Vault" value={vaultState} />
          <RailField label="Source reach" value={sourceCount != null ? `${sourceCount} routes` : "Configured routes"} />
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
