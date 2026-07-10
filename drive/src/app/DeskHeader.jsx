import { DeskStatusBadges } from "@/app/DeskStatusBadges";

export function DeskHeader({
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  onAskFromSearch,
  onOpenNew,
  onOpenSignIn,
  onBrandClick,
  headerInitials,
  datasetCount,
  connectedCount,
  workCount,
  onNavToggle,
}) {
  return (
    <header className="yzu-header">
      <button type="button" className="yzu-nav-toggle" aria-label="Menu" onClick={onNavToggle}>
        ☰
      </button>
      <button type="button" className="yzu-brand" onClick={onBrandClick}>
        <span className="rd-brand-mark">RD</span>
        <div className="yzu-brand-text">
          <strong>Research Drive</strong>
        </div>
      </button>
      <div className="rd-search">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="m21 21-4.2-4.2m1.2-5.3a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search datasets in the library"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSearchSubmit();
            }
          }}
        />
        <button type="button" className="btn-ghost" onClick={onAskFromSearch}>
          Source
        </button>
      </div>
      <DeskStatusBadges
        className="rd-header-status-wrap"
        datasetCount={datasetCount}
        connectedCount={connectedCount}
        workCount={workCount}
      />
      <div className="rd-top-actions">
        <button type="button" className="btn-round" onClick={onOpenNew}>
          New
        </button>
        <button type="button" className="rd-header-avatar" aria-label="Account" onClick={onOpenSignIn}>
          {headerInitials}
        </button>
      </div>
    </header>
  );
}
