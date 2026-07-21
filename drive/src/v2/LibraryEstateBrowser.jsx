import { displayName, statusPillKind } from "@/v2/datasetMeta";
import { StatusPill } from "@/v2/StatusPill";
import {
  assetMeta,
  assetPurpose,
  collectionEstateSummary,
  libraryAssetCounts,
} from "@/v2/libraryEstate";

/**
 * Library estate — LIBRARY_FULL_SCALE_FREEZE skeletal centre:
 * readiness chips · COLLECTIONS | EVIDENCE ledger (SOURCE · VERIFY · STATE)
 */

function ReadinessChips({ mode, counts, onChange }) {
  const chips = [
    { id: "all", label: "All", count: counts.total },
    { id: "ready", label: "Query-ready", count: counts.queryReady },
    { id: "registered", label: "Registered", count: counts.registered },
    { id: "metadata", label: "Metadata only", count: counts.metadataOnly },
  ];
  return (
    <div className="rd-v2-library-readiness" role="tablist" aria-label="Evidence readiness">
      {chips.map((chip) => (
        <button
          key={chip.id}
          type="button"
          role="tab"
          aria-selected={mode === chip.id}
          className={mode === chip.id ? "on" : ""}
          onClick={() => onChange(chip.id)}
        >
          {chip.label} <b>{chip.count}</b>
        </button>
      ))}
    </div>
  );
}

function sourceCell(row) {
  return row?.source || row?.publisher || row?.source_route || row?.backend || "—";
}

function verifyCell(row) {
  const kind = statusPillKind(row).kind;
  if (kind === "query-ready") return "Verified";
  if (row?.archive_verified === true) return "Archived";
  if (kind === "connected") return "Connected";
  return "Unverified";
}

function CollectionTreeItem({ folder, datasets, onOpen, active }) {
  const summary = collectionEstateSummary(folder, datasets);
  return (
    <button
      type="button"
      className={`rd-v2-library-tree-item${active ? " on" : ""}`}
      onClick={() => onOpen(folder)}
      data-testid="library-collection"
      data-kind="folder"
      aria-pressed={active}
    >
      {active ? <span className="rd-v2-library-selected-mark" aria-hidden>▌</span> : null}
      <strong>{summary.title}</strong>
      <span>{summary.counts.total}</span>
    </button>
  );
}

function EvidenceLedgerRow({ item, selected, onSelect, onDoubleClick }) {
  const row = item?.row || item;
  const purpose = assetPurpose(row);
  return (
    <button
      type="button"
      className={`rd-v2-library-ledger-row${selected ? " selected" : ""}`}
      onClick={() => onSelect(row)}
      onDoubleClick={() => onDoubleClick?.(row)}
      data-kind="dataset"
      aria-pressed={selected}
    >
      <span className="rd-v2-library-ledger-title">
        {selected ? <span className="rd-v2-library-selected-mark" aria-hidden>▌</span> : null}
        <strong>{displayName(row)}</strong>
        {purpose ? <em>{purpose}</em> : null}
      </span>
      <span className="rd-v2-library-ledger-source">{sourceCell(row)}</span>
      <span className="rd-v2-library-ledger-verify">{verifyCell(row)}</span>
      <span className="rd-v2-library-ledger-state">
        <StatusPill dataset={row} />
      </span>
    </button>
  );
}

