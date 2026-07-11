/**
 * Discover local sufficiency / equivalence authority.
 *
 * Honest comparison of an external (or needs-access) candidate against the
 * lab catalog. Does not use title similarity or lexical search scores.
 *
 * States:
 *   exact-local | partial-local | related-local |
 *   no-local-alternative | comparison-unknown
 *
 * likely-equivalent is intentionally unsupported until the backend exposes
 * an explicit equivalence contract (canonical family + matching coverage).
 */

export const SUFFICIENCY = Object.freeze({
  EXACT_LOCAL: "exact-local",
  LIKELY_EQUIVALENT: "likely-equivalent",
  PARTIAL_LOCAL: "partial-local",
  RELATED_LOCAL: "related-local",
  NO_LOCAL_ALTERNATIVE: "no-local-alternative",
  COMPARISON_UNKNOWN: "comparison-unknown",
});

const LABELS = Object.freeze({
  [SUFFICIENCY.EXACT_LOCAL]: "Exact local match",
  [SUFFICIENCY.LIKELY_EQUIVALENT]: "Likely equivalent",
  [SUFFICIENCY.PARTIAL_LOCAL]: "Partial local coverage",
  [SUFFICIENCY.RELATED_LOCAL]: "Related lab asset",
  [SUFFICIENCY.NO_LOCAL_ALTERNATIVE]: "No local alternative found",
  [SUFFICIENCY.COMPARISON_UNKNOWN]: "Local comparison unavailable",
});

function lower(v) {
  return String(v || "")
    .trim()
    .toLowerCase();
}

function labTitle(row) {
  return String(row?.title || row?.name || row?.dataset_id || "Local dataset").trim();
}

function labId(row) {
  return String(row?.dataset_id || row?.id || "").trim();
}

function normalizeGrain(v) {
  return lower(v).replace(/[_\s-]+/g, " ").trim();
}

function coverageText(row) {
  return String(row?.coverage || row?.date_range || row?.temporal_coverage || "").trim();
}

function sourceIdentity(row) {
  return lower(row?.source_system || row?.source_id || row?.source || row?.publisher || row?.collect_via);
}

function joinKeySet(row) {
  const keys = row?.join_keys || row?.entity_fields || [];
  if (!Array.isArray(keys)) return new Set();
  return new Set(keys.map((k) => lower(k)).filter(Boolean));
}

function sharedJoinKeys(a, b) {
  const left = joinKeySet(a);
  const right = joinKeySet(b);
  if (!left.size || !right.size) return [];
  return [...left].filter((k) => right.has(k));
}

/**
 * Comparable identity signals on a candidate — without these we cannot claim
 * "no local alternative"; the comparison is unknown.
 */
export function candidateComparableSignals(candidate) {
  const signals = [];
  if (candidate?.dataset_id) signals.push("dataset_id");
  if (candidate?.doi) signals.push("doi");
  if (candidate?.equivalent_dataset_id || candidate?.local_equivalent_id) signals.push("explicit_equivalent");
  if (Array.isArray(candidate?.related_dataset_ids) && candidate.related_dataset_ids.length) {
    signals.push("related_dataset_ids");
  }
  if (sourceIdentity(candidate)) signals.push("source_identity");
  if (joinKeySet(candidate).size) signals.push("join_keys");
  if (normalizeGrain(candidate?.grain)) signals.push("grain");
  if (coverageText(candidate)) signals.push("temporal_coverage");
  return signals;
}

function unknownResult({ reason, comparisonComplete = false } = {}) {
  return {
    state: SUFFICIENCY.COMPARISON_UNKNOWN,
    label: LABELS[SUFFICIENCY.COMPARISON_UNKNOWN],
    summary: reason || "Local comparison could not be completed with the available metadata.",
    localMatches: [],
    bestLocal: null,
    basis: [],
    differences: [],
    comparisonComplete: Boolean(comparisonComplete),
    browseLine: LABELS[SUFFICIENCY.COMPARISON_UNKNOWN],
    focusHeadline: LABELS[SUFFICIENCY.COMPARISON_UNKNOWN],
    focusBody: reason || "Local comparison could not be completed with the available metadata.",
    primaryActionHint: null,
    secondaryActionHint: null,
  };
}

