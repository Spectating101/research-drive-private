import { FolderOpen } from "lucide-react";

export function EmptyRailState({
  title = "No dataset selected",
  hint = "Select a row in the catalog to inspect metadata, preview rows, or ask about procurement.",
}) {
  return (
    <div className="rd-v2-rail-empty-state" role="status">
      <FolderOpen className="rd-v2-rail-empty-icon" size={40} strokeWidth={1.25} aria-hidden />
      <p className="rd-v2-rail-empty-title">{title}</p>
      <p className="rd-v2-rail-empty-hint">{hint}</p>
    </div>
  );
}
