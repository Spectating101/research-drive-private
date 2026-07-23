import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  breadcrumbTrail,
  collectDatasetDescendants,
  listFolderChildren,
} from "@/driveTree";
import { buildProfessorVaultTree, datasetTitle, isOpsNoiseDataset } from "@/v2/professorVaultTree";
import { libraryFolderObject } from "@/v2/activeObject";
import { CatalogList } from "@/v2/CatalogList";
import { statusPillKind } from "@/v2/datasetMeta";
import { Chip, PageShell } from "@/v2/ui";

function datasetListItem(row) {
  const name = datasetTitle(row);
  return {
    kind: "dataset",
    id: row.dataset_id,
    name,
    row: { ...row, name },
  };
}

function readinessCount(rows) {
  return rows.filter((d) => statusPillKind(d).kind === "query-ready").length;
}

function itemDataset(item) {
  return item?.row || item;
}

function itemName(item) {
  if (item?.kind === "folder") return item.name || "";
  const row = itemDataset(item);
  return row.name || row.title || row.dataset_id || "";
}

function itemUpdatedTime(item) {
  const row = itemDataset(item);
  const raw = row.updated_at || row.last_modified || row.as_of;
  if (!raw) return 0;
  const time = new Date(raw).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function itemMatchesFilter(item, mode) {
  if (mode === "all" || item?.kind === "folder") return true;
  const row = itemDataset(item);
  return statusPillKind(row).kind === "query-ready";
}

function sortItems(rows, sortBy) {
  return [...rows].sort((a, b) => {
    if (a?.kind === "folder" && b?.kind !== "folder") return -1;
    if (a?.kind !== "folder" && b?.kind === "folder") return 1;
    if (sortBy === "updated") {
      const delta = itemUpdatedTime(b) - itemUpdatedTime(a);
      if (delta) return delta;
    }
    return itemName(a).localeCompare(itemName(b), undefined, { sensitivity: "base" });
  });
}

function folderDestination(trail, folderId) {
  if (!folderId) return "Lab root";
  return trail.map((c) => c.name).join(" / ");
}

function branchStatusNote({
  isRoot,
  items,
  showingBranchFallback,
  showingSearchHits,
  displayCount,
  folderCount,
  partitionCount,
  datasetCount,
}) {
  if (!displayCount && !folderCount) {
    if (showingSearchHits) return "No datasets match this search";
    return isRoot ? "No indexed folders yet" : "No holdings in this branch";
  }
  if (showingSearchHits) {
    return `${displayCount} matching dataset${displayCount === 1 ? "" : "s"} — open a row for readiness and Ask`;
  }
  if (showingBranchFallback) {
    return `${displayCount} dataset${displayCount === 1 ? "" : "s"} matched here`;
  }
  if (isRoot) {
    const parts = [];
    if (folderCount) parts.push(`${folderCount} ${folderCount === 1 ? "shelf" : "shelves"}`);
    if (partitionCount) parts.push(`${partitionCount} folder${partitionCount === 1 ? "" : "s"}`);
    if (datasetCount) parts.push(`${datasetCount} dataset${datasetCount === 1 ? "" : "s"}`);
    return parts.join(" · ") || "Browse shelves, then folders inside them";
  }
  if (items.length) {
    const parts = [];
    if (folderCount) parts.push(`${folderCount} folder${folderCount === 1 ? "" : "s"}`);
    if (datasetCount) parts.push(`${datasetCount} dataset${datasetCount === 1 ? "" : "s"}`);
    return parts.join(" · ") || "Open a folder or dataset";
  }
  return "No holdings in this branch";
}

function toolbarCountLabel({ searchActive, folderCount, datasetCount, visibleCount }) {
  if (searchActive) {
    return `${visibleCount} dataset${visibleCount === 1 ? "" : "s"}`;
  }
  const parts = [];
  if (folderCount) parts.push(`${folderCount} folder${folderCount === 1 ? "" : "s"}`);
  if (datasetCount) parts.push(`${datasetCount} dataset${datasetCount === 1 ? "" : "s"}`);
  return parts.join(" · ") || `${visibleCount} row${visibleCount === 1 ? "" : "s"}`;
}

function LibraryBreadcrumb({ trail, onFolderChange }) {
  return (
    <nav className="rd-v2-breadcrumb rd-v2-crumb" aria-label="Breadcrumb">
      {trail.map((c, i) => {
        const last = i === trail.length - 1;
        return (
          <span key={c.id || "root"} className="rd-v2-crumb-item">
            {i > 0 ? <span className="sep">›</span> : null}
            {last ? (
              <span className="here">{c.name}</span>
            ) : (
              <button type="button" onClick={() => onFolderChange(c.id)}>
                {c.name}
              </button>
            )}
          </span>
        );
      })}
    </nav>
  );
}

function LibraryNewMenu({ open, onToggle, onUploadFile, onAddUrl, onProcure, onClose }) {
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) onClose();
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open, onClose]);

  return (
    <div className="rd-v2-library-action-wrap" ref={menuRef}>
      <button
        type="button"
        className="rd-v2-btn sm rd-v2-library-action-btn primary"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Open new library item menu"
        onClick={onToggle}
      >
        New ▾
      </button>
      {open ? (
        <div className="rd-v2-library-action-menu" role="menu" aria-label="New library item">
          <button type="button" role="menuitem" className="rd-v2-library-menu-item" onClick={onUploadFile}>
            Upload file...
          </button>
          <button type="button" role="menuitem" className="rd-v2-library-menu-item" onClick={onAddUrl}>
            Add URL / DOI...
          </button>
          <button type="button" role="menuitem" className="rd-v2-library-menu-item" onClick={onProcure}>
            Procure missing data...
          </button>
          <button type="button" role="menuitem" className="rd-v2-library-menu-item" disabled>
            New folder
          </button>
        </div>
      ) : null}
    </div>
  );
}

