import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DRIVE_LAB,
  buildConsumerDriveTree,
  breadcrumbTrail,
  listFolderChildren,
} from "@/driveTree";
import { libraryFolderObject } from "@/v2/activeObject";
import { LibraryEstateBrowser } from "@/v2/LibraryEstateBrowser";
import { collectionOrder, datasetBelongsToFolder, libraryAssetCounts } from "@/v2/libraryEstate";
import { PageShell } from "@/v2/ui";

function datasetListItem(row) {
  return {
    kind: "dataset",
    id: row.dataset_id,
    name: row.name,
    row,
  };
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
  return libraryAssetCounts([itemDataset(item)]).queryReady === 1;
}

function sortItems(rows, sortBy, isRoot) {
  return [...rows].sort((a, b) => {
    if (a?.kind === "folder" && b?.kind !== "folder") return -1;
    if (a?.kind !== "folder" && b?.kind === "folder") return 1;
    if (isRoot && a?.kind === "folder" && b?.kind === "folder") {
      const delta = collectionOrder(a) - collectionOrder(b);
      if (delta) return delta;
    }
    if (sortBy === "updated") {
      const delta = itemUpdatedTime(b) - itemUpdatedTime(a);
      if (delta) return delta;
    }
    return itemName(a).localeCompare(itemName(b), undefined, { sensitivity: "base" });
  });
}

function folderDestination(trail, folderId) {
  if (!folderId) return "Lab";
  return trail.map((c) => c.name).join(" / ");
}

function branchStatusNote({ isRoot, items, showingBranchFallback, displayCount, folderCount, datasetCount }) {
  if (!displayCount) {
    return isRoot ? "No indexed collections yet" : "No holdings in this collection";
  }
  if (showingBranchFallback) {
    return `${displayCount} dataset${displayCount === 1 ? "" : "s"} matched here`;
  }
  if (items.length) {
    const parts = [];
    if (folderCount) parts.push(`${folderCount} collection${folderCount === 1 ? "" : "s"}`);
    if (datasetCount) parts.push(`${datasetCount} dataset${datasetCount === 1 ? "" : "s"}`);
    return parts.join(", ") || `${displayCount} item${displayCount === 1 ? "" : "s"}`;
  }
  return `${displayCount} item${displayCount === 1 ? "" : "s"} in collection`;
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
            Find missing data...
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
}) {
  const [sortBy, setSortBy] = useState("name");
  const [filterMode, setFilterMode] = useState("all");
  const [newMenuOpen, setNewMenuOpen] = useState(false);

  const tree = useMemo(
    () => buildConsumerDriveTree(datasets, { scope: DRIVE_LAB }),
    [datasets],
  );

  const trail = useMemo(() => {
    const crumbs = breadcrumbTrail(tree, folderId);
    if (crumbs[0]) crumbs[0].name = "Lab";
    return crumbs;
  }, [tree, folderId]);

  const destination = useMemo(() => folderDestination(trail, folderId), [trail, folderId]);
  const isRoot = !folderId;

  const items = useMemo(() => listFolderChildren(tree, folderId), [tree, folderId]);
  const branchRows = useMemo(
    () => datasets.filter((row) => datasetBelongsToFolder(row, folderId)).map(datasetListItem),
    [datasets, folderId],
  );
  const displayRows = useMemo(() => {
    if (items.length) return items;
    return branchRows;
  }, [items, branchRows]);
  const visibleRows = useMemo(
    () => sortItems(displayRows.filter((item) => itemMatchesFilter(item, filterMode)), sortBy, isRoot),
    [displayRows, filterMode, sortBy, isRoot],
  );
  const currentFolderName = isRoot ? "Lab" : trail[trail.length - 1]?.name || "Lab";
  const showingBranchFallback = !items.length && branchRows.length > 0;
  const branchDatasetRows = useMemo(
    () => (isRoot ? datasets : branchRows.map(itemDataset)),
    [branchRows, datasets, isRoot],
  );
  const branchCounts = libraryAssetCounts(branchDatasetRows);
  const readyCount = branchCounts.queryReady;
  const folderCount = visibleRows.filter((item) => item.kind === "folder").length;
  const datasetCount = branchDatasetRows.length;
  const branchNote = branchStatusNote({
    isRoot,
    items,
    showingBranchFallback,
    displayCount: displayRows.length,
    folderCount,
    datasetCount,
  });
  const branchObject = useMemo(
    () =>
      libraryFolderObject({
        folderId,
        trail,
        destination,
        note: branchNote,
        folderCount,
        datasetCount,
        readyCount,
        connectedCount: branchCounts.connected,
        metadataOnlyCount: branchCounts.metadataOnly,
        unknownCount: branchCounts.unknown,
        itemCount: visibleRows.length,
      }),
    [branchCounts.connected, branchCounts.metadataOnly, branchCounts.unknown, branchNote, datasetCount, destination, folderCount, folderId, readyCount, trail, visibleRows.length],
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
      lead="Everything the lab owns, connects to, acquires, and builds."
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
    >
      <LibraryEstateBrowser
        rows={visibleRows}
        datasets={datasets}
        branchDatasets={branchDatasetRows}
        isRoot={isRoot}
        currentFolderName={currentFolderName}
        branchNote={branchNote}
        selectedId={selectedId}
        filterMode={filterMode}
        sortBy={sortBy}
        onFilterChange={setFilterMode}
        onSortChange={setSortBy}
        onOpenFolder={(folder) => onFolderChange(folder.id)}
        onSelectDataset={onSelectDataset}
        onPreviewDataset={onPreviewDataset}
      />
    </PageShell>
  );
}
