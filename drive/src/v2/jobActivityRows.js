import { jobStatusLabel } from "@/v2/askArtifacts";
import { jobTitle } from "@/v2/procurementJobs";

const ACTIVE = new Set(["pending_approval", "queued", "running"]);

function jobProgressPct(job) {
  if (job == null) return null;
  if (typeof job.progress === "number" && Number.isFinite(job.progress)) {
    return Math.max(0, Math.min(100, Math.round(job.progress)));
  }
  const fromResult = job.result?.progress ?? job.result?.percent;
  if (typeof fromResult === "number") return Math.max(0, Math.min(100, Math.round(fromResult)));
  const text = String(job.metric || job.result?.gdelt_progress || "");
  const frac = text.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
  if (frac) {
    const den = Number(frac[2]);
    if (den > 0) return Math.round((Number(frac[1]) / den) * 100);
  }
  const pct = text.match(/(\d+(?:\.\d+)?)\s*%/);
  if (pct) return Math.max(0, Math.min(100, Math.round(Number(pct[1]))));
  if (job.status === "running") return null;
  if (job.status === "pending_approval") return 0;
  return null;
}

function fmtJobTime(job) {
  const raw = job.updated_at || job.created_at;
  if (!raw) return "Active now";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "Active now";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Inject live procurement jobs into the Activity run log when not already present. */
export function mergeJobsIntoActivity(activityRows = [], jobs = []) {
  const seen = new Set(
    activityRows
      .map((r) => r.event?.meta?.job_id || r.job?.id)
      .filter(Boolean),
  );

  const synthetic = jobs
    .filter((job) => ACTIVE.has(String(job.status || "")))
    .filter((job) => !seen.has(job.id))
    .map((job) => {
      const st = String(job.status || "");
      const progress = jobProgressPct(job);
      return {
        ok: st === "running" || st === "queued",
        warn: st === "pending_approval",
        kind: "activity",
        key: `job-live-${job.id}`,
        label: jobTitle(job),
        metric: jobStatusLabel(st),
        actionLabel: st === "pending_approval" ? "Awaiting approval" : "Collection job",
        sublabel: fmtJobTime(job),
        costLabel: progress != null ? `${progress}%` : "—",
        section: "activity",
        job,
        jobProgress: progress,
        event: {
          id: `job-live-${job.id}`,
          action: st === "pending_approval" ? "job_submit" : "job_approve",
          target: jobTitle(job),
          meta: { job_id: job.id, progress, status: st },
        },
      };
    });

  const priority = (row) => {
    const st = row.job?.status;
    if (st === "pending_approval") return 0;
    if (st === "running") return 1;
    return 2;
  };

  return [...synthetic.sort((a, b) => priority(a) - priority(b)), ...activityRows];
}
