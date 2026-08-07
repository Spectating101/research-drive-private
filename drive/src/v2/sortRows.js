/**
 * Result ordering over stored fields only.
 *
 * Relevance is the backend's ranking and is returned untouched — the frontend
 * does not re-score. Every other option reads a field the registry already
 * carries, so sorting never becomes a judgment.
 */

export const SORTS = [
  { id: "relevance", label: "Relevance" },
  { id: "verified", label: "Recently verified" },
  { id: "size", label: "Size" },
  { id: "name", label: "Name A–Z" },
];

function title(row) {
  return String(row?.display_name || row?.title || row?.name || row?.dataset_id || "");
}

export function sortRows(rows, sort) {
  const list = Array.isArray(rows) ? rows : [];
  if (sort === "relevance" || !sort) return list;
  const out = [...list];
  if (sort === "name") return out.sort((a, b) => title(a).localeCompare(title(b)));
  if (sort === "size") {
    return out.sort((a, b) => Number(b?.size_bytes || 0) - Number(a?.size_bytes || 0));
  }
  if (sort === "verified") {
    return out.sort((a, b) =>
      String(b?.query_verified_at || "").localeCompare(String(a?.query_verified_at || "")),
    );
  }
  return list;
}
