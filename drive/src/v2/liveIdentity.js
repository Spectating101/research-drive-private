/** Apply RC2-A sanitized live identity onto desk rows without inventing readiness. */

export function liveIdentityBadge(identity) {
  const readiness = String(identity?.readiness || "").toLowerCase();
  if (readiness === "query_ready") return { kind: "query-ready", label: "Query ready" };
  if (readiness === "registered") return { kind: "registered", label: "Registered" };
  const expected = identity?.synthesis_expectation?.badge;
  if (expected) return { kind: readiness || "unknown", label: String(expected) };
  return null;
}

/**
 * Overlay authoritative production identity onto a catalog / detail row.
 * Does not invent query_ready when the factory only proved registration.
 */
export function applyLiveIdentity(dataset, identity) {
  if (!dataset || !identity) return dataset;
  const readiness = String(identity.readiness || "").trim();
  const badge = liveIdentityBadge(identity);
  return {
    ...dataset,
    dataset_id: identity.dataset_id || dataset.dataset_id,
    registry_id: identity.registry_id || dataset.registry_id,
    manifest_id: identity.manifest_id || dataset.manifest_id,
    job_id: identity.job_id || dataset.job_id || dataset.originating_job_id,
    run_id: identity.run_id || dataset.run_id,
    attempt: identity.attempt ?? dataset.attempt,
    worker_id: identity.worker_id || dataset.worker_id,
    analysis_readiness: readiness || dataset.analysis_readiness,
    live_identity: identity,
    live_identity_badge: badge,
    vault_path: identity.vault_suffix
      ? dataset.vault_path || dataset.local_root || identity.vault_suffix
      : dataset.vault_path || dataset.local_root,
  };
}

export function identityLookupFromRow(row = {}) {
  const datasetId = String(
    row.dataset_id || row.registry_id || row.meta?.dataset_id || row.event?.meta?.dataset_id || "",
  ).trim();
  const jobId = String(
    row.job_id || row.originating_job_id || row.meta?.job_id || row.event?.meta?.job_id || row.job?.id || "",
  ).trim();
  return {
    datasetId: datasetId || undefined,
    jobId: jobId || undefined,
  };
}
