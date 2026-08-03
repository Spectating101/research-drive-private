const SUBSCRIPT_DIGITS = Object.freeze({
  "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
  "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
});

const GENERIC_QUERY_TERMS = new Set([
  "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with", "from",
  "what", "which", "where", "when", "why", "how", "can", "could", "should", "would",
  "do", "does", "is", "are", "i", "we", "you", "use", "using", "need", "want", "find",
  "help", "illustrate", "measure", "measurement", "measurements", "public", "open", "data",
  "dataset", "datasets", "research", "study", "source", "sources",
  "daily", "weekly", "monthly", "quarterly", "annual", "yearly", "time", "series",
]);

export function normalizeDiscoverText(value = "") {
  return String(value)
    .replace(/[₀-₉]/g, (digit) => SUBSCRIPT_DIGITS[digit] || digit)
    .toLowerCase();
}

export function meaningfulDiscoverTerms(tokens = []) {
  return tokens
    .map((token) => normalizeDiscoverText(token).trim())
    .filter((token) => token.length >= 3 && !GENERIC_QUERY_TERMS.has(token));
}

export function candidateSpecificityText(row = {}) {
  return normalizeDiscoverText([
    row?.title,
    row?.name,
    row?.source,
    row?.publisher,
    row?.description,
    row?.recommended_use,
    ...(Array.isArray(row?.capabilities) ? row.capabilities : []),
  ].filter(Boolean).join(" "));
}

export function hasSpecificDiscoverRoute(rows = [], tokens = []) {
  const terms = meaningfulDiscoverTerms(tokens);
  if (!terms.length) return true;
  const requiredHits = terms.length >= 4 ? 2 : 1;
  return rows.some((row) => {
    const text = candidateSpecificityText(row);
    return terms.filter((term) => text.includes(term)).length >= requiredHits;
  });
}
