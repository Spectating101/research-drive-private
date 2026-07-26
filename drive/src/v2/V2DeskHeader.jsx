/** v2 header — brand · research context · resting status (no global search/Ask pill) */

import { deskStatusBadgeLabel } from "@/v2/deskHealthPresentation";

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

      <div className="rd-v2-header-meta">
        <div className="rd-v2-trust-strip" aria-label="Desk status" data-testid="desk-integration-strip">
          {deskStatus === "ok" ? (
            <span className="rd-v2-trust-badge ok">{deskStatusBadgeLabel("ok")}</span>
          ) : deskStatus === "syncing" ? (
            <span className="rd-v2-trust-badge muted">{deskStatusBadgeLabel("syncing")}</span>
          ) : deskStatus === "empty" ? (
            <span className="rd-v2-trust-badge warn">{deskStatusBadgeLabel("empty")}</span>
          ) : usingSeed || deskStatus === "demo" ? (
            <span className="rd-v2-trust-badge warn">{deskStatusBadgeLabel("demo", { usingSeed: true })}</span>
          ) : deskStatus === "degraded" ? (
            <span className="rd-v2-trust-badge warn">{deskStatusBadgeLabel("degraded")}</span>
          ) : (
            <span className="rd-v2-trust-badge warn">{deskStatusBadgeLabel(deskStatus)}</span>
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
