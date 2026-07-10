import { CatalogRow } from "@/v2/CatalogRow";

function rowKey(item) {
  if (item?.kind === "folder") return `folder:${item.id}`;
  const dataset = item?.row || item;
  return `dataset:${item?.id || dataset?.dataset_id || dataset?.title || dataset?.url}`;
}

function isSelected(item, selectedId) {
  if (item?.kind === "folder") return false;
  const dataset = item?.row || item;
  return selectedId === (item?.id || dataset?.dataset_id || dataset?.title || dataset?.url);
}

/** Drive-style list — folders + datasets in one scroll (Library / Home). */
export function CatalogList({
  rows = [],
  selectedId,
  onSelectDataset,
  onOpenFolder,
  onDoubleClick,
  compact = true,
  external = false,
  rowState,
}) {
  if (!rows.length) return null;

  return (
    <ul className="rd-v2-catalog rd-v2-catalog-list" aria-label="Catalog">
      {rows.map((item) => (
        <CatalogRow
          key={rowKey(item)}
          item={item}
          selected={isSelected(item, selectedId)}
          compact={compact}
          external={external || item?.external}
          rowState={rowState}
          onSelect={onSelectDataset}
          onOpenFolder={onOpenFolder}
          onDoubleClick={onDoubleClick}
        />
      ))}
    </ul>
  );
}