function noneResult() {
  return {
    state: SUFFICIENCY.NO_LOCAL_ALTERNATIVE,
    label: LABELS[SUFFICIENCY.NO_LOCAL_ALTERNATIVE],
    summary: "The completed local comparison found no qualifying lab asset.",
    localMatches: [],
    bestLocal: null,
    basis: [],
    differences: [],
    comparisonComplete: true,
    browseLine: LABELS[SUFFICIENCY.NO_LOCAL_ALTERNATIVE],
    focusHeadline: LABELS[SUFFICIENCY.NO_LOCAL_ALTERNATIVE],
    focusBody: "The completed local comparison found no qualifying lab asset.",
    primaryActionHint: null,
    secondaryActionHint: null,
  };
}

function exactMatch(lab) {
  const title = labTitle(lab);
  const ready = lower(lab.analysis_readiness) === "instant" || lab.local_ready === true;
  return {
    state: SUFFICIENCY.EXACT_LOCAL,
    label: LABELS[SUFFICIENCY.EXACT_LOCAL],
    summary: ready
      ? `${title} is already in your lab and query ready.`
      : `${title} is already in your lab.`,
    localMatches: [lab],
    bestLocal: lab,
    basis: [{ dimension: "canonical_identity", relation: "same" }],
    differences: [],
    comparisonComplete: true,
    browseLine: `${LABELS[SUFFICIENCY.EXACT_LOCAL]} · ${title}`,
    focusHeadline: LABELS[SUFFICIENCY.EXACT_LOCAL],
    focusBody: ready
      ? `${title} is already in your lab and query ready.`
      : `${title} is already in your lab.`,
    primaryActionHint: { id: "open_local", label: "Open local dataset" },
    secondaryActionHint: null,
  };
}

function coverageGapSummary(localCov, candCov) {
  if (!localCov || !candCov || lower(localCov) === lower(candCov)) return null;
  return {
    dimension: "temporal_coverage",
    local: localCov,
    candidate: candCov,
    summary: `Local: ${localCov} · Candidate: ${candCov}`,
  };
}

function grainGapSummary(localGrain, candGrain) {
  const a = normalizeGrain(localGrain);
  const b = normalizeGrain(candGrain);
  if (!a || !b || a === b) return null;
  return {
    dimension: "grain",
    local: localGrain,
    candidate: candGrain,
    summary: `Local grain: ${localGrain} · Candidate grain: ${candGrain}`,
  };
}

function relatedOrPartial(lab, candidate, basis) {
  const diffs = [];
  const covGap = coverageGapSummary(coverageText(lab), coverageText(candidate));
  if (covGap) diffs.push(covGap);
  const grainGap = grainGapSummary(lab?.grain, candidate?.grain);
  if (grainGap) diffs.push(grainGap);

  const title = labTitle(lab);
  if (diffs.length) {
    const gapLine = diffs.map((d) => d.summary).join("; ");
    const shortGap =
      diffs[0].dimension === "temporal_coverage"
        ? `Local data covers ${diffs[0].local}`
        : diffs[0].dimension === "grain"
          ? `${diffs[0].local}, candidate is ${diffs[0].candidate}`
          : diffs[0].summary;
    return {
      state: SUFFICIENCY.PARTIAL_LOCAL,
      label: LABELS[SUFFICIENCY.PARTIAL_LOCAL],
      summary: `A related local asset covers part of this need. ${gapLine}`,
      localMatches: [lab],
      bestLocal: lab,
      basis,
      differences: diffs,
      comparisonComplete: true,
      browseLine: `${LABELS[SUFFICIENCY.PARTIAL_LOCAL]} · ${shortGap}`,
      focusHeadline: LABELS[SUFFICIENCY.PARTIAL_LOCAL],
      focusBody: `A related local panel covers ${coverageText(lab) || normalizeGrain(lab?.grain) || "a subset"}. This candidate covers ${coverageText(candidate) || normalizeGrain(candidate?.grain) || "a different range"}.`,
      gapLines: diffs.map((d) => d.summary),
      primaryActionHint: null,
      secondaryActionHint: { id: "open_local", label: "Open local dataset" },
    };
  }

  const basisNote =
    basis.find((b) => b.dimension === "source_identity")?.note ||
    basis.find((b) => b.dimension === "join_keys")?.note ||
    basis.find((b) => b.dimension === "related_dataset_ids")?.note ||
    "Shared research object";

  return {
    state: SUFFICIENCY.RELATED_LOCAL,
    label: LABELS[SUFFICIENCY.RELATED_LOCAL],
    summary: `The lab has a dataset for the same research object, but equivalence is not established.`,
    localMatches: [lab],
    bestLocal: lab,
    basis,
    differences: [],
    comparisonComplete: true,
    browseLine: `${LABELS[SUFFICIENCY.RELATED_LOCAL]} · ${basisNote}`,
    focusHeadline: LABELS[SUFFICIENCY.RELATED_LOCAL],
    focusBody: `The lab has ${title} for the same research object, but equivalence is not established.`,
    primaryActionHint: null,
    secondaryActionHint: { id: "inspect_related", label: "Inspect related lab asset" },
  };
}

