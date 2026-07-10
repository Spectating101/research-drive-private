/** Discover — what happens when the professor clicks Add to lab (no new visuals). */

import { discoverCandidateUrl } from "@/v2/discoverActions";

const ACTIVE_JOB = new Set(["pending_approval", "queued", "running"]);

export function discoverCollectPreflight({ target, probeResult, boundJob, destination }) {
  const connector = probeResult?.connector;
  const connectorId = connector?.connector_id || connector?.id;
  const spec = connector?.spec || {};
  const vaultPath =
    destination ||
    boundJob?.plan?.destination ||
    target?.destination ||
    spec.destination ||
    "collection/ (lab vault)";

  if (boundJob && ACTIVE_JOB.has(String(boundJob.status || ""))) {
    const needsApproval = boundJob.status === "pending_approval";
    return {
      connectorReady: true,
      connector: connectorId || boundJob.plan?.connector_id || "queued",
      onAdd: "Job already queued",
      approval: needsApproval ? "Awaiting your approval" : "Approved",
      destination: vaultPath,
      canAdd: false,
    };
  }

  const connectorReady = Boolean(connectorId);
  const canProbe = Boolean(discoverCandidateUrl(target));
  return {
    connectorReady,
    connector: connectorReady ? connectorId : canProbe ? "Probe source first" : "Source link required",
    onAdd: connectorReady
      ? "Queues collection job"
      : canProbe
        ? "Blocked until probe succeeds"
        : "Blocked until a source link is available",
    approval: connectorReady ? "Required before worker runs" : "—",
    destination: vaultPath,
    canAdd: connectorReady,
  };
}
