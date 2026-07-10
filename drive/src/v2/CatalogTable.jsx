import { StatusPill } from "@/v2/StatusPill";
import {
  coverageLabel,
  datasetRowSub,
  datasetRowTitle,
  folderRowTitle,
  sourceLabel,
  statusLabel,
  updatedLabel,
} from "@/v2/catalogColumns";
import { SourceRibbon } from "@/v2/ui";

const FolderIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </svg>
);
const DatasetIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
  </svg>
);

const HEADERS = {
  library: [
    { key: "name", label: "Name", className: "col-name" },
    { key: "ready", label: "Ready", className: "col-ready" },
    { key: "coverage", label: "Coverage", className: "col-coverage" },
    { key: "source", label: "Source", className: "col-source" },
    { key: "updated", label: "Updated", className: "col-updated" },
  ],
  recent: [
    { key: "name", label: "Name", className: "col-name" },
    { key: "ready", label: "Status", className: "col-ready" },
  ],
  discover: [
    { key: "source", label: "Source", className: "col-source" },
    { key: "name", label: "Dataset", className: "col-name" },
    { key: "ready", label: "Status", className: "col-ready" },
  ],
};

function isFolder(item) {
  return item?.kind === "folder";
}

function datasetFromItem(item) {
  return item?.row || item;
}

export function CatalogTable({
  variant = "library",
  rows = [],
  selectedId,
  onSelectDataset,
  onOpenFolder,
  onDoubleClick,
  onSelectDiscover,
  discoverState,
}) {
  const headers = HEADERS[variant] || HEADERS.library;

  if (!rows.length) return null;

  return (
    <div className="rd-v2-catalog-table-wrap">
      <table className="rd-v2-catalog-table">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h.key} className={h.className} scope="col">
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => {
            if (variant === "discover") {
              const id = item.dataset_id || item.title || item.url;
              const state = discoverState?.(item) || { label: "External", className: "muted" };
              const selected = selectedId === id;
              const isExternal = !state.label.includes("In lab");
              return (
                <tr
                  key={id}
                  className={`${selected ? "selected" : ""}${isExternal ? " rd-v2-row-external" : ""}`}
                  onClick={() => onSelectDiscover?.(item)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onSelectDiscover?.(item);
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <td className="col-source">
                    <SourceRibbon source={item.source || item.collect_via || item.source_route} />
                  </td>
                  <td className="col-name">
                    <span className="rd-v2-ct-title">{item.title || datasetRowTitle(item)}</span>
                    <span className="rd-v2-ct-sub">{item.subtitle || datasetRowSub(item)}</span>
                  </td>
                  <td className="col-ready">
                    <span className={`rd-v2-pill ${state.className}`}>{state.label}</span>
                  </td>
                </tr>
              );
            }

            if (isFolder(item)) {
              return (
                <tr
                  key={item.id}
                  className="folder-row"
                  onClick={() => onOpenFolder?.(item)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onOpenFolder?.(item);
                  }}
                  tabIndex={0}
                  role="button"
                >
                  <td className="col-name" colSpan={headers.length}>
                    <span className="rd-v2-ct-icon"><FolderIcon /></span>
                    <span className="rd-v2-ct-title">{folderRowTitle(item)}</span>
                    <span className="rd-v2-ct-sub muted">
                      {Object.keys(item.children || {}).length} items
                    </span>
                  </td>
                </tr>
              );
            }

            const dataset = datasetFromItem(item);
            const id = dataset.dataset_id;
            const selected = selectedId === id;

            return (
              <tr
                key={id}
                className={selected ? "selected" : undefined}
                onClick={() => onSelectDataset?.(dataset)}
                onDoubleClick={() => onDoubleClick?.(dataset)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSelectDataset?.(dataset);
                }}
                tabIndex={0}
                role="button"
              >
                <td className="col-name">
                  <span className="rd-v2-ct-icon"><DatasetIcon /></span>
                  <span className="rd-v2-ct-title">{datasetRowTitle(dataset)}</span>
                  <span className="rd-v2-ct-sub">{datasetRowSub(dataset)}</span>
                </td>
                {variant === "library" ? (
                  <>
                    <td className="col-ready">
                      <StatusPill dataset={dataset} label={statusLabel(dataset)} />
                    </td>
                    <td className="col-coverage">{coverageLabel(dataset)}</td>
                    <td className="col-source">{sourceLabel(dataset)}</td>
                    <td className="col-updated">{updatedLabel(dataset)}</td>
                  </>
                ) : (
                  <td className="col-ready">
                    <StatusPill dataset={dataset} label={statusLabel(dataset)} />
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
