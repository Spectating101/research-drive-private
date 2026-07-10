import { statusPillKind } from "@/v2/datasetMeta";

const STYLES = {
  "query-ready": "rd-v2-status-pill rd-v2-status-ready",
  connected: "rd-v2-status-pill rd-v2-status-connected",
  review: "rd-v2-status-pill rd-v2-status-review",
  failed: "rd-v2-status-pill rd-v2-status-failed",
  external: "rd-v2-status-pill rd-v2-status-external",
  remote: "rd-v2-status-pill rd-v2-status-external",
  queued: "rd-v2-status-pill rd-v2-status-review",
  warn: "rd-v2-status-pill rd-v2-status-review",
};

export function StatusPill({ dataset, label }) {
  const text = label || statusPillKind(dataset).label;
  const kind = statusPillKind(dataset).kind;
  const cls = STYLES[kind] || STYLES["query-ready"];
  return (
    <span className={cls}>
      <span className="rd-v2-status-dot" aria-hidden />
      {text}
    </span>
  );
}
