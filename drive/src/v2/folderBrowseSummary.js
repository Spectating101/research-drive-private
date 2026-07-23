/** Library folder row copy — folders inside + dataset totals, not vague "items". */

export function countDatasetDescendants(folder) {
  let n = 0;
  for (const child of Object.values(folder?.children || {})) {
    if (child?.kind === "dataset") n += 1;
    else if (child?.kind === "folder") n += countDatasetDescendants(child);
  }
  return n;
}

function datasetPhrase(n) {
  if (n <= 0) return "0 datasets";
  return n === 1 ? "1 dataset" : `${n} datasets`;
}

function folderNameList(folders, limit = 3) {
  const names = folders.map((f) => String(f.name || "").trim()).filter(Boolean);
  if (!names.length) return "";
  const shown = names.slice(0, limit);
  let text = shown.join(" · ");
  if (names.length > limit) text += ` · +${names.length - limit} more`;
  return text;
}

/**
 * @returns {{ sub: string, pill: string, desc: string|null }}
 */
export function folderBrowseSummary(folder) {
  const children = Object.values(folder?.children || {});
  const subfolders = children
    .filter((c) => c?.kind === "folder")
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }));
  const datasets = countDatasetDescendants(folder);
  const blurb = String(folder?.blurb || "").trim();

  if (subfolders.length) {
    const foldersBit = folderNameList(subfolders);
    return {
      desc: blurb || null,
      sub:
        datasets <= 0
          ? `${foldersBit} · no datasets on this desk yet`
          : `${foldersBit} · ${datasetPhrase(datasets)}`,
      pill: String(datasets),
    };
  }

  // Partition (leaf) folder — files live here.
  if (datasets <= 0) {
    return {
      desc: blurb || null,
      sub: "No datasets on this desk yet",
      pill: "0",
    };
  }
  return {
    desc: blurb || null,
    sub: datasetPhrase(datasets),
    pill: String(datasets),
  };
}

/** Soft path under a search hit: Shelf › Partition */
export function datasetBrowsePathLabel(item) {
  const label = String(item?.pathLabel || "").trim();
  if (label) return label;
  const parts = Array.isArray(item?.browsePath) ? item.browsePath.filter(Boolean) : [];
  return parts.length ? parts.join(" › ") : "";
}