function findExact(candidate, catalog) {
  const id = String(candidate?.dataset_id || "").trim();
  const doi = lower(candidate?.doi);
  const equiv = String(
    candidate?.equivalent_dataset_id || candidate?.local_equivalent_id || "",
  ).trim();
  const key = lower(candidate?.candidate_key);

  for (const lab of catalog) {
    const lid = labId(lab);
    if (!lid) continue;
    if (id && lid === id) return lab;
    if (equiv && lid === equiv) return lab;
    if (doi && lower(lab.doi) && lower(lab.doi) === doi) return lab;
    if (key && (key === `dataset:${lower(lid)}` || key === lower(lab.candidate_key))) return lab;
  }
  return null;
}

function relationBasis(candidate, lab) {
  const basis = [];
  const relatedIds = Array.isArray(candidate?.related_dataset_ids)
    ? candidate.related_dataset_ids.map((x) => String(x))
    : [];
  const lid = labId(lab);
  if (lid && relatedIds.includes(lid)) {
    basis.push({
      dimension: "related_dataset_ids",
      relation: "explicit",
      note: "Explicit related dataset",
    });
  }

  const candSrc = sourceIdentity(candidate);
  const labSrc = sourceIdentity(lab);
  if (candSrc && labSrc && (candSrc === labSrc || labSrc.includes(candSrc) || candSrc.includes(labSrc))) {
    basis.push({
      dimension: "source_identity",
      relation: "same",
      note: "Same source family",
    });
  }

  const shared = sharedJoinKeys(candidate, lab);
  const minKeys = Math.min(joinKeySet(candidate).size, joinKeySet(lab).size);
  if (shared.length && (shared.length >= 2 || (minKeys > 0 && shared.length === minKeys))) {
    basis.push({
      dimension: "join_keys",
      relation: "overlap",
      note: "Same issuer universe",
      keys: shared,
    });
  }

  return basis;
}

/**
 * Ranked local matches that share an honest relationship (not title).
 */
function findRelated(candidate, catalog) {
  const scored = [];
  for (const lab of catalog) {
    const basis = relationBasis(candidate, lab);
    if (!basis.length) continue;
    // Prefer explicit related ids, then source identity, then join keys.
    const rank =
      (basis.some((b) => b.dimension === "related_dataset_ids") ? 300 : 0) +
      (basis.some((b) => b.dimension === "source_identity") ? 200 : 0) +
      (basis.some((b) => b.dimension === "join_keys") ? 100 + (basis.find((b) => b.keys)?.keys?.length || 0) : 0);
    scored.push({ lab, basis, rank });
  }
  scored.sort((a, b) => b.rank - a.rank);
  return scored;
}

/**
 * Consume an optional backend local_comparison object when present and complete.
 * Never invents title/score equivalence.
 */
