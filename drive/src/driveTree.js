/** Consumer drive tree — My Drive / Lab Drive with normal nested folders (Google Drive style). */

const GLOB_RE = /[*?{\[]/;

export const DRIVE_MY = "my";
export const DRIVE_LAB = "lab";

const DRIVE_ROOT_NAMES = {
  [DRIVE_MY]: "My Drive",
  [DRIVE_LAB]: "Lab Drive",
};

const FOLDER_LABELS = {
  uploads: "Uploads",
  lab_pipelines: "Data pipelines",
  news_shock: "News shock (ingestion)",
  research_panels: "Research panels",
  procured: "Acquired data",
  catalogues: "Catalogues",
  reference: "Reference data",
  connections: "Connected sources",
  campaigns: "Campaigns",
  processed: "Processed",
  sec: "SEC filings",
  entity_mapping: "Entity mapping",
  spk_v1: "SPK v1",
  other: "Other assets",
};

function cleanSegment(part) {
  let seg = String(part || "").trim();
  if (GLOB_RE.test(seg)) seg = seg.split("*", 1)[0].replace(/_+$/, "");
  return seg || "files";
}

export function folderLabel(segment) {
  return FOLDER_LABELS[segment] || segment.replace(/_/g, " ");
}

export function driveRootName(scope) {
  return DRIVE_ROOT_NAMES[scope] || "Drive";
}

/** Personal vs shared lab — consumer split (backend schema unchanged). */
export function datasetDriveScope(row) {
  if (String(row?.domain || "") === "web_scrape") return DRIVE_MY;
  return DRIVE_LAB;
}

export function filterDatasetsByScope(datasets, scope) {
  return (datasets || []).filter((row) => datasetDriveScope(row) === scope);
}

function labPathFromDataLake(parts) {
  if (!parts.length) return ["other"];
  const head = cleanSegment(parts[0]);
  const tail = parts.slice(1).map(cleanSegment).filter(Boolean);

  // Ingestion/backfill — never a top-level Lab Drive folder (not the same as My Drive uploads).
  if (head === "news_shock_taxonomy") return ["lab_pipelines", "news_shock", ...tail];
  if (head === "dataset_catalog") return ["lab_pipelines", "catalogues", ...tail];
  if (head === "spectator_engine") return ["lab_pipelines", "scrapes", ...tail];
  if (head === "research_panels") return ["research_panels", ...tail];
  if (head === "procured") return ["procured", ...tail];
  if (head === "sec") return ["reference", "sec", ...tail];
  if (head === "entity_mapping") return ["reference", "entity_mapping", ...tail];
  if (head === "spk_v1") return ["reference", "spk_v1", ...tail];
  return ["other", head, ...tail];
}

/** Folder path inside My Drive or Lab Drive (no librarian root buckets). */
export function consumerDatasetPath(row, scope = datasetDriveScope(row)) {
  const domain = String(row?.domain || "");
  const localPath = String(row?.local_path || "").trim();
  const localRoot = String(row?.local_root || "").trim();
  const raw = localPath || localRoot;
  // local_root is a directory path — dataset_id must be appended so insertPath
  // nests the leaf one level deeper (inside the named subfolder, not at folder level)
  const usingRoot = !localPath && !!localRoot;
  const did = String(row?.dataset_id || "item");

  if (scope === DRIVE_MY) {
    const scrapeId = String(row?.dataset_id || "").replace(/^scrape_/, "");
    if (domain === "web_scrape" || raw.includes("spectator_engine")) {
      return scrapeId ? ["uploads", scrapeId] : ["uploads", "draft"];
    }
    return ["uploads", String(row?.dataset_id || "file")];
  }

  if (raw.startsWith("data_lake/")) {
    const parts = raw
      .replace(/^data_lake\//, "")
      .split("/")
      .filter(Boolean)
      .map(cleanSegment);
    const resolved = usingRoot ? [...parts, did] : parts;
    return labPathFromDataLake(resolved);
  }

  if (raw.startsWith("data/datasets/")) {
    const parts = raw
      .replace(/^data\/datasets\//, "")
      .split("/")
      .filter(Boolean)
      .map(cleanSegment);
    const project = parts[0] || "datasets";
    const tail = parts.slice(1).filter((seg) => seg !== "latest");
    const leaf = tail.length ? tail[tail.length - 1] : did;
    const folders = tail.length > 1 ? tail.slice(0, -1) : [];
    const fileStem = leaf.includes(".") ? leaf.replace(/\.[^.]+$/, "") : leaf;
    return ["research_panels", project, ...folders, fileStem || did];
  }

  if (domain === "procured") {
    if (raw && raw.includes("procured")) {
      const tail = raw.split("procured/", 2)[1];
      if (tail) {
        const tailParts = tail.split("/").filter(Boolean).map(cleanSegment);
        return ["procured", ...(usingRoot ? [...tailParts, did] : tailParts)];
      }
    }
    return ["procured", did];
  }

  if (!raw) {
    const readiness = String(row?.analysis_readiness || "");
    const backend = String(row?.backend || "");
    if (readiness === "metadata_search" || /catalog|jsonl/i.test(backend)) {
      return ["lab_pipelines", "catalogues", did];
    }
    return ["connections", did];
  }

  const parts = raw
    .replace(/^data_lake\//, "")
    .split("/")
    .filter(Boolean)
    .map(cleanSegment);
  if (!parts.length) return ["other", did];

  const resolved = usingRoot ? [...parts, did] : parts;

  if (resolved[0] === "news_shock_taxonomy" || resolved[0] === "dataset_catalog" || resolved[0] === "spectator_engine") {
    return labPathFromDataLake(resolved);
  }
  if (["research_panels", "procured", "reference", "lab_pipelines", "connections"].includes(resolved[0])) {
    return resolved;
  }

  return ["other", ...resolved];
}

function datasetLeaf(row, scope) {
  const did = String(row?.dataset_id || "");
  return {
    id: did,
    kind: "dataset",
    name: row?.name || did,
    dataset_id: did,
    domain: row?.domain,
    backend: row?.backend,
    analysis_readiness: row?.analysis_readiness,
    local_root: row?.local_root,
    local_path: row?.local_path,
    path: consumerDatasetPath(row, scope),
    row,
  };
}

function insertPath(root, segments, leaf) {
  let node = root;
  const pathSoFar = [];
  for (let i = 0; i < segments.length; i += 1) {
    const seg = segments[i];
    pathSoFar.push(seg);
    const isLeaf = i === segments.length - 1;
    if (isLeaf) {
      node.children = node.children || {};
      node.children[leaf.id] = leaf;
      return;
    }
    const folderId = pathSoFar.join("/");
    node.children = node.children || {};
    if (!node.children[folderId]) {
      node.children[folderId] = {
        id: folderId,
        kind: "folder",
        name: folderLabel(seg),
        segment: seg,
        path: [...pathSoFar],
        children: {},
      };
    }
    node = node.children[folderId];
  }
}

export function buildConsumerDriveTree(datasets, { scope = DRIVE_LAB, campaigns = [], pins = [] } = {}) {
  const rootName = driveRootName(scope);
  const root = {
    id: "",
    kind: "folder",
    name: rootName,
    path: [],
    children: {},
  };

  const scoped = filterDatasetsByScope(datasets, scope);

  for (const row of scoped) {
    const did = String(row?.dataset_id || "");
    if (!did) continue;
    insertPath(root, consumerDatasetPath(row, scope), datasetLeaf(row, scope));
  }

  if (scope === DRIVE_LAB && campaigns.length) {
    const campRoot = {
      id: "campaigns",
      kind: "folder",
      name: folderLabel("campaigns"),
      path: ["campaigns"],
      children: {},
    };
    for (const c of campaigns) {
      const cid = String(c?.id || "");
      if (!cid) continue;
      campRoot.children[`campaign:${cid}`] = {
        id: `campaign:${cid}`,
        kind: "campaign",
        name: String(c?.goal || cid).slice(0, 72),
        campaign_id: cid,
        phase: c?.phase,
        status: c?.status,
        path: ["campaigns", cid],
      };
    }
    root.children.campaigns = campRoot;
  }

  if (scope === DRIVE_LAB) {
    for (const pin of pins) {
      const fp = String(pin?.file_path || "");
      if (!fp.startsWith("data_lake/")) continue;
      const parts = fp
        .replace(/^data_lake\//, "")
        .split("/")
        .filter(Boolean)
        .map(cleanSegment);
      const segments = labPathFromDataLake(parts);
      insertPath(root, segments, {
        id: `pin:${pin?.handle}`,
        kind: "pin",
        name: String(pin?.metadata?.title || pin?.handle || "Pinned file"),
        handle: pin?.handle,
        campaign_id: pin?.campaign_id,
        file_path: fp,
        path: segments,
      });
    }
  }

  return { root, scope, rootName };
}

/** @deprecated use buildConsumerDriveTree */
export function buildDriveTree(datasets, opts = {}) {
  return buildConsumerDriveTree(datasets, { ...opts, scope: DRIVE_LAB });
}

export function findFolder(root, folderId) {
  if (!folderId || folderId === root.id) return root;
  let node = root;
  const acc = [];
  for (const part of folderId.split("/")) {
    if (!part) continue;
    acc.push(part);
    const currentId = acc.join("/");
    const children = node.children || {};
    let nxt = children[currentId];
    if (!nxt) {
      nxt = Object.values(children).find((c) => c.kind === "folder" && c.id === currentId);
    }
    if (!nxt) return null;
    node = nxt;
  }
  return node;
}

export function listFolderChildren(tree, folderId = "") {
  const root = tree?.root || tree;
  const node = findFolder(root, folderId);
  if (!node) return [];
  const children = Object.values(node.children || {});
  const folders = children
    .filter((c) => c.kind === "folder")
    .sort((a, b) => a.name.localeCompare(b.name));
  const files = children
    .filter((c) => c.kind !== "folder")
    .sort((a, b) => a.name.localeCompare(b.name));
  return [...folders, ...files];
}

export function breadcrumbTrail(tree, folderId = "") {
  const root = tree?.root || tree;
  const rootLabel = root.name || driveRootName(tree.scope) || "Drive";
  if (!folderId) return [{ id: "", name: rootLabel }];
  const parts = folderId.split("/").filter(Boolean);
  const trail = [{ id: "", name: rootLabel }];
  let acc = [];
  for (const part of parts) {
    acc.push(part);
    const id = acc.join("/");
    const node = findFolder(root, id);
    trail.push({ id, name: node?.name || folderLabel(part) });
  }
  return trail;
}

export function collectFolderNodes(root, folderId = "", depth = 0, out = [], maxDepth = 3) {
  const node = folderId ? findFolder(root, folderId) : root;
  if (!node || node.kind !== "folder") return out;
  if (depth > 0) out.push({ id: node.id, name: node.name, depth });
  if (depth >= maxDepth) return out;
  const folders = Object.values(node.children || {})
    .filter((c) => c.kind === "folder")
    .sort((a, b) => a.name.localeCompare(b.name));
  for (const child of folders) {
    collectFolderNodes(root, child.id, depth + 1, out, maxDepth);
  }
  return out;
}