function LibraryHeadActions({
  newMenuOpen,
  onToggleNewMenu,
  onCloseNewMenu,
  onOpenUpload,
  onOpenUrlModal,
  onProcureBranch,
  onRefresh,
}) {
  return (
    <div className="rd-v2-library-actions">
      <LibraryNewMenu
        open={newMenuOpen}
        onToggle={onToggleNewMenu}
        onClose={onCloseNewMenu}
        onUploadFile={onOpenUpload}
        onAddUrl={onOpenUrlModal}
        onProcure={onProcureBranch}
      />
      <button
        type="button"
        className="rd-v2-btn sm rd-v2-library-action-btn ghost"
        onClick={onRefresh}
        disabled={!onRefresh}
      >
        Refresh
      </button>
    </div>
  );
}

export function LibraryPage({
  datasets,
  partitions = [],
  shelves = [],
  guide = null,
  cluster,
  folderId,
  onFolderChange,
  selectedId,
  onSelectDataset,
  onPreviewDataset,
  onRefresh,
  onFocusFolder,
  onStartUpload,
  onStartUrl,
  onStartProcure,
  searchQuery = "",
  onSearchChange,
}) {
  const [sortBy, setSortBy] = useState("name");
  const [filterMode, setFilterMode] = useState("all");
  const [newMenuOpen, setNewMenuOpen] = useState(false);

  const vaultDatasets = useMemo(
    () => (datasets || []).filter((row) => !isOpsNoiseDataset(row)),
    [datasets],
  );

  const tree = useMemo(
    () => buildProfessorVaultTree(vaultDatasets, partitions.length ? partitions : (cluster?.lanes || []), shelves),
    [vaultDatasets, partitions, shelves, cluster?.lanes],
  );

  const trail = useMemo(() => {
    const crumbs = breadcrumbTrail(tree, folderId);
    if (crumbs[0]) crumbs[0].name = "Lab";
    return crumbs;
  }, [tree, folderId]);

  const destination = useMemo(() => folderDestination(trail, folderId), [trail, folderId]);
  const isRoot = !folderId;

  const items = useMemo(() => listFolderChildren(tree, folderId), [tree, folderId]);
  const searchActive = Boolean(String(searchQuery || "").trim());
  // Search already filters the catalog upstream; without flattening, Lab root only
  // shows ancestor shelf/partition folders — never the matching datasets themselves.
  const displayRows = useMemo(() => {
    if (!searchActive) return items;
    return collectDatasetDescendants(tree, folderId);
  }, [folderId, items, searchActive, tree]);
  const visibleRows = useMemo(
    () => sortItems(displayRows.filter((item) => itemMatchesFilter(item, filterMode)), sortBy),
    [displayRows, filterMode, sortBy],
  );
  const currentFolderName = isRoot ? "Lab root" : trail[trail.length - 1]?.name || "Lab";
  const showingBranchFallback = false;
  const showingSearchHits = searchActive;
  const folderRows = useMemo(
    () => visibleRows.filter((item) => item.kind === "folder"),
    [visibleRows],
  );
  const folderCount = folderRows.length;
  const partitionCount = useMemo(() => {
    if (!isRoot || searchActive) return 0;
    return folderRows.reduce(
      (sum, shelf) =>
        sum + Object.values(shelf.children || {}).filter((c) => c?.kind === "folder").length,
      0,
    );
  }, [folderRows, isRoot, searchActive]);
  const branchDatasetRows = useMemo(() => {
    if (searchActive) return displayRows.map(itemDataset);
    if (isRoot) return vaultDatasets;
    return collectDatasetDescendants(tree, folderId).map(itemDataset);
  }, [displayRows, folderId, isRoot, searchActive, tree, vaultDatasets]);
  const readyCount = readinessCount(branchDatasetRows);
  const browseDatasetCount = branchDatasetRows.length;
  const branchNote = branchStatusNote({
    isRoot,
    items,
    showingBranchFallback,
    showingSearchHits,
    displayCount: displayRows.length,
    folderCount,
    partitionCount,
    datasetCount: browseDatasetCount,
  });
  const startHereShelves = useMemo(() => {
    const ids = Array.isArray(guide?.start_here) ? guide.start_here : [];
    const byId = new Map((shelves || []).map((s) => [String(s.id || ""), s]));
    const fromGuide = ids.map((id) => byId.get(String(id))).filter(Boolean);
    if (fromGuide.length) {
      return fromGuide.map((s) => ({ id: String(s.id), label: String(s.label || s.id) }));
    }
    return folderRows.slice(0, 5).map((s) => ({ id: s.id, label: s.name }));
  }, [folderRows, guide, shelves]);
  const branchObject = useMemo(
    () =>
      libraryFolderObject({
        folderId,
        trail,
        destination,
        note: branchNote,
        folderCount,
        datasetCount: browseDatasetCount,
        readyCount,
        itemCount: visibleRows.length,
      }),
    [branchNote, browseDatasetCount, destination, folderCount, folderId, readyCount, trail, visibleRows.length],
  );

  useEffect(() => {
    if (!selectedId) onFocusFolder?.(branchObject);
  }, [branchObject, onFocusFolder, selectedId]);

  const closeNewMenu = useCallback(() => setNewMenuOpen(false), []);
  const toggleNewMenu = useCallback(() => setNewMenuOpen((open) => !open), []);

  const openUploadRail = useCallback(() => {
    setNewMenuOpen(false);
    onStartUpload?.(branchObject);
  }, [branchObject, onStartUpload]);

  const openUrlRail = useCallback(() => {
    setNewMenuOpen(false);
    onStartUrl?.(branchObject);
  }, [branchObject, onStartUrl]);

  const handleRefresh = useCallback(() => {
    onRefresh?.();
  }, [onRefresh]);

  const handleProcureBranch = useCallback(() => {
    setNewMenuOpen(false);
    onStartProcure?.(branchObject);
  }, [branchObject, onStartProcure]);

  return (
    <PageShell
      className="rd-v2-library-page"
      title="Library"
      lead="Open a shelf first — news, stocks, crypto, panels — then the datasets inside."
      headExtra={
        <div className="rd-v2-library-headline">
          <LibraryBreadcrumb trail={trail} onFolderChange={onFolderChange} />
          <LibraryHeadActions
            newMenuOpen={newMenuOpen}
            onToggleNewMenu={toggleNewMenu}
            onCloseNewMenu={closeNewMenu}
            onOpenUpload={openUploadRail}
            onOpenUrlModal={openUrlRail}
            onProcureBranch={handleProcureBranch}
            onRefresh={onRefresh ? handleRefresh : undefined}
          />
        </div>
      }
      toolbar={
        <>
          <label className="rd-v2-library-toolbar-search" data-testid="library-toolbar-search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="m21 21-4.2-4.2m1.2-5.3a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            <input
              value={searchQuery}
              onChange={(e) => onSearchChange?.(e.target.value)}
              placeholder="Search datasets in this library…"
              aria-label="Search library holdings"
              onKeyDown={(e) => {
                // Live filter; Enter just commits focus so results stay visible.
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
          </label>
          <Chip active={sortBy === "name"} onClick={() => setSortBy("name")}>
            Name {sortBy === "name" ? "↑" : "↕"}
          </Chip>
          <Chip active={sortBy === "updated"} onClick={() => setSortBy("updated")}>
            Last modified {sortBy === "updated" ? "↓" : "↕"}
          </Chip>
          <Chip
            active={filterMode === "ready"}
            onClick={() => setFilterMode((cur) => (cur === "ready" ? "all" : "ready"))}
          >
            Filter: {filterMode === "ready" ? "Query-ready" : "All"}
          </Chip>
          <span className="rd-v2-toolbar-spacer" />
          <span className="rd-v2-toolbar-count">
            {toolbarCountLabel({
              searchActive,
              folderCount,
              datasetCount: browseDatasetCount,
              visibleCount: visibleRows.length,
            })}
          </span>
        </>
      }
      footer="double-click row → Preview"
    >
      {isRoot && !searchActive && startHereShelves.length ? (
        <div className="rd-v2-library-start-here" aria-label="Start here shelves">
          <span className="rd-v2-library-start-here-label">Start here</span>
          <div className="rd-v2-library-start-here-chips">
            {startHereShelves.map((shelf) => (
              <Chip key={shelf.id} onClick={() => onFolderChange(shelf.id)}>
                {shelf.label}
              </Chip>
            ))}
          </div>
        </div>
      ) : null}
      <div className="rd-v2-library-branchline rd-v2-library-pathbar" aria-label="Library location status">
        <div className="rd-v2-library-pathcopy">
          <strong>{currentFolderName}</strong>
          <p>
            {searchActive
              ? branchNote
              : isRoot
                ? "Browse shelves first, then the folders inside — each folder holds the datasets for that collection."
                : branchNote}
          </p>
        </div>
        <div className="rd-v2-library-pathstats">
          {searchActive ? null : isRoot ? (
            <>
              <span>
                {folderCount} {folderCount === 1 ? "shelf" : "shelves"}
              </span>
              <span>
                {partitionCount} folder{partitionCount === 1 ? "" : "s"}
              </span>
            </>
          ) : (
            <span>
              {folderCount} folder{folderCount === 1 ? "" : "s"}
            </span>
          )}
          <span>
            {browseDatasetCount} dataset{browseDatasetCount === 1 ? "" : "s"}
            {searchActive ? " matched" : ""}
          </span>
          <span>{readyCount} query-ready</span>
        </div>
      </div>
      <div className="rd-v2-catalog-list-wrap">
        {visibleRows.length ? (
          <CatalogList
            rows={visibleRows}
            selectedId={selectedId}
            onOpenFolder={(folder) => onFolderChange(folder.id)}
            onSelectDataset={onSelectDataset}
            onDoubleClick={onPreviewDataset}
            compact
          />
        ) : (
          <div className="rd-v2-library-empty">
            <strong>{searchActive ? "No datasets match this search" : "No holdings in this branch"}</strong>
            <p>
              {searchActive
                ? "Try a broader keyword, or clear the search to browse shelves again."
                : "Clear the filter or open the Lab breadcrumb to return to indexed folders."}
            </p>
          </div>
        )}
      </div>
    </PageShell>
  );
}
