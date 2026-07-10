import { computeDatasetOverlap } from "@/v2/clusterOverlap";
import { normalizedTitle } from "@/v2/procurementJobs";

function candidateAsDataset(target) {
  if (!target) return null;
  return {
    dataset_id: target.dataset_id,
    title: target.title || target.name,
    grain: target.grain,
    join_keys: target.join_keys || target.entity_fields || [],
    coverage: target.coverage || target.subtitle,
    description: target.description,
  };
}

function titleSimilarity(a, b) {
  const left = normalizedTitle(a);
  const right = normalizedTitle(b);
  if (!left || !right) return 0;
  if (left === right) return 100;
  if (left.includes(right) || right.includes(left)) return 72;
  const leftTokens = new Set(left.split(/[^a-z0-9]+/g).filter((t) => t.length > 2));
  const rightTokens = right.split(/[^a-z0-9]+/g).filter((t) => t.length > 2);
  if (!leftTokens.size || !rightTokens.length) return 0;
  let shared = 0;
  for (const token of rightTokens) {
    if (leftTokens.has(token)) shared += 1;
  }
  return Math.round((shared / Math.max(leftTokens.size, rightTokens.length)) * 100);
}

function bestLabMatch(target, catalog = [], labIds = new Set()) {
  const candidate = candidateAsDataset(target);
  if (!candidate) return null;

  if (target.dataset_id && labIds.has(target.dataset_id)) {
    const exact = catalog.find((d) => d.dataset_id === target.dataset_id);
    return {
      dataset: exact || { dataset_id: target.dataset_id, title: target.title },
      overlap: { pct: 100, label: "Already in lab", grainMatch: true, shared: [], join: "in lab" },
      reason: "Registered in vault",
    };
  }

  let best = null;
  for (const dataset of catalog) {
    const overlap = computeDatasetOverlap(candidate, dataset);
    const titlePct = titleSimilarity(candidate.title, dataset.name || dataset.title);
    const score = Math.max(overlap?.pct || 0, titlePct);
    if (!best || score > best.score) {
      best = { dataset, overlap, score, reason: score >= 70 ? "Strong title match" : "Partial registry overlap" };
    }
  }
  if (!best || best.score < 35) return null;
  const displayPct = Math.max(best.overlap?.pct || 0, best.score || 0);
  return {
    ...best,
    overlap: {
      ...(best.overlap || {}),
      pct: displayPct,
      label: best.overlap?.label || (displayPct >= 70 ? "Strong title match" : "Partial overlap"),
    },
  };
}

function profileFit(target, profile) {
  if (!profile || profile.unknown) {
    return { status: "unknown", label: "No faculty profile", detail: "Sign in with @yzu.edu.tw for ranked fit." };
  }
  const title = target?.title || target?.name || "";
  const recs = profile.procurement_recommendations || [];
  const match = recs.find((rec) => {
    const hay = [rec.title, rec.search_query, rec.query].map((s) => String(s || "").trim()).filter(Boolean);
    return hay.some((q) => titleSimilarity(title, q) >= 60);
  });
  if (match) {
    return {
      status: "match",
      label: "Profile recommended",
      detail: match.title || match.search_query || "Listed in faculty procurement stack",
    };
  }
  const tags = (profile.domain_tags || []).slice(0, 3);
  if (tags.length) {
    const tagHit = tags.some((tag) => normalizedTitle(title).includes(normalizedTitle(tag)));
    if (tagHit) {
      return { status: "partial", label: "Domain overlap", detail: `Touches profile tags: ${tags.join(", ")}` };
    }
  }
  return {
    status: "outside",
    label: "Outside profile stack",
    detail: "Not in procurement recommendations — verify before collecting.",
  };
}

function peerKey(row) {
  return row?.dataset_id || row?.doi || row?.title || row?.url || "";
}

function listAlternatives(target, peers = [], labIds = new Set()) {
  const selfKey = peerKey(target);
  return peers
    .filter((row) => {
      const key = peerKey(row);
      return key && key !== selfKey;
    })
    .slice(0, 4)
    .map((row) => ({
      key: peerKey(row),
      row,
      title: row.title || row.name || row.dataset_id || "Alternative",
      source: row.source || row.collect_via || "registry",
      inLab: Boolean(row.dataset_id && labIds.has(row.dataset_id)),
    }));
}

/** Compare a Discover candidate against lab holdings, faculty profile, and search peers. */
export function assessDiscoverCandidate({ target, catalog = [], profile = null, peers = [], labIds = new Set() }) {
  const labMatch = bestLabMatch(target, catalog, labIds);
  const facultyFit = profileFit(target, profile);
  const alternatives = listAlternatives(target, peers, labIds);

  let verdict = "New external source — probe and compare before collecting.";
  if (labMatch?.overlap?.pct >= 100) {
    verdict = "Already in lab — open Library instead of re-collecting.";
  } else if (labMatch?.score >= 70) {
    verdict = "Likely overlaps an existing lab dataset — confirm gap before collecting.";
  } else if (facultyFit.status === "match") {
    verdict = "Matches faculty procurement stack — good default to collect after probe.";
  } else if (alternatives.length > 1) {
    verdict = `${alternatives.length} alternatives in this search — compare sources before approving.`;
  }

  return {
    labMatch,
    profile: facultyFit,
    alternatives,
    verdict,
  };
}
