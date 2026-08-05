/** Professor Library tree — shelves → folders → datasets (not Apps & connections junk). */

const OPS_NOISE_RE =
  /canary|smoke|host_acceptance|day2_deploy|mcp_canary|winclaim|fullops|post-heal|landing prove|windows http|ssrf\d|rev_live|example\.com|capability_canary|codex_sec_tickers_canary|synthesis_.*canary/i;

export function isOpsNoiseDataset(row) {
  if (row?.professor_visible === false) return true;
  const blob = [
    row?.dataset_id,
    row?.registry_id,
    row?.name,
    row?.display_name,
    row?.description,
    row?.source,
    row?.grain,
    row?.manifest_id,
    row?.job_id,
  ]
    .filter(Boolean)
    .join(" ");
  return OPS_NOISE_RE.test(blob);
}

export function datasetTitle(row) {
  return String(row?.display_name || row?.name || row?.title || row?.dataset_id || "").trim();
}

function partitionIdOf(lane) {
  return String(lane?.partition_id || lane?.detail?.partition_id || "").trim();
}

function registryIdsOf(lane) {
  return new Set(lane?.detail?.registry_dataset_ids || lane?.registry_dataset_ids || []);
}

function deriveShelves(partitions = [], shelves = []) {
  if (Array.isArray(shelves) && shelves.length) {
    return shelves
      .filter((s) => s?.professor_visible !== false)
      .map((s) => ({
        id: String(s.id || ""),
        label: String(s.label || s.id || "Shelf"),
        blurb: String(s.blurb || ""),
        sort: Number(s.sort || 500),
        partition_ids: [...(s.partition_ids || [])],
      }))
      .filter((s) => s.id);
  }
  const byId = new Map();
  for (const lane of partitions || []) {
    const sid = String(lane.shelf_id || "ungrouped");
    if (!byId.has(sid)) {
      byId.set(sid, {
        id: sid,
        label: String(lane.shelf_label || sid),
        blurb: "",
        sort: Number(lane.professor_sort || 500),
        partition_ids: [],
      });
    }
    const pid = partitionIdOf(lane);
    if (pid) byId.get(sid).partition_ids.push(pid);
  }
  return [...byId.values()];
}

/**
 * Build a Lab tree compatible with listFolderChildren / breadcrumbTrail:
 *   {shelf_id} / {partition_id} / dataset
 */
/**
 * A shelf can hold datasets while owning no browsable folder, because a
 * partition's `professor_visible` flag is an operator concern about a storage
 * folder and says nothing about the datasets inside it. Crypto is the case that
 * matters: `markets.crypto-coingecko` is an ops holding slot marked not-visible
 * and carries 26 visible crypto datasets, so the shelf rendered "no holdings"
 * while its datasets were silently swept into Other holdings under Project
 * downloads -- inflating that shelf to 82 rows and hiding the desk's largest
 * holding in the wrong place.
 *
 * Giving the shelf its own folder keeps those datasets where the researcher
 * looked for them, without surfacing the operator-hidden partition itself.
 */
function ensureShelfHoldingsFolder(shelf, partNodes) {
  const key = `shelf:${shelf.id}`;
  if (partNodes.has(key)) return partNodes.get(key);
  const folderId = `${shelf.id}/held`;
  const folder = {
    id: folderId,
    kind: "folder",
    name: String(shelf.name || shelf.id),
    segment: "held",
    path: [shelf.id, "held"],
    partition_id: key,
    sort: 500,
    children: {},
    registry_ids: new Set(),
  };
  shelf.children[folderId] = folder;
  partNodes.set(key, folder);
  return folder;
}

