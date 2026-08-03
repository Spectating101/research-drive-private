/** Derive Home research-state briefing from observed jobs/assets/acquisitions only. */

import { recentDatasets } from "./recent.js";
import {
  displayName,
  isQueryReadyReadiness,
  isReceiptOnlyAsset,
  statusPillKind,
} from "./datasetMeta.js";

function jobTitle(job) {
  return (
    job?.plan?.title ||
    job?.title ||
    job?.name ||
    job?.dataset_id ||
    job?.type ||
    "Procurement job"
  );
}

function jobStatus(job) {
  return String(job?.status || job?.state || "").toLowerCase();
}

function isPendingJudgment(job) {
  return /pending|approval|hold|awaiting/.test(jobStatus(job));
}

function isFailedOrRecovery(job) {
  return /fail|error|recover|blocked|stalled/.test(jobStatus(job));
}

function isRunning(job) {
  return /run|active|collect|progress/.test(jobStatus(job));
}

function assetUpdatedAt(row) {
  const raw = row?.updated_at || row?.last_modified || row?.as_of || row?.generated_at;
  if (!raw) return 0;
  const time = new Date(raw).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function sortByUpdated(rows) {
  return [...rows].sort((a, b) => assetUpdatedAt(b) - assetUpdatedAt(a));
}

function isAnalysisReadyAsset(row) {
  return isQueryReadyReadiness(row?.analysis_readiness) && !isReceiptOnlyAsset(row);
}

function isOrdinaryHolding(row) {
  return Boolean(row) && !isReceiptOnlyAsset(row);
}

function pickContinueDataset(datasets, recent) {
  const ordered = [];
  const seen = new Set();
  for (const row of [...recent, ...datasets]) {
    const id = row?.dataset_id || row;
    if (!row || seen.has(id)) continue;
    seen.add(id);
    ordered.push(row);
  }
  return (
    ordered.find(isAnalysisReadyAsset) ||
    ordered.find((row) => isOrdinaryHolding(row) && statusPillKind(row).kind === "registered") ||
    ordered.find(isOrdinaryHolding) ||
    null
  );
}

function evidenceItem(row, { freshnessUnknown = false, receipt = false } = {}) {
  const pill = statusPillKind(row);
  const previewAllowed = isAnalysisReadyAsset(row);
  return {
    id: row.dataset_id,
    kind: receipt ? "receipt" : "asset",
    title: displayName(row),
    detail: row.dataset_id,
    metric: pill.label,
    dataset: row,
    tab: "library",
    previewAllowed,
    freshnessUnknown: freshnessUnknown || undefined,
  };
}

/**
 * @returns {{
 *   continueWork: object|null,
 *   needsJudgment: object[],
 *   evidence: object[],
 *   nextActions: object[],
 *   empty: { continue: boolean, judgment: boolean, evidence: boolean, actions: boolean }
 * }}
 */
export function buildHomeBriefing({
  datasets = [],
  jobs = [],
  acquisitions = [],
  health = null,
  profile = null,
} = {}) {
  const recent = recentDatasets(datasets, 5);
  const continueDs = pickContinueDataset(datasets, recent);
  const pendingJobs = jobs.filter(isPendingJudgment);
  const recoveryJobs = jobs.filter(isFailedOrRecovery);
  const runningJobs = jobs.filter(isRunning);
  const healthPending = health?.desk?.jobs?.pending_approval;
  const healthRunning = health?.desk?.jobs?.running;

  const continueWork = continueDs
    ? {
        id: continueDs.dataset_id,
        kind: "dataset",
        title: displayName(continueDs),
        detail: continueDs.dataset_id,
        readiness: statusPillKind(continueDs).label,
        dataset: continueDs,
        tab: "library",
        previewAllowed: isAnalysisReadyAsset(continueDs),
      }
    : null;

  const needsJudgment = [];
  for (const job of pendingJobs.slice(0, 4)) {
    needsJudgment.push({
      id: `job-${job.id || jobTitle(job)}`,
      kind: "approval",
      label: "Needs approval",
      title: jobTitle(job),
      detail: "Review source, cost, and vault destination before collection starts.",
      metric: String(job.status || job.state || "pending").replace(/_/g, " "),
      warn: true,
      tab: "browse",
      discoverFilter: "awaiting",
      job,
      resourceRow: {
        kind: "active",
        key: job.id ? `job-${job.id}` : "jobs-pending",
        label: jobTitle(job),
        metric: String(job.status || "pending").replace(/_/g, " "),
        section: "active",
        warn: true,
        ok: false,
        job,
      },
      prompt: `Review the pending procurement approval for ${jobTitle(job)}${job.id ? ` (job ${job.id})` : ""}.`,
    });
  }
  for (const job of recoveryJobs.slice(0, 2)) {
    if (needsJudgment.some((item) => item.job?.id && item.job.id === job.id)) continue;
    needsJudgment.push({
      id: `recover-${job.id || jobTitle(job)}`,
      kind: "recovery",
      label: "Needs recovery",
      title: jobTitle(job),
      detail: "Open Discover History to inspect the durable job record.",
      metric: String(job.status || job.state || "failed").replace(/_/g, " "),
      warn: true,
      tab: "browse",
      discoverMode: "history",
      job,
      prompt: `Explain recovery options for ${jobTitle(job)}.`,
    });
  }
  if (!pendingJobs.length && Number(healthPending) > 0) {
    needsJudgment.push({
      id: "approval-count",
      kind: "approval",
      label: "Needs approval",
      title: "Procurement approval waiting",
      detail: "Desk reports pending approval — open Discover to review.",
      metric: `${healthPending} pending`,
      warn: true,
      tab: "browse",
      discoverFilter: "awaiting",
      resourceRow: {
        kind: "active",
        key: "jobs-pending",
        label: "Procurement approval waiting",
        metric: `${healthPending} pending`,
        section: "active",
        warn: true,
        ok: false,
      },
      prompt: "Review pending procurement approvals on this desk.",
    });
  }

  const ordinaryHoldings = datasets.filter(isOrdinaryHolding);
  const datedOrdinary = sortByUpdated(
    ordinaryHoldings.filter((row) => assetUpdatedAt(row) > 0),
  );
  const readyFirst = [...datedOrdinary].sort((a, b) => {
    const readyDelta = Number(isAnalysisReadyAsset(b)) - Number(isAnalysisReadyAsset(a));
    if (readyDelta) return readyDelta;
    return assetUpdatedAt(b) - assetUpdatedAt(a);
  });
  const evidence = [];
  for (const row of readyFirst.slice(0, 4)) {
    evidence.push(evidenceItem(row));
  }
  if (!evidence.length && ordinaryHoldings.length) {
    for (const row of (recent.filter(isOrdinaryHolding).length
      ? recent.filter(isOrdinaryHolding)
      : ordinaryHoldings
    ).slice(0, 4)) {
      evidence.push(evidenceItem(row, { freshnessUnknown: true }));
    }
  }
  if (!evidence.length) {
    const receipts = sortByUpdated(datasets.filter(isReceiptOnlyAsset)).slice(0, 4);
    for (const row of receipts) {
      evidence.push(evidenceItem(row, { receipt: true, freshnessUnknown: assetUpdatedAt(row) <= 0 }));
    }
  }

  const liveAcquisitions = (acquisitions || []).filter((a) => (a.stage || "running") === "running");
  const nextActions = [];
  if (needsJudgment.some((item) => item.kind === "approval")) {
    nextActions.push({
      id: "review-approvals",
      label: "Review pending approvals",
      detail: "Discover holds the approval decision.",
      tab: "browse",
      discoverFilter: "awaiting",
    });
  }
  if (recoveryJobs.length) {
    nextActions.push({
      id: "open-history",
      label: "Open Discover History",
      detail: "Inspect failed or blocked jobs.",
      tab: "browse",
      discoverMode: "history",
    });
  }
  if (runningJobs.length || Number(healthRunning) > 0 || liveAcquisitions.length) {
    nextActions.push({
      id: "watch-runs",
      label: "Check running collections",
      detail: "Open Discover History for live job records.",
      tab: "browse",
      discoverMode: "history",
    });
  }
  if (continueWork) {
    nextActions.push({
      id: "continue-library",
      label: `Continue ${continueWork.title}`,
      detail: "Open the holding in Library.",
      tab: "library",
      dataset: continueWork.dataset,
    });
  } else if (datasets.length) {
    nextActions.push({
      id: "open-library",
      label: "Browse Library vault",
      detail: `${datasets.length} registered holding${datasets.length === 1 ? "" : "s"}.`,
      tab: "library",
    });
  } else {
    nextActions.push({
      id: "find-evidence",
      label: "Find missing evidence",
      detail: "Search registries from Discover.",
      tab: "browse",
    });
  }

  const profileGaps = (profile?.procurement_recommendations || [])
    .map((r) => r.search_query || r.title || r.prompt)
    .filter(Boolean)
    .slice(0, 2);
  for (const gap of profileGaps) {
    nextActions.push({
      id: `gap-${gap}`,
      label: `Search: ${gap}`,
      detail: "From research context recommendations.",
      tab: "browse",
      searchQuery: gap,
    });
  }

  return {
    continueWork,
    needsJudgment,
    evidence,
    nextActions: nextActions.slice(0, 5),
    empty: {
      continue: !continueWork,
      judgment: needsJudgment.length === 0,
      evidence: evidence.length === 0,
      actions: nextActions.length === 0,
    },
  };
}
