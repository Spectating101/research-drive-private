/** v2 header — freeze shell: research context ▾ · page · search · resting status */

function freshnessLabel(refreshedAt) {
  if (refreshedAt == null) return null;
  const sec = Math.max(0, Math.round((Date.now() - refreshedAt) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  return `${min}m ago`;
}

const PAGE_LABELS = {
  home: "HOME",
  library: "LIBRARY",
  browse: "DISCOVER",
  synthesis: "SYNTHESIS",
  resources: "RESOURCES",
  profile: "PROFILE",
  settings: "SETTINGS",
};

export function V2DeskHeader({
  searchQuery,
  onSearchChange,
  onSearchSubmit,
  onAskFromSearch,
  onBrandClick,
  onRetry,
  headerInitials = "YZ",
  datasetCount = 0,
  usingSeed = false,
  workCount = 0,
  onPendingClick,
  deskStatus = "unknown",
  refreshedAt = null,
  dryRunProtected: _dryRunProtected = true,
  integrationChips = [],
  activeResearchTitle = "Active research",
  currentPage = "home",
  /**
   * Catalog search lives only on Library. Everywhere else (incl. Discover, which has
   * its own bar) the header is Ask-only — no shared global query.
   */
  libraryOwnsSearch = false,
}) {
  const metaText = usingSeed
    ? `${datasetCount} datasets`
    : workCount > 0
      ? `${datasetCount} datasets · ${workCount} pending`
      : `${datasetCount} datasets`;
  const fresh = freshnessLabel(refreshedAt);
  const chips = Array.isArray(integrationChips) ? integrationChips : [];
  const pageLabel = PAGE_LABELS[currentPage] || String(currentPage || "").toUpperCase();

  return (
    <header className="yzu-header rd-v2-header rd-v2-header-wire">
      <button type="button" className="yzu-brand" onClick={onBrandClick}>
        <span className="rd-brand-mark">RD</span>
        <div className="yzu-brand-text">
          <strong>Research Drive</strong>
        </div>
      </button>

      <div className="rd-v2-header-context" aria-label="Active research context">
        <button type="button" className="rd-v2-header-research" title={activeResearchTitle}>
          <span>{activeResearchTitle}</span>
          <em aria-hidden>▾</em>
        </button>
        <span className="rd-v2-header-page" data-testid="header-page-label">
          {pageLabel}
        </span>
      </div>

      {libraryOwnsSearch ? (
        <div className="rd-search rd-v2-search-pill" data-testid="header-library-search">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="m21 21-4.2-4.2m1.2-5.3a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <input
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search this library…"
            aria-label="Search library holdings"
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onSearchSubmit();
              }
              if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
                e.preventDefault();
                onAskFromSearch();
              }
            }}
          />
          <button type="button" className="rd-v2-search-kbd" onClick={onAskFromSearch} title="Ask">
            ⌘K
          </button>
        </div>
      ) : (
        <div className="rd-search rd-v2-search-pill rd-v2-search-pill--ask" data-testid="header-ask-only">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 3c4.4 0 8 3.1 8 7s-3.6 7-8 7c-.7 0-1.4-.1-2-.2L5 19l1.1-3.3C4.8 14.6 4 12.9 4 10c0-3.9 3.6-7 8-7Z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          </svg>
          <button
            type="button"
            className="rd-v2-header-ask-trigger"
            onClick={onAskFromSearch}
            aria-label="Ask the desk"
          >
            Ask the desk…
          </button>
          <button type="button" className="rd-v2-search-kbd" onClick={onAskFromSearch} title="Ask">
            ⌘K
          </button>
        </div>
      )}
      <div className="rd-v2-header-meta">
        <div className="rd-v2-trust-strip" aria-label="Desk status" data-testid="desk-integration-strip">
          {deskStatus === "ok" ? (
            <span className="rd-v2-trust-badge ok">Live registry</span>
          ) : deskStatus === "syncing" ? (
            <span className="rd-v2-trust-badge muted">Syncing…</span>
          ) : deskStatus === "empty" ? (
            <span className="rd-v2-trust-badge warn">Empty registry</span>
          ) : usingSeed || deskStatus === "demo" ? (
            <span className="rd-v2-trust-badge warn">Demo catalog</span>
          ) : deskStatus === "degraded" ? (
            <span className="rd-v2-trust-badge warn">Desk degraded</span>
          ) : (
            <span className="rd-v2-trust-badge warn">Desk API offline</span>
          )}
          {chips
            .filter((chip) => ["warn", "error", "danger", "bad"].includes(chip.tone))
            .map((chip) => (
              <span
                key={chip.id}
                className={`rd-v2-trust-badge ${chip.tone || "muted"}`}
                title={chip.label}
              >
                {chip.label}
              </span>
            ))}
          {/* Keep trust strip lean: Live registry + warn chips only (no dry-run / age dump). */}
          {fresh && deskStatus !== "ok" ? (
            <span className="rd-v2-trust-badge muted">Updated {fresh}</span>
          ) : null}
        </div>
        <span className="rd-v2-header-meta-count" title={metaText}>
          {workCount > 0 && onPendingClick ? (
            <>
              {`${datasetCount} datasets · `}
              <button
                type="button"
                className="rd-v2-header-pending-link"
                data-testid="header-pending-link"
                onClick={onPendingClick}
              >
                {workCount} pending
              </button>
            </>
          ) : (
            metaText
          )}
        </span>
        {usingSeed && onRetry ? (
          <button type="button" className="rd-v2-header-retry" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
      <button type="button" className="rd-header-avatar" aria-label="Account">
        {headerInitials}
      </button>
    </header>
  );
}
