export function DeskStatusBadges({ datasetCount = 0, connectedCount = 0, workCount = 0, className = "" }) {
  return (
    <div className={`rd-header-status ${className}`.trim()} aria-label="Desk status">
      <span><strong>{datasetCount}</strong> datasets</span>
      <span><strong>{connectedCount}</strong> query links</span>
      <span className={workCount > 0 ? "active" : ""}><strong>{workCount}</strong> jobs</span>
    </div>
  );
}
