/**
 * Home Iteration 10 projection helpers — docs/HOME_FULL_SCALE_FREEZE_2026-07-16.md
 */

import { displayName, statusPill } from "./datasetMeta.js";
import { buildLab } from "./profileViewModel.js";
import { recentDatasets } from "./recent.js";
import { isHistoryNoise } from "./historyNoiseFence.js";

function purposeLine(ds) {
  return (
    ds?.summary ||
    ds?.description ||
    ds?.purpose ||
    [ds?.source, ds?.coverage, ds?.grain].filter(Boolean).join(" · ") ||
    "Research dataset in the lab vault"
  );
}

function folderLabel(value) {
  if (value == null || value === "") return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value === "object") {
    return (
      value.path ||
      value.name ||
      value.label ||
      value.folder ||
      value.id ||
      value.dataset_id ||
      ""
    );
  }
  return "";
}

function folderLocation(ds) {
  const folder = folderLabel(
    ds?.library_folder || ds?.folder || ds?.collection || ds?.estate_folder || "",
  );
  if (folder) return `LIBRARY / ${String(folder).replace(/_/g, " ").toUpperCase()}`;
  return "LIBRARY";
}

function formatHeadroom(pct) {
  if (!Number.isFinite(pct)) return "Capacity on file";
  return `${Math.max(0, Math.round(100 - pct))}% headroom`;
}

export function buildPickUp({ datasets = [], jobs = [], health } = {}) {
  const recent = recentDatasets(datasets, 2);
  // Prefer touched recent IDs; fall back to first holdings so Pick Up is never empty when the vault has assets.
  const primaryDs = recent[0] || datasets[0] || null;
  const secondaryDs =
    recent[1] ||
    (primaryDs && datasets.find((ds) => ds?.dataset_id && ds.dataset_id !== primaryDs.dataset_id)) ||
    null;
  const pendingJobs = jobs.filter((job) =>
    /pending|approval|hold/i.test(String(job.status || job.state || "")),
  );
  const pending = health?.desk?.jobs?.pending_approval ?? pendingJobs.length;
  const firstPending = pendingJobs[0];

  const primary = primaryDs
    ? {
        kind: "library_asset",
        id: primaryDs.dataset_id,
        title: displayName(primaryDs),
        stateSummary: purposeLine(primaryDs),
        location: folderLocation(primaryDs),
        pill: statusPill(primaryDs),
        dataset: primaryDs,
        action: "continue",
      }
    : null;

  let secondary = null;
  if (pending > 0 && firstPending) {
    secondary = {
      kind: "decision",
      id: firstPending.id || "approval",
      title:
        firstPending?.plan?.title ||
        firstPending?.title ||
        firstPending?.name ||
        "Procurement approval waiting",
      stateSummary: "Decision required before collection can continue.",
      location: "RESOURCES / APPROVALS",
      pill: `${pending} pending`,
      job: firstPending,
      action: "review",
      warn: true,
    };
  } else if (secondaryDs) {
    secondary = {
      kind: "library_asset",
      id: secondaryDs.dataset_id,
      title: displayName(secondaryDs),
      stateSummary: purposeLine(secondaryDs),
      location: folderLocation(secondaryDs),
      pill: statusPill(secondaryDs),
      dataset: secondaryDs,
      action: "continue",
    };
  }

  return { primary, secondary, pending };
}

function headroomPct(used, cap) {
  const u = Number(used);
  const c = Number(cap);
  if (!Number.isFinite(u) || !Number.isFinite(c) || c <= 0) return null;
  return Math.round((u / c) * 100);
}