export function LibraryEstateBrowser({
  rows,
  datasets,
  branchDatasets,
  collectionFolders = null,
  isRoot,
  currentFolderId = "",
  currentFolderName,
  branchNote,
  selectedId,
  filterMode,
  sortBy,
  estateQuery = "",
  onEstateQueryChange,
  onFilterChange,
  onSortChange,
  onOpenFolder,
  onSelectDataset,
  onPreviewDataset,
}) {
  const folders = Array.isArray(collectionFolders) && collectionFolders.length
    ? collectionFolders
    : rows.filter((item) => item?.kind === "folder");
  const assetsFromRows = rows.filter((item) => item?.kind !== "folder");
  // Freeze: COLLECTIONS tree + EVIDENCE ledger. Selected collection filters branchDatasets.
  const assets = Array.isArray(collectionFolders)
    ? (branchDatasets || []).map((row) => ({ kind: "dataset", id: row.dataset_id, row }))
    : isRoot && !assetsFromRows.length
      ? (branchDatasets || []).map((row) => ({ kind: "dataset", id: row.dataset_id, row }))
      : assetsFromRows;
  const counts = libraryAssetCounts(branchDatasets);
  const q = String(estateQuery || "").trim().toLowerCase();
  const visibleAssets = q
    ? assets.filter((item) => {
        const row = item?.row || item;
        const hay = [displayName(row), assetPurpose(row), sourceCell(row), ...(assetMeta(row) || [])]
          .join(" ")
          .toLowerCase();
        return hay.includes(q);
      })
    : assets;

  return (
    <div className="rd-v2-library-estate rd-v2-library-estate-wire" data-testid="library-estate-browser">
      <header className="rd-v2-library-estate-head">
        <div>
          <h2>{isRoot ? "Research evidence estate" : currentFolderName}</h2>
          <p>
            {counts.total} asset{counts.total === 1 ? "" : "s"}
            {counts.queryReady ? ` · ${counts.queryReady} query-ready` : ""}
          </p>
          {!isRoot && branchNote ? <p className="rd-v2-library-estate-note">{branchNote}</p> : null}
        </div>
        <label className="rd-v2-library-estate-search">
          <span className="sr-only">Search assets</span>
          <input
            value={estateQuery}
            onChange={(e) => onEstateQueryChange?.(e.target.value)}
            placeholder="Search assets, entities, fields, sources, provenance…"
            aria-label="Search Library estate"
          />
        </label>
      </header>

      <ReadinessChips mode={filterMode} counts={counts} onChange={onFilterChange} />

      <div className="rd-v2-library-split">
        <aside className="rd-v2-library-collections-pane" aria-label="Collections">
          <header>
            <span>Collections</span>
            <b>{folders.length}</b>
          </header>
          <div className="rd-v2-library-tree">
            {folders.length ? (
              folders.map((folder) => (
                <CollectionTreeItem
                  key={folder.id}
                  folder={folder}
                  datasets={datasets}
                  onOpen={onOpenFolder}
                  active={Boolean(currentFolderId) && currentFolderId === folder.id}
                />
              ))
            ) : (
              <p className="rd-v2-library-pane-empty">No collections in this branch.</p>
            )}
          </div>
        </aside>

        <section className="rd-v2-library-evidence-pane" aria-label="Evidence">
          <header className="rd-v2-library-ledger-head">
            <span>Evidence</span>
            <span>Source</span>
            <span>Verify</span>
            <span>State</span>
          </header>
          <div className="rd-v2-library-ledger">
            {visibleAssets.length ? (
              visibleAssets.map((item) => {
                const row = item?.row || item;
                return (
                  <EvidenceLedgerRow
                    key={row.dataset_id || item.id}
                    item={item}
                    selected={selectedId === row.dataset_id}
                    onSelect={onSelectDataset}
                    onDoubleClick={onPreviewDataset}
                  />
                );
              })
            ) : (
              <div className="rd-v2-library-empty">
                <strong>No holdings in this collection</strong>
                <p>Add evidence to this collection, clear the readiness filter, or return to Lab.</p>
                <div className="rd-v2-library-empty-actions">
                  <span className="muted small">Use + Add evidence to upload, add a URL/DOI, or find external evidence.</span>
                </div>
              </div>
            )}
          </div>
          <div className="rd-v2-library-ledger-tools">
            <button
              type="button"
              className={sortBy === "name" ? "on" : ""}
              onClick={() => onSortChange?.("name")}
            >
              Name
            </button>
            <button
              type="button"
              className={sortBy === "updated" ? "on" : ""}
              onClick={() => onSortChange?.("updated")}
            >
              Last modified
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