export function buildProfessorVaultTree(datasets = [], partitions = [], shelves = []) {
  const root = {
    id: "",
    kind: "folder",
    name: "Library",
    path: [],
    children: {},
  };

  const shelfSpecs = deriveShelves(partitions, shelves);
  const shelfNodes = new Map();
  for (const spec of shelfSpecs) {
    const node = {
      id: spec.id,
      kind: "folder",
      name: spec.label,
      segment: spec.id,
      path: [spec.id],
      blurb: spec.blurb,
      sort: spec.sort,
      children: {},
    };
    shelfNodes.set(spec.id, node);
    root.children[spec.id] = node;
  }

  const partNodes = new Map();
  for (const lane of partitions || []) {
    if (lane?.professor_visible === false) continue;
    const pid = partitionIdOf(lane);
    if (!pid) continue;
    const sid = String(lane.shelf_id || shelfSpecs.find((s) => (s.partition_ids || []).includes(pid))?.id || "project_downloads");
    let shelf = shelfNodes.get(sid);
    if (!shelf) {
      shelf = {
        id: sid,
        kind: "folder",
        name: String(lane.shelf_label || sid),
        segment: sid,
        path: [sid],
        sort: Number(lane.professor_sort || 500),
        children: {},
      };
      shelfNodes.set(sid, shelf);
      root.children[sid] = shelf;
    }
    const folderId = `${sid}/${pid}`;
    const folder = {
      id: folderId,
      kind: "folder",
      name: String(lane.professor_label || lane.subtitle || lane.name || pid),
      segment: pid,
      path: [sid, pid],
      partition_id: pid,
      blurb: String(lane.professor_blurb || lane.scope || ""),
      sort: Number(lane.professor_sort || 500),
      children: {},
      registry_ids: registryIdsOf(lane),
    };
    shelf.children[folderId] = folder;
    partNodes.set(pid, folder);
  }

  // Catch-all for readable holdings without a wired partition.
  const otherShelfId = "project_downloads";
  if (!shelfNodes.has(otherShelfId)) {
    const node = {
      id: otherShelfId,
      kind: "folder",
      name: "Your project downloads",
      segment: otherShelfId,
      path: [otherShelfId],
      sort: 90,
      children: {},
    };
    shelfNodes.set(otherShelfId, node);
    root.children[otherShelfId] = node;
  }
  const otherFolderId = `${otherShelfId}/unfiled`;
  if (!partNodes.has("unfiled")) {
    const folder = {
      id: otherFolderId,
      kind: "folder",
      name: "Other holdings",
      segment: "unfiled",
      path: [otherShelfId, "unfiled"],
      partition_id: "unfiled",
      sort: 999,
      children: {},
      registry_ids: new Set(),
    };
    shelfNodes.get(otherShelfId).children[otherFolderId] = folder;
    partNodes.set("unfiled", folder);
  }

  let placed = 0;
  let skipped = 0;
  for (const row of datasets || []) {
    if (isOpsNoiseDataset(row)) {
      skipped += 1;
      continue;
    }
    const did = String(row.dataset_id || "");
    if (!did) continue;

    let folder = null;
    const pid = String(row.partition_id || row.collection?.partition_id || "").trim();
    if (pid && partNodes.has(pid)) folder = partNodes.get(pid);
    if (!folder) {
      for (const candidate of partNodes.values()) {
        if (candidate.registry_ids?.has(did)) {
          folder = candidate;
          break;
        }
      }
    }
    if (!folder) {
      const hint = String(row.shelf_hint || "").trim();
      if (hint && shelfNodes.has(hint)) {
        const shelf = shelfNodes.get(hint);
        folder =
          Object.values(shelf.children || {}).find((c) => c.kind === "folder") ||
          ensureShelfHoldingsFolder(shelf, partNodes);
      } else {
        folder = partNodes.get("unfiled");
      }
    }
    if (!folder) continue;

    const shelfName = shelfNodes.get(String(folder.path?.[0] || ""))?.name || "";
    folder.children[did] = {
      kind: "dataset",
      id: did,
      name: datasetTitle(row),
      row: { ...row, name: datasetTitle(row) },
      path: [...(folder.path || []), did],
      browsePath: [shelfName, folder.name].filter(Boolean),
      pathLabel: [shelfName, folder.name].filter(Boolean).join(" › "),
    };
    placed += 1;
  }

  // Keep shelf → partition taxonomy even when no local datasets matched yet.
  // Only drop the synthetic "Other holdings" catch-all when it is empty.
  for (const [sid, shelf] of [...shelfNodes.entries()]) {
    for (const part of Object.values(shelf.children || {}).filter((c) => c.kind === "folder")) {
      if (part.partition_id !== "unfiled") continue;
      const files = Object.values(part.children || {}).filter((c) => c.kind === "dataset");
      if (!files.length) delete shelf.children[part.id];
    }
    if (
      sid === "project_downloads" &&
      !Object.keys(shelf.children || {}).length
    ) {
      delete root.children[sid];
    }
  }

  return {
    root,
    scope: "lab",
    rootName: "Library",
    meta: { placed, skipped, shelves: Object.keys(root.children || {}).length },
  };
}