export function sufficiencyFromBackend(localComparison, catalog = []) {
  if (!localComparison || typeof localComparison !== "object") return null;
  const complete = localComparison.comparison_complete !== false;
  const stateRaw = lower(localComparison.state || localComparison.sufficiency_state).replace(
    /_/g,
    "-",
  );
  const ids = localComparison.local_dataset_ids || [];
  const bestId = ids[0] || localComparison.local_dataset_id || null;
  const bestLocal =
    (bestId && catalog.find((d) => labId(d) === String(bestId))) ||
    (bestId ? { dataset_id: bestId, name: bestId } : null);

  const map = {
    "exact-local": SUFFICIENCY.EXACT_LOCAL,
    exact: SUFFICIENCY.EXACT_LOCAL,
    "likely-equivalent": SUFFICIENCY.LIKELY_EQUIVALENT,
    "partial-local": SUFFICIENCY.PARTIAL_LOCAL,
    partial: SUFFICIENCY.PARTIAL_LOCAL,
    "related-local": SUFFICIENCY.RELATED_LOCAL,
    related: SUFFICIENCY.RELATED_LOCAL,
    "no-local-alternative": SUFFICIENCY.NO_LOCAL_ALTERNATIVE,
    none: SUFFICIENCY.NO_LOCAL_ALTERNATIVE,
    "comparison-unknown": SUFFICIENCY.COMPARISON_UNKNOWN,
    unknown: SUFFICIENCY.COMPARISON_UNKNOWN,
  };
  const state = map[stateRaw];
  if (!state) return null;
  const basis = localComparison.basis || [];
  if (state === SUFFICIENCY.LIKELY_EQUIVALENT) {
    // Accept only when backend sent explicit equivalence evidence.
    const hasExplicit = basis.some((b) =>
      /equivalent|canonical|same.?series|explicit/i.test(
        `${b.dimension || ""} ${b.relation || ""}`,
      ),
    );
    if (!hasExplicit) return null;
  }
  if (!complete && state !== SUFFICIENCY.COMPARISON_UNKNOWN) {
    return unknownResult({ reason: "Local comparison did not complete." });
  }
  if (state === SUFFICIENCY.EXACT_LOCAL && bestLocal) return exactMatch(bestLocal);
  if (state === SUFFICIENCY.NO_LOCAL_ALTERNATIVE) return noneResult();
  if (state === SUFFICIENCY.COMPARISON_UNKNOWN) {
    return unknownResult({
      reason: localComparison.summary || "Local comparison unavailable.",
      comparisonComplete: complete,
    });
  }
  if (state === SUFFICIENCY.LIKELY_EQUIVALENT && bestLocal) {
    const title = labTitle(bestLocal);
    return {
      state: SUFFICIENCY.LIKELY_EQUIVALENT,
      label: LABELS[SUFFICIENCY.LIKELY_EQUIVALENT],
      summary:
        localComparison.summary ||
        `${title} is treated as equivalent by an explicit backend relation.`,
      localMatches: [bestLocal],
      bestLocal,
      basis,
      differences: localComparison.differences || [],
      comparisonComplete: true,
      browseLine: `${LABELS[SUFFICIENCY.LIKELY_EQUIVALENT]} · ${title}`,
      focusHeadline: LABELS[SUFFICIENCY.LIKELY_EQUIVALENT],
      focusBody:
        localComparison.summary ||
        `${title} is treated as equivalent by an explicit backend relation.`,
      primaryActionHint: { id: "open_local", label: "Open local dataset" },
      secondaryActionHint: null,
    };
  }
  // Rebuild partial/related presentation from backend diffs when possible.
  if (bestLocal && (state === SUFFICIENCY.PARTIAL_LOCAL || state === SUFFICIENCY.RELATED_LOCAL)) {
    const fakeCandidate = {
      grain: (localComparison.differences || []).find((d) => d.dimension === "grain")?.candidate,
      coverage: (localComparison.differences || []).find((d) => d.dimension === "temporal_coverage")
        ?.candidate,
    };
    const basis = localComparison.basis || [{ dimension: "dataset_family", relation: "same" }];
    if (state === SUFFICIENCY.PARTIAL_LOCAL) {
      const built = relatedOrPartial(bestLocal, fakeCandidate, basis);
      if (Array.isArray(localComparison.differences) && localComparison.differences.length) {
        built.differences = localComparison.differences;
        built.gapLines = localComparison.differences.map(
          (d) => d.summary || `${d.dimension}: ${d.local} vs ${d.candidate}`,
        );
        built.browseLine = `${LABELS[SUFFICIENCY.PARTIAL_LOCAL]} · ${built.gapLines[0]}`;
      }
      return built;
    }
    return relatedOrPartial(bestLocal, {}, basis);
  }
  return null;
}

/**
 * Assess local sufficiency for a Discover candidate against the lab catalog.
 *
 * @param {object} candidate
 * @param {object[]} catalog lab datasets from /datasets
 * @param {{ comparisonFailed?: boolean, skip?: boolean }} [opts]
 */
export function assessLocalSufficiency(candidate, catalog = [], opts = {}) {
  if (opts.skip) {
    return unknownResult({ reason: "Local comparison did not run." });
  }
  if (opts.comparisonFailed) {
    return unknownResult({ reason: "Local comparison failed." });
  }
  if (candidate?.local_comparison) {
    const fromBackend = sufficiencyFromBackend(candidate.local_comparison, catalog);
    if (fromBackend) return fromBackend;
  }

  const labs = Array.isArray(catalog) ? catalog.filter(Boolean) : [];
  if (!labs.length) {
    return unknownResult({ reason: "Lab catalog is unavailable for comparison." });
  }

  const exact = findExact(candidate, labs);
  if (exact) return exactMatch(exact);

  const signals = candidateComparableSignals(candidate);
  // Identity-only signals that can complete a "none" search without relatedness dims:
  const canComplete =
    signals.includes("dataset_id") ||
    signals.includes("doi") ||
    signals.includes("explicit_equivalent") ||
    signals.includes("related_dataset_ids") ||
    signals.includes("source_identity") ||
    signals.includes("join_keys");

  if (!canComplete) {
    return unknownResult({
      reason:
        "Necessary comparison metadata is absent (no shared identity, source family, or join keys).",
    });
  }

  const related = findRelated(candidate, labs);
  if (related.length) {
    const top = related[0];
    return relatedOrPartial(top.lab, candidate, top.basis);
  }

  return noneResult();
}

