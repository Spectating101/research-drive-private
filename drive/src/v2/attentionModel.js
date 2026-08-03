/**
 * Shared Attention vocabulary — Phase 1 truth.
 *
 * Home Attention = professor decisions only (approvals / holds).
 * Resources ops posture = capacity warnings + failed jobs (+ pending labeled as decisions).
 * Never use the same sentence for both surfaces.
 */

export function countOpsAttention({ issues = [], jobs = {} } = {}) {
  const issueCount = Array.isArray(issues) ? issues.length : Number(issues) || 0;
  const pending = Number(jobs.pending_approval ?? jobs.pending ?? 0);
  const actionable = jobs.actionable && typeof jobs.actionable === "object" ? jobs.actionable : {};
  // Prefer faculty-actionable failures — lifetime / ops-canary noise stays out of posture.
  const failed = Number(
    jobs.failed_actionable ?? actionable.failed_actionable ?? jobs.failed_recent ?? jobs.failed ?? 0,
  );
  const running = Number(jobs.running ?? 0);
  return {
    decisions: pending,
    opsWarnings: issueCount,
    failedJobs: failed,
    running,
    opsTotal: issueCount + failed,
  };
}

/** Professor-facing Home empty copy stays decision-scoped. */
export function homeAttentionEmptyCopy() {
  return "Nothing needs a decision right now.";
}

/**
 * Resources rail posture — never "N items need attention" when Home is clear of decisions.
 */
export function resourcesOpsPosture(counts) {
  const { decisions, opsWarnings, failedJobs, running } = counts;
  const parts = [];
  if (decisions > 0) {
    parts.push(`${decisions} awaiting your approval`);
  }
  if (failedJobs > 0) {
    parts.push(`${failedJobs} failed job${failedJobs === 1 ? "" : "s"}`);
  }
  if (opsWarnings > 0) {
    parts.push(`${opsWarnings} capacity warning${opsWarnings === 1 ? "" : "s"}`);
  }
  if (parts.length) return parts.join(" · ");
  if (running > 0) {
    return `${running} collection${running === 1 ? "" : "s"} running`;
  }
  return "Desk ready";
}

export function resourcesOpsPill(counts, queryUp) {
  if (queryUp === false) return { label: "Offline", warn: false };
  if (counts.decisions > 0) return { label: "Decision", warn: true };
  if (counts.opsTotal > 0) return { label: "Ops", warn: true };
  return { label: "Ready", warn: false };
}
