import { displayName, statusPillKind } from "@/v2/datasetMeta";
import { StatusPill } from "@/v2/StatusPill";
import {
  assetMeta,
  assetPurpose,
  assetTypeLabel,
  collectionEstateSummary,
  libraryAssetCounts,
} from "@/v2/libraryEstate";

function LibraryFilterMenu({ mode, counts, onChange }) {
  return (
    <details className="rd-v2-library-control-menu" data-testid="library-filter-menu">
      <summary>
        <span>Filter</span>
        {mode === "ready" ? <strong>Query ready</strong> : null}
      </summary>
      <div className="rd-v2-library-control-popover" role="group" aria-label="Filter Library assets">
        <button type="button" className={mode === "all" ? "on" : ""} onClick={(event) => { onChange("all"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>
          <span>All assets</span>
          <b>{counts.total}</b>
        </button>
        <button type="button" className={mode === "ready" ? "on" : ""} onClick={(event) => { onChange("ready"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>
          <span>Query ready</span>
          <b>{counts.queryReady}</b>
        </button>
      </div>
    </details>
  );
}

function LibrarySortMenu({ sortBy, onChange }) {
  return (
    <details className="rd-v2-library-control-menu" data-testid="library-sort-menu">
      <summary>
        <span>Sort</span>
        <strong>{sortBy === "updated" ? "Last modified" : "Name"}</strong>
      </summary>
      <div className="rd-v2-library-control-popover" role="group" aria-label="Sort Library assets">
        <button type="button" className={sortBy === "name" ? "on" : ""} onClick={(event) => { onChange("name"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>
          Name
        </button>
        <button type="button" className={sortBy === "updated" ? "on" : ""} onClick={(event) => { onChange("updated"); event.currentTarget.closest("details")?.removeAttribute("open"); }}>
          Last modified
        </button>
      </div>
    </details>
  );
}

function CollectionCard({ folder, datasets, onOpen }) {
  const summary = collectionEstateSummary(folder, datasets);
  return (
    <button
      type="button"
      className={`rd-v2-library-collection rd-v2-library-collection-${summary.tone}`}
      onClick={() => onOpen(folder)}
      data-testid="library-collection"
      data-kind="folder"
    >
      <span className="rd-v2-library-collection-mark" aria-hidden>
        <span />
      </span>
      <span className="rd-v2-library-collection-copy">
        <strong>{summary.title}</strong>
        <span>{summary.description}</span>
        <em>
          {summary.counts.total} dataset{summary.counts.total === 1 ? "" : "s"}
          {summary.counts.queryReady ? ` · ${summary.counts.queryReady} query ready` : ""}
        </em>
      </span>
      <span className="rd-v2-library-row-arrow" aria-hidden>→</span>
    </button>
  );
}

function AssetRow({ item, selected, onSelect, onDoubleClick }) {
  const row = item?.row || item;
  const purpose = assetPurpose(row);
  const meta = assetMeta(row);
  const state = statusPillKind(row);
  return (
    <button
      type="button"
      className={`rd-v2-library-asset${selected ? " selected" : ""}`}
      onClick={() => onSelect(row)}
      onDoubleClick={() => onDoubleClick?.(row)}
      data-kind="dataset"
      data-readiness={state.kind}
      aria-pressed={selected}
    >
      <span className="rd-v2-library-asset-main">
        <span className="rd-v2-library-asset-heading">
          <strong>{displayName(row)}</strong>
          <StatusPill dataset={row} />
        </span>
        {purpose ? <span className="rd-v2-library-asset-purpose">{purpose}</span> : null}
        {meta.length ? (
          <span className="rd-v2-library-asset-meta">
            {meta.map((value) => <em key={value}>{value}</em>)}
          </span>
        ) : null}
      </span>
      <span className="rd-v2-library-asset-type">{assetTypeLabel(row)}</span>
      <span className="rd-v2-library-row-arrow" aria-hidden>→</span>
    </button>
  );
}

export function LibraryEstateBrowser({
  rows,
  datasets,
  branchDatasets,
  isRoot,
  currentFolderName,
  branchNote,
  selectedId,
  filterMode,
  sortBy,
  onFilterChange,
  onSortChange,
  onOpenFolder,
  onSelectDataset,
  onPreviewDataset,
}) {
  const folders = rows.filter((item) => item?.kind === "folder");
  const assets = rows.filter((item) => item?.kind !== "folder");
  const counts = libraryAssetCounts(branchDatasets);
  const rootTitle = "All holdings";

  return (
    <div className="rd-v2-library-estate" data-testid="library-estate-browser">
      <section className="rd-v2-library-estate-summary" aria-label="Library estate summary">
        <div>
          <p className="rd-v2-library-estate-eyebrow">{isRoot ? "Research data estate" : "Folder"}</p>
          <h2>{isRoot ? rootTitle : currentFolderName}</h2>
          <p className="rd-v2-library-estate-scope">
            {counts.total} asset{counts.total === 1 ? "" : "s"}
            {counts.queryReady ? ` · ${counts.queryReady} ready to use` : ""}
          </p>
          {!isRoot && branchNote ? <p className="rd-v2-library-estate-note">{branchNote}</p> : null}
        </div>
        <div className="rd-v2-library-estate-controls">
          <LibraryFilterMenu mode={filterMode} counts={counts} onChange={onFilterChange} />
          <LibrarySortMenu sortBy={sortBy} onChange={onSortChange} />
        </div>
      </section>

      {folders.length ? (
        <section className="rd-v2-library-estate-section" aria-label="Collections">
          <header className="rd-v2-library-estate-section-head">
            <div>
              <p>Folders</p>
              <span>{isRoot ? "Organize and browse the lab's data estate" : "Folders in this collection"}</span>
            </div>
            <b>{folders.length}</b>
          </header>
          <div className="rd-v2-library-collections">
            {folders.map((folder) => (
              <CollectionCard key={folder.id} folder={folder} datasets={datasets} onOpen={onOpenFolder} />
            ))}
          </div>
        </section>
      ) : null}

      {assets.length ? (
        <section className="rd-v2-library-estate-section" aria-label="Assets">
          <header className="rd-v2-library-estate-section-head">
            <div>
              <p>Data assets</p>
              <span>Registered datasets and reusable research objects</span>
            </div>
            <b>{assets.length}</b>
          </header>
          <div className="rd-v2-library-assets">
            {assets.map((item) => {
              const row = item?.row || item;
              return (
                <AssetRow
                  key={row.dataset_id || item.id}
                  item={item}
                  selected={selectedId === row.dataset_id}
                  onSelect={onSelectDataset}
                  onDoubleClick={onPreviewDataset}
                />
              );
            })}
          </div>
        </section>
      ) : null}

      {!rows.length ? (
        <div className="rd-v2-library-empty">
          <strong>No holdings in this collection</strong>
          <p>Clear the filter or return to Lab to browse the indexed data estate.</p>
        </div>
      ) : null}
    </div>
  );
}