/**
 * Apply sufficiency action hints onto evaluation actions.
 * Lifecycle primary/secondary always win when provided by the caller.
 */
export function applySufficiencyToActions(actions, sufficiency, { lifecycleOverrides = false } = {}) {
  if (!actions || lifecycleOverrides) return actions;
  if (!sufficiency || sufficiency.state === SUFFICIENCY.COMPARISON_UNKNOWN) return actions;

  const next = {
    primary: actions.primary ? { ...actions.primary } : null,
    secondary: Array.isArray(actions.secondary) ? actions.secondary.map((a) => ({ ...a })) : [],
  };

  if (sufficiency.state === SUFFICIENCY.EXACT_LOCAL && sufficiency.primaryActionHint) {
    next.primary = { ...sufficiency.primaryActionHint };
    // Keep ordinary inspect/ask as secondary; drop redundant add_lab as primary intent.
    next.secondary = next.secondary.filter((a) => a.id !== "open_local" && a.id !== "open_library");
    if (!next.secondary.some((a) => a.id === "ask")) {
      next.secondary.push({ id: "ask", label: "Ask about this source" });
    }
  } else if (sufficiency.secondaryActionHint) {
    const hint = sufficiency.secondaryActionHint;
    if (!next.secondary.some((a) => a.id === hint.id) && next.primary?.id !== hint.id) {
      next.secondary = [hint, ...next.secondary.filter((a) => a.id !== hint.id)];
    }
  }
  return next;
}

/**
 * Structured Ask context — never upgrades related → equivalent via prose.
 */
export function buildSufficiencyAskContext(sufficiency, candidate) {
  if (!sufficiency) return null;
  return {
    sufficiency_state: sufficiency.state,
    sufficiency_label: sufficiency.label,
    local_dataset_id: labId(sufficiency.bestLocal) || null,
    local_title: sufficiency.bestLocal ? labTitle(sufficiency.bestLocal) : null,
    basis: sufficiency.basis || [],
    differences: sufficiency.differences || [],
    comparison_complete: Boolean(sufficiency.comparisonComplete),
    candidate_key: candidate?.candidate_key || null,
    candidate_title: candidate?.title || candidate?.name || null,
  };
}

export function sufficiencyAskPrompts(sufficiency, title) {
  const label = title || "this candidate";
  if (!sufficiency || sufficiency.state === SUFFICIENCY.COMPARISON_UNKNOWN) {
    return [
      {
        id: "why_unknown",
        label: "Why is local comparison unavailable?",
        prompt: `Why is local comparison unavailable for ${label}? Distinguish missing metadata from a completed empty search.`,
      },
    ];
  }
  if (sufficiency.state === SUFFICIENCY.PARTIAL_LOCAL) {
    return [
      {
        id: "why_partial",
        label: "Why is the local dataset only partial?",
        prompt: `Why is the local dataset only partial for ${label}? Use the documented coverage/grain differences only.`,
      },
      {
        id: "what_acquisition_adds",
        label: "What coverage would acquisition add?",
        prompt: `What coverage would acquiring ${label} add beyond the local asset? Do not invent dimensions.`,
      },
    ];
  }
  if (sufficiency.state === SUFFICIENCY.RELATED_LOCAL) {
    return [
      {
        id: "compare_related",
        label: "How is the local asset related?",
        prompt: `How is the local asset related to ${label}? Do not claim equivalence.`,
      },
    ];
  }
  if (sufficiency.state === SUFFICIENCY.EXACT_LOCAL) {
    return [
      {
        id: "use_local",
        label: "Can I answer with the local asset?",
        prompt: `Can I answer my research question with the local asset already matched to ${label}?`,
      },
    ];
  }
  if (sufficiency.state === SUFFICIENCY.NO_LOCAL_ALTERNATIVE) {
    return [
      {
        id: "confirm_none",
        label: "What did the local comparison check?",
        prompt: `What did the completed local comparison check for ${label}, and why was no qualifying lab asset found?`,
      },
    ];
  }
  return [];
}
