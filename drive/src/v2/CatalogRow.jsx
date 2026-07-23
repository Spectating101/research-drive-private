import { statusPill, displayName, rowSubtitle } from "@/v2/datasetMeta";
import { datasetBrowsePathLabel, folderBrowseSummary } from "@/v2/folderBrowseSummary";
import { StatusPill } from "@/v2/StatusPill";
import { SourceRibbon } from "@/v2/ui";

const DatasetIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <ellipse cx="12" cy="5" rx="9" ry="3"/>
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
  </svg>
);
const FolderRowIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
  </svg>
);

function datasetDescription(dataset) {
  return dataset?.description
    || dataset?.recommended_use
    || dataset?.source
    || null;
}

export function CatalogRow({
  item,
  selected,
  onSelect,
  onOpenFolder,
  onDoubleClick,
  external = false,
  compact = false,
  rowState,
}) {
  const isFolder = item.kind === "folder";
  const dataset = item.row || item;
  const title = isFolder ? item.name : displayName(dataset);
  const folderSummary = isFolder ? folderBrowseSummary(item) : null;
  const pathLabel = !isFolder ? datasetBrowsePathLabel(item) : "";
  const sub = isFolder ? folderSummary.sub : rowSubtitle(dataset);
  const desc = isFolder
    ? folderSummary.desc
    : compact
      ? null
      : datasetDescription(dataset);
  const state = !isFolder && rowState ? rowState(dataset) : null;
  const kind = isFolder ? "folder" : external ? "external" : "dataset";

  return (
    <li className={selected ? "rd-v2-row-on" : undefined}>
      <button
        type="button"
        className={`row${selected ? " selected" : ""}${external ? " rd-v2-row-ext" : ""}`}
        data-kind={kind}
        onClick={() => (isFolder ? onOpenFolder(item) : onSelect(dataset))}
        onDoubleClick={() => {
          if (!isFolder && onDoubleClick) onDoubleClick(dataset);
        }}
      >
        <span className={`rd-v2-row-icon${external ? " source" : ""}`}>
          {external ? (
            <SourceRibbon source={dataset.source || dataset.collect_via || dataset.source_route} />
          ) : isFolder ? (
            <FolderRowIcon />
          ) : (
            <DatasetIcon />
          )}
        </span>
        <span className="text">
          <span className="row-title">{title}</span>
          {pathLabel ? <span className="row-desc rd-v2-row-path">{pathLabel}</span> : null}
          {desc ? <span className="row-desc">{desc}</span> : null}
          {sub ? <span className="row-sub">{sub}</span> : null}
        </span>
        {!isFolder && state ? (
          <span className={`rd-v2-pill ${state.className}`}>{state.label}</span>
        ) : null}
        {!isFolder && !state ? <StatusPill dataset={dataset} label={statusPill(dataset)} /> : null}
        {isFolder ? (
          <span className="rd-v2-pill muted" title="Datasets in this branch">
            {folderSummary.pill}
          </span>
        ) : null}
      </button>
    </li>
  );
}
