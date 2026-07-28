/**
 * Discover Explore composition — DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md
 * Ranked centre: interpreting chips → Best fit → Other matches.
 * Legacy groupDiscoverBrowseRows kept for tests / alternate buckets.
 */

const STOP = new Set([
  "a",
  "an",
  "the",
  "and",
  "or",
  "of",
  "for",
  "to",
  "in",
  "on",
  "with",
  "from",
  "into",
  "around",
  "before",
  "after",
  "across",
  "i",
  "need",
  "want",
  "looking",
  "find",
  "get",
  "my",
  "our",
  "this",
  "that",
  "these",
  "those",
  "are",
  "is",
  "be",
  "as",
  "by",
  "at",
  "it",
  "we",
  "you",
  "me",
  "what",
  "which",
  "where",
  "when",
  "why",
  "how",
  "can",
  "could",
  "should",
  "would",
  "do",
  "does",
  "use",
  "using",
  "study",
  "research",
  "data",
  "dataset",
  "datasets",
  "evidence",
  "source",
  "sources",
]);

/**
 * Lightweight evidence-need chips from the active query (readout, not a wizard).
 * Budget: three named signals, optional fourth, then +N overflow.
 */
export function interpretEvidenceNeed(query = "") {
  const raw = String(query || "")
    .replace(/[^\p{L}\p{N}\s+-]/gu, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 1 && !STOP.has(t.toLowerCase()));
  const seen = new Set();
  const tokens = [];
  for (const token of raw) {
    const key = token.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    tokens.push(token.length <= 3 ? token.toUpperCase() : token[0].toUpperCase() + token.slice(1));
  }
  const visibleBudget = 4;
  const visible = tokens.slice(0, visibleBudget);
  const overflow = Math.max(0, tokens.length - visibleBudget);
  return { chips: visible, overflow, tokens };
}

/**
 * Freeze Explore ranking: first ordered row = Best fit; remainder = Other matches.
 */
export function splitBestFitAndOthers(rows = []) {
  const list = Array.isArray(rows) ? rows : [];
  return {
    bestFit: list[0] || null,
    others: list.slice(1),
    total: list.length,
  };
}

/**
 * @param {object[]} rows decorated Discover rows with discover_taxonomy
 * @returns {{ id: string, title: string, description: string, rows: object[] }[]}
 */
export function groupDiscoverBrowseRows(rows) {
  const lab = [];
  const external = [];
  const access = [];
  for (const row of rows || []) {
    const group = Number(row?.discover_taxonomy?.group ?? 3);
    if (group <= 2) lab.push(row);
    else if (group === 4) access.push(row);
    else external.push(row);
  }
  return [
    {
      id: "lab",
      title: "Already in your lab",
      description: "Use what the lab already holds before collecting again.",
      rows: lab,
    },
    {
      id: "external",
      title: "Sources beyond your lab",
      description: "Evaluate public and connected sources before acquisition.",
      rows: external,
    },
    {
      id: "access",
      title: "Needs access",
      description: "Manual, licensed, or unavailable paths need review.",
      rows: access,
    },
  ].filter((g) => g.rows.length > 0);
}