export function buildResourceHeadroom(rollup) {
  const usage = rollup?.usage || {};
  const hero = rollup?.hero || {};
  const slots = [];

  const vault = usage.vault || hero.vault || {};
  if (vault.used_tb != null || vault.cap_tb != null) {
    const pct = vault.pct != null ? Number(vault.pct) : headroomPct(vault.used_tb, vault.cap_tb);
    const used = Number.isFinite(Number(vault.used_tb)) ? Number(vault.used_tb) : null;
    const cap = Number.isFinite(Number(vault.cap_tb)) ? Number(vault.cap_tb) : null;
    slots.push({
      id: "vault",
      name: vault.label || "GDrive vault",
      pinned: true,
      metric: `${used ?? "?"}/${cap ?? "?"} TB`,
      pct: Number.isFinite(pct) ? Math.round(pct) : null,
      headroom: formatHeadroom(pct),
      warn: pct != null && pct >= 75,
      action: "resources",
    });
  }

  const hot = usage.hot || {};
  const cache = usage.cache || {};
  if (hot.used_pct != null || hot.free_gb != null) {
    const pct = Number(hot.used_pct);
    const free =
      hot.free_gb != null && Number.isFinite(Number(hot.free_gb))
        ? Math.round(Number(hot.free_gb) * 10) / 10
        : null;
    slots.push({
      id: "hot",
      name: hot.label || "Working disk",
      pinned: false,
      metric: free != null ? `${free} GB free` : Number.isFinite(pct) ? `${Math.round(pct)}% used` : "Capacity",
      pct: Number.isFinite(pct) ? Math.round(pct) : null,
      headroom:
        Number.isFinite(pct) && pct >= 85 ? "Check →" : formatHeadroom(pct),
      warn: hot.headroom_ok === false || (Number.isFinite(pct) && pct >= 85),
      action: Number.isFinite(pct) && pct >= 85 ? "check" : "resources",
    });
  } else if (cache.used_gb != null || cache.total_gb != null) {
    const pct = cache.pct != null ? Number(cache.pct) : headroomPct(cache.used_gb, cache.total_gb);
    slots.push({
      id: "cache",
      name: cache.label || "USB bulk cache",
      pinned: false,
      metric: cache.total_gb
        ? `${cache.used_gb ?? "?"}/${cache.total_gb} GB`
        : "mounted",
      pct: Number.isFinite(pct) ? Math.round(pct) : null,
      headroom: formatHeadroom(pct),
      warn: pct != null && pct >= 85,
      action: "resources",
    });
  }

  return slots.slice(0, 2);
}

export function buildRecommendedEvidence(profile, { limit = 2 } = {}) {
  const lab = buildLab(profile);
  return (lab.suggested || []).slice(0, limit).map((item) => ({
    id: item.id,
    title: item.label,
    reason: item.reason || "recommended for current research",
    badge: item.action === "link" ? "IN LAB, NOT LINKED" : "NOT IN LAB YET",
    query: item.query,
    datasetId: item.datasetId,
    action: item.action === "link" ? "library" : "explore",
  }));
}

export function buildRecentTrail({ jobs = [], datasets = [], limit = 3 } = {}) {
  const material = [...jobs]
    .filter((job) => {
      const status = String(job.status || "");
      if (!/completed|registered|failed|cancelled|canceled|running|queued/i.test(status)) return false;
      return !isHistoryNoise({
        id: job.id,
        target: job?.plan?.title || job?.title || job?.name || job?.dataset_id,
        title: job?.plan?.title || job?.title || job?.name,
        summary: job.error || job.result?.summary || status,
        status,
        error: job.error,
        meta: { summary: job.error || job.result?.summary, status },
      });
    })
    .sort((a, b) => {
      const rank = (job) => {
        const s = String(job.status || "").toLowerCase();
        if (/registered|completed/.test(s)) return 0;
        if (/running|queued/.test(s)) return 1;
        if (/failed/.test(s)) return 2;
        return 3;
      };
      const byRank = rank(a) - rank(b);
      if (byRank !== 0) return byRank;
      return String(b.updated_at || b.created_at || "").localeCompare(
        String(a.updated_at || a.created_at || ""),
      );
    });

  const seen = new Set();
  const fromJobs = [];
  for (const job of material) {
    const status = String(job.status || "").toLowerCase();
    let kind = "PROCUREMENT";
    if (/registered|completed/.test(status)) kind = "COLLECTION COMPLETED";
    else if (/failed/.test(status)) kind = "COLLECTION FAILED";
    else if (/cancelled|canceled/.test(status)) kind = "COLLECTION CANCELLED";
    else if (/running|queued/.test(status)) kind = "REFRESH ADVANCED";
    const title =
      job?.plan?.title ||
      job?.title ||
      job?.name ||
      job?.dataset_id ||
      "Collection job";
    const key = `${kind}|${String(title).toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    fromJobs.push({
      id: job.id,
      kind,
      title,
      summary: String(job.error || job.result?.summary || status).replace(/_/g, " "),
      dest: /registered|completed/.test(status) ? "library" : "history",
    });
    if (fromJobs.length >= limit) break;
  }

  if (fromJobs.length) return fromJobs;

  return recentDatasets(datasets, limit).map((ds) => ({
    id: ds.dataset_id,
    kind: "REGISTERED ASSET",
    title: displayName(ds),
    summary: statusPill(ds),
    dest: "library",
    dataset: ds,
  }));
}
