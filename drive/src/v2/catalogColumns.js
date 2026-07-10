import { displayName, statusPill } from "@/v2/datasetMeta";

export function coverageLabel(dataset) {
  return dataset?.coverage || dataset?.date_range || dataset?.temporal_coverage || "—";
}

export function sourceLabel(dataset) {
  return dataset?.source || dataset?.publisher || dataset?.domain || dataset?.backend || "—";
}

export function updatedLabel(dataset) {
  const raw = dataset?.updated_at || dataset?.last_modified || dataset?.as_of;
  if (!raw) return "—";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 10);
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days < 1) return "Today";
  if (days === 1) return "1d ago";
  if (days < 14) return `${days}d ago`;
  return d.toISOString().slice(0, 10);
}

export function folderRowTitle(item) {
  return item?.name || "Folder";
}

export function datasetRowTitle(dataset) {
  return displayName(dataset);
}

export function datasetRowSub(dataset) {
  const parts = [dataset?.dataset_id, dataset?.grain].filter(Boolean);
  return parts.join(" · ");
}

export function statusLabel(dataset) {
  return statusPill(dataset);
}
