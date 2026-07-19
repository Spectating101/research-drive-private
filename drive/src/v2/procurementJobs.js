/** Bind cluster jobs to Discover candidates and normalize procure state. */

export function normalizedTitle(value) {
  return String(value || "").trim().toLowerCase();
}

export function jobTitle(job) {
  return job?.plan?.title || job?.plan?.dataset_id || job?.type || job?.id || "Collection job";
}

export function jobMatchesCandidate(job, candidate) {
  if (!job || !candidate) return false;
  const boundId = candidate.bound_job_id || candidate.job_id;
  if (boundId && job.id === boundId) return true;
  const jt = normalizedTitle(jobTitle(job));
  const ct = normalizedTitle(candidate.title || candidate.name || candidate.dataset_id);
  if (!jt || !ct) return false;
  return ct.includes(jt) || jt.includes(ct);
}

export function findJobForCandidate(candidate, jobs = []) {
  if (!candidate) return null;
  if (candidate.bound_job) return candidate.bound_job;
  const boundId = candidate.bound_job_id || candidate.job_id;
  if (boundId) {
    return jobs.find((j) => j.id === boundId) || candidate.bound_job || null;
  }
  if (candidate.kind === "job_pending") {
    return jobs.find((j) => jobMatchesCandidate(j, candidate)) || null;
  }
  return null;
}

export function jobToCandidateRow(job) {
  if (!job) return null;
  const title = jobTitle(job);
  return {
    kind: "job_pending",
    title,
    name: title,
    dataset_id: `job:${job.id}`,
    bound_job_id: job.id,
    bound_job: job,
    source: job.plan?.source || job.type || "cluster",
    description: `Pending approval · ${job.id}`,
    queued: true,
  };
}

export function jobToDiscoverHistoryEvent(job) {
  if (!job?.id) return null;
  const status = String(job.status || "queued");
  const title = jobTitle(job);
  const source = job.plan?.source || job.request?.source || job.connector_id || job.type || "Collection route";
  const summary =
    job.error ||
    job.message ||
    job.plan?.summary ||
    (status === "pending_approval"
      ? "Researcher approval is required before collection begins"
      : `${source} · ${status.replace(/_/g, " ")}`);
  return {
    id: `job:${job.id}`,
    ts: job.updated_at || job.created_at || job.submitted_at || "",
    action: status === "pending_approval" ? "intent" : "collection_run",
    kind: status === "pending_approval" ? "intent" : "collection_run",
    target: title,
    summary,
    status,
    meta: {
      status,
      kind: status === "pending_approval" ? "intent" : "collection_run",
      summary,
      job_id: job.id,
      candidate_key: job.candidate_key || job.request?.candidate_key,
      source_id: source,
    },
    durable: true,
  };
}

export function bindJobsToCandidates(rows, jobs = [], localBindings = {}) {
  return rows.map((row) => {
    const key = row.dataset_id || row.doi || row.title || row.url || row.name;
    const localJobId = key ? localBindings[key] : "";
    const boundId = localJobId || row.bound_job_id;
    if (!boundId) return row;
    const boundJob = jobs.find((j) => j.id === boundId) || row.bound_job;
    if (!boundJob) return { ...row, bound_job_id: boundId };
    return { ...row, bound_job_id: boundJob.id, bound_job: boundJob, queued: true };
  });
}

export function pendingApprovalJobs(jobs = []) {
  return jobs.filter((j) => j.status === "pending_approval");
}

export function pendingApprovalCount(jobs = []) {
  return pendingApprovalJobs(jobs).length;
}

export function activeProcurementJobs(jobs = []) {
  return jobs.filter((j) => ["pending_approval", "queued", "running"].includes(String(j.status || "")));
}
